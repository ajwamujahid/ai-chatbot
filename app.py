

from flask import Flask, Response, request, jsonify, render_template, send_file, stream_with_context
from dotenv import load_dotenv
from agents import Agent, Runner, function_tool # type: ignore
from groq import Groq # type: ignore
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import time
import pandas as pd
import numpy as np

from services.file_context import build_csv_summary, extract_pdf_text, is_allowed_file
from services.storage import (
    clear_messages,
    count_session_messages,
    create_session,
    delete_session,
    ensure_default_session,
    get_session,
    init_db,
    list_sessions,
    load_all_chat_messages,
    load_chat_history,
    rename_session,
    save_message,
    search_chat,
    set_message_feedback,
    set_session_pinned,
    update_assistant_message,
    update_user_message,
)

MPL_CACHE_DIR = Path(__file__).resolve().parent / ".matplotlib-cache"
MPL_CACHE_DIR.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))

import matplotlib
matplotlib.use('Agg')  # Server pe graph banana
import matplotlib.pyplot as plt
import io
import base64

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
load_dotenv(override=True)

app = Flask(__name__)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_HISTORY = 20  # kitne messages yaad rakhe
MAX_FILE_CHARS = 12000
openai_available = bool(os.getenv("OPENAI_API_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=30.0) if os.getenv("GROQ_API_KEY") else None
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# In-memory chat history
chat_history = []
current_session_id = 1
attached_file = {
    "name": "",
    "content": "",
    "chars": 0,
    "summary": "",
}

BASE_AGENT_INSTRUCTIONS = (
    "Reply in the same language style as the user, including Roman Urdu/Hinglish when appropriate. "
    "Be concise, practical, and friendly. "
    "When the user asks about chat stats, analytics, message counts, or conversation history, "
    "use the get_chat_stats tool before answering."
)

AGENT_PROFILES = {
    "general": {
        "label": "General",
        "name": "General Assistant",
        "instructions": "You are a helpful general-purpose AI assistant.",
    },
    "coding": {
        "label": "Coding",
        "name": "Coding Agent",
        "instructions": (
            "You are a senior coding assistant. Give practical implementation steps, "
            "debugging help, and clean code guidance."
        ),
    },
    "study": {
        "label": "Study",
        "name": "Study Agent",
        "instructions": (
            "You are a patient study tutor. Explain concepts simply, make notes, "
            "quiz the user, and break topics into easy steps."
        ),
    },
    "business": {
        "label": "Business",
        "name": "Business Agent",
        "instructions": (
            "You are a business planning assistant. Help with ideas, marketing, "
            "customer research, pricing, and clear action plans."
        ),
    },
}


def build_chat_stats() -> str:
    """Return basic stats about the current chat conversation."""
    if not chat_history:
        return "No messages yet."

    user_messages = [m["content"] for m in chat_history if m["role"] == "user"]
    assistant_messages = [m["content"] for m in chat_history if m["role"] == "assistant"]
    avg_user_len = int(np.mean([len(m) for m in user_messages])) if user_messages else 0
    avg_assistant_len = int(np.mean([len(m) for m in assistant_messages])) if assistant_messages else 0

    return (
        f"Total messages: {len(chat_history)}. "
        f"User messages: {len(user_messages)}. "
        f"Assistant messages: {len(assistant_messages)}. "
        f"Average user message length: {avg_user_len}. "
        f"Average assistant message length: {avg_assistant_len}."
    )


@function_tool
def get_chat_stats() -> str:
    """Return basic stats about the current chat conversation."""
    return build_chat_stats()


def is_stats_request(message: str) -> bool:
    """Detect simple local chat stats requests."""
    text = message.lower()
    return any(term in text for term in (
        "stats",
        "analytics",
        "message count",
        "chat history",
        "stats batao",
        "kitne message",
        "kitni chat",
    ))


def model_context_messages(exclude_ids: set[int] | None = None) -> list[dict[str, str]]:
    """Return only role/content pairs for model APIs."""
    messages = []
    exclude_ids = exclude_ids or set()

    if attached_file["content"]:
        summary = ""
        if attached_file["summary"]:
            summary = f"Attached file auto-analysis:\n{attached_file['summary']}\n\n"

        messages.append({
            "role": "user",
            "content": (
                f"Attached file name: {attached_file['name']}\n"
                f"{summary}"
                f"Attached file content:\n{attached_file['content']}"
            ),
        })

    messages.extend([
        {"role": msg["role"], "content": msg["content"]}
        for msg in chat_history[-MAX_HISTORY:]
        if int(msg.get("id") or 0) not in exclude_ids
    ])
    return messages


assistant_agents = {
    key: Agent(
        name=profile["name"],
        model=MODEL,
        instructions=f"{profile['instructions']} {BASE_AGENT_INSTRUCTIONS}",
        tools=[get_chat_stats],
    )
    for key, profile in AGENT_PROFILES.items()
}


def trim_history() -> None:
    """Keep only the latest messages in memory."""
    if len(chat_history) > MAX_HISTORY:
        del chat_history[:-MAX_HISTORY]


TITLE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "batao",
    "banao",
    "do",
    "for",
    "hai",
    "hain",
    "in",
    "is",
    "ka",
    "ke",
    "ki",
    "ko",
    "karo",
    "liye",
    "mein",
    "mujhe",
    "of",
    "on",
    "or",
    "please",
    "the",
    "to",
    "ye",
}


def build_session_title(message: str) -> str:
    """Create a short local title from the first user message."""
    words = re.findall(r"[A-Za-z0-9]+", message.lower())
    useful_words = [word for word in words if word not in TITLE_STOP_WORDS]
    title_words = useful_words[:4] or words[:4]

    if not title_words:
        return "New Chat"

    return " ".join(word.capitalize() for word in title_words)[:60]


def maybe_auto_title_session(user_message: str) -> None:
    """Auto-title fresh default sessions from the first user message."""
    session = get_session(current_session_id)
    if not session:
        return

    if count_session_messages(current_session_id) > 0:
        return

    if not re.fullmatch(r"Chat \d+", session["title"]):
        return

    rename_session(current_session_id, build_session_title(user_message))


def save_turn(
    user_message: str,
    bot_reply: str,
    agent_label: str = "",
    provider_label: str = "",
) -> dict[str, int]:
    """Save a user/assistant turn to memory."""
    global current_session_id
    maybe_auto_title_session(user_message)
    user_message_id = save_message("user", user_message, agent_label, "", current_session_id)
    assistant_message_id = save_message(
        "assistant",
        bot_reply,
        agent_label,
        provider_label,
        current_session_id,
    )
    chat_history.append({
        "id": user_message_id,
        "role": "user",
        "content": user_message,
        "agent": agent_label,
        "provider": "",
    })
    chat_history.append({
        "id": assistant_message_id,
        "role": "assistant",
        "content": bot_reply,
        "agent": agent_label,
        "provider": provider_label,
    })
    trim_history()
    return {
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message_id,
    }


def get_agent_key(raw_agent: str | None) -> str:
    """Return a valid agent key."""
    return raw_agent if raw_agent in AGENT_PROFILES else "general"


def run_groq_fallback(
    user_message: str,
    agent_key: str,
    context_messages: list[dict[str, str]] | None = None,
) -> str | None:
    """Use Groq when OpenAI API quota is unavailable."""
    if not groq_client:
        return None

    profile = AGENT_PROFILES[get_agent_key(agent_key)]
    context_messages = context_messages if context_messages is not None else model_context_messages()

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": f"{profile['instructions']} {BASE_AGENT_INSTRUCTIONS}",
            },
            *context_messages,
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


def generate_reply(
    user_message: str,
    agent_key: str,
    context_messages: list[dict[str, str]] | None = None,
) -> tuple[str, str]:
    """Generate one assistant reply and return reply/provider."""
    global openai_available
    context_messages = context_messages if context_messages is not None else model_context_messages()

    if is_stats_request(user_message):
        return build_chat_stats(), "Local stats"

    if not openai_available:
        bot_reply = run_groq_fallback(user_message, agent_key, context_messages)
        if bot_reply:
            return bot_reply, "Groq fallback"
        raise RuntimeError(
            "OPENAI_API_KEY missing hai. Free fallback ke liye `.env` mein GROQ_API_KEY "
            "add karein, phir Flask server restart karein."
        )

    try:
        result = Runner.run_sync(
            assistant_agents[agent_key],
            [
                *context_messages,
                {"role": "user", "content": user_message},
            ],
        )
        return result.final_output, "OpenAI Agents SDK"
    except Exception as e:
        error_text = str(e)
        if "insufficient_quota" in error_text or "429" in error_text:
            openai_available = False
            bot_reply = run_groq_fallback(user_message, agent_key, context_messages)
            if bot_reply:
                return bot_reply, "Groq fallback"
            raise RuntimeError(
                "OpenAI quota/billing available nahi hai. Free fallback ke liye Groq key "
                "banayein aur `.env` mein `GROQ_API_KEY=...` add karke server restart karein."
            ) from e
        raise


def stream_event(event_type: str, **payload: str) -> str:
    """Return one newline-delimited JSON stream event."""
    return json.dumps({"type": event_type, **payload}) + "\n"


def stream_groq_reply(user_message: str, agent_key: str):
    """Yield a Groq fallback reply in browser-visible chunks."""
    if not groq_client:
        yield stream_event(
            "error",
            message=(
                "OpenAI quota/billing available nahi hai. Free streaming fallback ke liye "
                "`.env` mein `GROQ_API_KEY=...` add karke server restart karein."
            ),
        )
        return

    profile = AGENT_PROFILES[get_agent_key(agent_key)]
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": f"{profile['instructions']} {BASE_AGENT_INSTRUCTIONS}",
                },
                *model_context_messages(),
                {"role": "user", "content": user_message},
            ],
        )
        reply = response.choices[0].message.content or ""

        for word in reply.split(" "):
            yield stream_event("chunk", text=f"{word} ")
            time.sleep(0.015)

    except Exception as e:
        yield stream_event("error", message=f"Groq error: {str(e)}")


init_db()
current_session_id = ensure_default_session()
chat_history.extend(load_chat_history(MAX_HISTORY, current_session_id))

# ─────────────────────────────────────────
# HTML Template
# ─────────────────────────────────────────
# UI lives in templates/index.html, static/styles.css, and static/chat.js.


# ─────────────────────────────────────────
# Routes
# ─────────────────────────────────────────

@app.route('/')
def home():
    """Main chat page"""
    has_groq = bool(os.getenv("GROQ_API_KEY"))
    provider_label = "Online · OpenAI Agents SDK"
    footer_label = f"Powered by OpenAI Agents SDK · {MODEL}"

    if has_groq:
        provider_label = "Online · OpenAI Agents SDK + Groq fallback"
        footer_label = f"OpenAI: {MODEL} · Fallback: {GROQ_MODEL}"

    file_label = "No file attached"
    if attached_file["name"]:
        file_label = f"Attached: {attached_file['name']} ({attached_file['chars']} chars)"

    return render_template(
        "index.html",
        provider_label=provider_label,
        footer_label=footer_label,
        initial_messages=chat_history,
        file_label=file_label,
        sessions=list_sessions(),
        active_session_id=current_session_id,
    )


@app.errorhandler(413)
def file_too_large(_error):
    """Return JSON when an uploaded file is too large."""
    return jsonify({"error": "File 10MB se badi hai. Chhoti file upload karein."}), 413


@app.route('/upload', methods=['POST'])
def upload_file():
    """Attach a text file as context for future chat messages."""
    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "File select karein."}), 400

    filename = Path(uploaded.filename).name
    extension = Path(filename).suffix.lower()
    if not is_allowed_file(filename):
        return jsonify({
            "error": "Supported files: .txt, .md, .csv, .json, .py, .js, .html, .css, .pdf"
        }), 400

    raw = uploaded.read()
    if extension == ".pdf":
        try:
            text = extract_pdf_text(raw)
        except Exception as e:
            return jsonify({"error": f"PDF text extract nahi hua: {str(e)}"}), 400
    else:
        text = raw.decode("utf-8", errors="replace").strip()

    if not text:
        return jsonify({"error": "File empty hai ya readable text nahi mila."}), 400

    if len(text) > MAX_FILE_CHARS:
        text = text[:MAX_FILE_CHARS] + "\n\n[File truncated for context limit.]"

    summary = ""
    if extension == ".csv":
        try:
            summary = build_csv_summary(text)
        except Exception as e:
            summary = f"CSV auto-analysis failed: {str(e)}"
    elif extension == ".pdf":
        summary = f"PDF text extracted. Pages with readable text: {text.count('[Page ')}"

    attached_file.update({
        "name": filename,
        "content": text,
        "chars": len(text),
        "summary": summary,
    })

    return jsonify({
        "filename": filename,
        "chars": len(text),
        "preview": text[:300],
        "summary": summary,
    })


@app.route('/upload/clear', methods=['POST'])
def clear_upload():
    """Remove the attached file context."""
    attached_file.update({"name": "", "content": "", "chars": 0, "summary": ""})
    return jsonify({"status": "cleared"})


@app.route('/sessions')
def sessions():
    """Return all available chat sessions."""
    return jsonify({
        "sessions": list_sessions(),
        "active_session_id": current_session_id,
    })


@app.route('/search')
def search():
    """Search chat sessions and messages."""
    query = request.args.get("q", "").strip()
    return jsonify({
        "query": query,
        "results": search_chat(query),
    })


@app.route('/sessions/new', methods=['POST'])
def new_session():
    """Create a new empty chat session and switch to it."""
    global current_session_id
    title = (request.get_json(silent=True) or {}).get("title")
    current_session_id = create_session(title)
    chat_history.clear()
    attached_file.update({"name": "", "content": "", "chars": 0, "summary": ""})
    return jsonify({
        "status": "created",
        "active_session_id": current_session_id,
        "sessions": list_sessions(),
        "messages": chat_history,
    })


@app.route('/sessions/select', methods=['POST'])
def select_session():
    """Switch the active chat session."""
    global current_session_id
    data = request.get_json(silent=True) or {}
    try:
        session_id = int(data.get("session_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid session select karein."}), 400

    if not any(session["id"] == session_id for session in list_sessions()):
        return jsonify({"error": "Session nahi mili."}), 404

    current_session_id = session_id
    chat_history.clear()
    chat_history.extend(load_chat_history(MAX_HISTORY, current_session_id))
    attached_file.update({"name": "", "content": "", "chars": 0, "summary": ""})
    return jsonify({
        "status": "selected",
        "active_session_id": current_session_id,
        "sessions": list_sessions(),
        "messages": chat_history,
    })


@app.route('/sessions/rename', methods=['POST'])
def rename_active_session():
    """Rename the current chat session."""
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Session ka naam likhein."}), 400

    if not rename_session(current_session_id, title):
        return jsonify({"error": "Session rename nahi hui."}), 404

    return jsonify({
        "status": "renamed",
        "active_session_id": current_session_id,
        "sessions": list_sessions(),
    })


@app.route('/sessions/delete', methods=['POST'])
def delete_active_session():
    """Delete the current chat session and switch to another one."""
    global current_session_id
    current_session_id = delete_session(current_session_id)
    chat_history.clear()
    chat_history.extend(load_chat_history(MAX_HISTORY, current_session_id))
    attached_file.update({"name": "", "content": "", "chars": 0, "summary": ""})

    return jsonify({
        "status": "deleted",
        "active_session_id": current_session_id,
        "sessions": list_sessions(),
        "messages": chat_history,
    })


@app.route('/sessions/pin', methods=['POST'])
def pin_active_session():
    """Pin or unpin the current chat session."""
    data = request.get_json(silent=True) or {}
    pinned = bool(data.get("pinned"))

    if not set_session_pinned(current_session_id, pinned):
        return jsonify({"error": "Session update nahi hui."}), 404

    return jsonify({
        "status": "pinned" if pinned else "unpinned",
        "active_session_id": current_session_id,
        "sessions": list_sessions(),
    })


@app.route('/feedback', methods=['POST'])
def feedback():
    """Save thumbs up/down feedback for an assistant message."""
    data = request.get_json(silent=True) or {}
    try:
        message_id = int(data.get("message_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid message select karein."}), 400

    value = (data.get("feedback") or "").strip()
    if value not in {"up", "down", ""}:
        return jsonify({"error": "Feedback valid nahi hai."}), 400

    if not set_message_feedback(message_id, value):
        return jsonify({"error": "Feedback save nahi hua."}), 404

    return jsonify({"status": "saved", "message_id": message_id, "feedback": value})


@app.route('/message/edit', methods=['POST'])
def edit_message():
    """Edit a user message in place."""
    data = request.get_json(silent=True) or {}
    try:
        message_id = int(data.get("message_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid message select karein."}), 400

    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Message empty nahi ho sakta."}), 400

    if not update_user_message(message_id, content):
        return jsonify({"error": "Message update nahi hua."}), 404

    for message in chat_history:
        if message.get("id") == message_id and message.get("role") == "user":
            message["content"] = content
            break

    return jsonify({"status": "updated", "message_id": message_id, "content": content})


@app.route('/message/edit-regenerate', methods=['POST'])
def edit_and_regenerate_message():
    """Edit a user message and replace its existing assistant response."""
    data = request.get_json(silent=True) or {}
    try:
        user_message_id = int(data.get("user_message_id", 0))
        assistant_message_id = int(data.get("assistant_message_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid message select karein."}), 400

    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Message empty nahi ho sakta."}), 400
    if not user_message_id or not assistant_message_id:
        return jsonify({"error": "User aur assistant message IDs required hain."}), 400

    agent_key = get_agent_key(data.get("agent"))
    agent_label = AGENT_PROFILES[agent_key]["label"]

    if not update_user_message(user_message_id, content):
        return jsonify({"error": "User message update nahi hua."}), 404

    for message in chat_history:
        if message.get("id") == user_message_id and message.get("role") == "user":
            message["content"] = content
            message["agent"] = agent_label
            break

    try:
        context = model_context_messages(exclude_ids={user_message_id, assistant_message_id})
        bot_reply, provider_label = generate_reply(content, agent_key, context)
    except Exception as e:
        return jsonify({
            "error": f"Response regenerate nahi hua: {str(e)}",
            "provider": "Error",
            "agent": agent_label,
        }), 500

    if not update_assistant_message(assistant_message_id, bot_reply, agent_label, provider_label):
        return jsonify({"error": "Assistant response update nahi hua."}), 404

    for message in chat_history:
        if message.get("id") == assistant_message_id and message.get("role") == "assistant":
            message["content"] = bot_reply
            message["agent"] = agent_label
            message["provider"] = provider_label
            message["feedback"] = ""
            break

    return jsonify({
        "status": "updated",
        "response": bot_reply,
        "provider": provider_label,
        "agent": agent_label,
        "message_id": assistant_message_id,
        "user_message_id": user_message_id,
    })


@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages with the OpenAI Agents SDK."""
    global openai_available
    user_message = request.json.get('message', '').strip()
    agent_key = get_agent_key(request.json.get('agent'))
    agent_label = AGENT_PROFILES[agent_key]["label"]

    if not user_message:
        return jsonify({"response": "Kuch likho please!"}), 400

    if is_stats_request(user_message):
        bot_reply = build_chat_stats()
        ids = save_turn(user_message, bot_reply, agent_label, "Local stats")
        return jsonify({
            "response": bot_reply,
            "provider": "Local stats",
            "agent": agent_label,
            "message_id": ids["assistant_message_id"],
            "user_message_id": ids["user_message_id"],
        })

    if not openai_available:
        bot_reply = run_groq_fallback(user_message, agent_key)
        if bot_reply:
            ids = save_turn(user_message, bot_reply, agent_label, "Groq fallback")
            return jsonify({
                "response": bot_reply,
                "provider": "Groq fallback",
                "agent": agent_label,
                "message_id": ids["assistant_message_id"],
                "user_message_id": ids["user_message_id"],
            })

        return jsonify({
            "response": (
                "OPENAI_API_KEY missing hai. Free fallback ke liye `.env` mein GROQ_API_KEY "
                "add karein, phir Flask server restart karein."
            ),
            "provider": "Setup needed",
            "agent": agent_label,
        }), 500

    try:
        agent_input = [
            *model_context_messages(),
            {"role": "user", "content": user_message},
        ]
        result = Runner.run_sync(assistant_agents[agent_key], agent_input)
        bot_reply = result.final_output

        ids = save_turn(user_message, bot_reply, agent_label, "OpenAI Agents SDK")
        return jsonify({
            "response": bot_reply,
            "provider": "OpenAI Agents SDK",
            "agent": agent_label,
            "message_id": ids["assistant_message_id"],
            "user_message_id": ids["user_message_id"],
        })

    except Exception as e:
        error_text = str(e)
        if "insufficient_quota" in error_text or "429" in error_text:
            openai_available = False
            bot_reply = run_groq_fallback(user_message, agent_key)
            if bot_reply:
                ids = save_turn(user_message, bot_reply, agent_label, "Groq fallback")
                return jsonify({
                    "response": bot_reply,
                    "provider": "Groq fallback",
                    "agent": agent_label,
                    "message_id": ids["assistant_message_id"],
                    "user_message_id": ids["user_message_id"],
                })

            return jsonify({
                "response": (
                    "OpenAI quota/billing available nahi hai. Free fallback ke liye Groq key "
                    "banayein aur `.env` mein `GROQ_API_KEY=...` add karke server restart karein."
                ),
                "provider": "Setup needed",
                "agent": agent_label,
            }), 500

        return jsonify({
            "response": f"Error: {str(e)}",
            "provider": "Error",
            "agent": agent_label,
        }), 500


@app.route('/chat/stream', methods=['POST'])
def chat_stream():
    """Stream chat replies to the browser."""
    global openai_available
    data = request.get_json(silent=True) or {}
    user_message = data.get('message', '').strip()
    agent_key = get_agent_key(data.get('agent'))
    agent_label = AGENT_PROFILES[agent_key]["label"]

    if not user_message:
        return Response(
            stream_event("error", message="Kuch likho please!"),
            mimetype="application/x-ndjson",
        )

    @stream_with_context
    def generate():
        global openai_available
        provider_label = "OpenAI Agents SDK"
        full_reply = ""

        yield stream_event("meta", provider=provider_label, agent=agent_label)

        if is_stats_request(user_message):
            provider_label = "Local stats"
            yield stream_event("meta", provider=provider_label, agent=agent_label)
            full_reply = build_chat_stats()

            for word in full_reply.split(" "):
                yield stream_event("chunk", text=f"{word} ")
                time.sleep(0.015)

            ids = save_turn(user_message, full_reply, agent_label, provider_label)
            yield stream_event(
                "done",
                provider=provider_label,
                agent=agent_label,
                message_id=str(ids["assistant_message_id"]),
                user_message_id=str(ids["user_message_id"]),
            )
            return

        if not openai_available:
            provider_label = "Groq fallback"
            yield stream_event("meta", provider=provider_label, agent=agent_label)
            for event in stream_groq_reply(user_message, agent_key):
                data = json.loads(event)
                if data["type"] == "chunk":
                    full_reply += data["text"]
                yield event

            if full_reply:
                ids = save_turn(user_message, full_reply, agent_label, provider_label)
                yield stream_event(
                    "done",
                    provider=provider_label,
                    agent=agent_label,
                    message_id=str(ids["assistant_message_id"]),
                    user_message_id=str(ids["user_message_id"]),
                )
            return

        try:
            agent_input = [
                *model_context_messages(),
                {"role": "user", "content": user_message},
            ]
            result = Runner.run_sync(assistant_agents[agent_key], agent_input)
            full_reply = result.final_output

            for word in full_reply.split(" "):
                yield stream_event("chunk", text=f"{word} ")

            ids = save_turn(user_message, full_reply, agent_label, provider_label)
            yield stream_event(
                "done",
                provider=provider_label,
                agent=agent_label,
                message_id=str(ids["assistant_message_id"]),
                user_message_id=str(ids["user_message_id"]),
            )

        except Exception as e:
            error_text = str(e)
            if "insufficient_quota" in error_text or "429" in error_text:
                openai_available = False
                provider_label = "Groq fallback"
                yield stream_event("meta", provider=provider_label, agent=agent_label)
                full_reply = ""

                for event in stream_groq_reply(user_message, agent_key):
                    data = json.loads(event)
                    if data["type"] == "chunk":
                        full_reply += data["text"]
                    yield event

                if full_reply:
                    ids = save_turn(user_message, full_reply, agent_label, provider_label)
                    yield stream_event(
                        "done",
                        provider=provider_label,
                        agent=agent_label,
                        message_id=str(ids["assistant_message_id"]),
                        user_message_id=str(ids["user_message_id"]),
                    )
                return

            yield stream_event("error", message=f"Error: {error_text}")

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route('/export')
def export_chat():
    """Download the full chat history as a text file."""
    rows = load_all_chat_messages(current_session_id)
    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "OpenAI Agent SDK Assistant - Chat Export",
        f"Exported at: {exported_at}",
        "=" * 48,
        "",
    ]

    if not rows:
        lines.append("No chat messages yet.")
    else:
        for row in rows:
            role = "User" if row["role"] == "user" else "Assistant"
            meta = []
            if row["agent"]:
                meta.append(f"Agent: {row['agent']}")
            if row["provider"]:
                meta.append(f"Provider: {row['provider']}")

            lines.append(f"[{row['created_at']}] {role}")
            if meta:
                lines.append(" | ".join(meta))
            lines.append(row["content"])
            lines.append("-" * 48)

    buffer = io.BytesIO("\n".join(lines).encode("utf-8"))
    filename = f"chat-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="text/plain",
    )


@app.route('/clear', methods=['POST'])
def clear():
    """Clear chat history"""
    chat_history.clear()
    clear_messages(current_session_id)
    return jsonify({"status": "cleared"})


@app.route('/analytics')
def analytics():
    """Chat Analytics using NumPy + Pandas + Matplotlib"""
    if not chat_history:
        return "<h2 style='font-family:sans-serif;text-align:center;margin-top:50px;color:#333'>Pehle kuch chat karo! 😊<br><br><a href='/'>← Wapas Jao</a></h2>"

    # ── Pandas: DataFrame banao ──
    df = pd.DataFrame(chat_history)
    df['length'] = df['content'].apply(len)

    user_msgs = df[df['role'] == 'user']
    bot_msgs  = df[df['role'] == 'assistant']

    # ── NumPy: Stats nikalo ──
    avg_user_len = int(np.mean(user_msgs['length'])) if len(user_msgs) > 0 else 0
    avg_bot_len  = int(np.mean(bot_msgs['length']))  if len(bot_msgs) > 0 else 0
    total_msgs   = len(df)

    # ── Most Common Words ──
    all_words = ' '.join(user_msgs['content']).lower().split()
    stop_words = {'the','a','an','is','in','it','of','and','to','i','you','me','my',
                  'this','that','what','how','can','do','was','are','for','on','with'}
    words = [w for w in all_words if w not in stop_words and len(w) > 2]
    top_words = Counter(words).most_common(5)

    # ── Matplotlib: Graphs banao ──
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    fig.patch.set_facecolor('#13131a')

    axes[0].bar(['User', 'Bot'], [len(user_msgs), len(bot_msgs)],
                color=['#7c6cfc', '#fc6cb4'], width=0.5)
    axes[0].set_title('Messages Count', color='white', pad=10)
    axes[0].set_facecolor('#1a1a28')
    axes[0].tick_params(colors='white')
    for spine in axes[0].spines.values():
        spine.set_edgecolor('#1e1e2e')

    axes[1].bar(['User Avg', 'Bot Avg'], [avg_user_len, avg_bot_len],
                color=['#7c6cfc', '#fc6cb4'], width=0.5)
    axes[1].set_title('Avg Message Length', color='white', pad=10)
    axes[1].set_facecolor('#1a1a28')
    axes[1].tick_params(colors='white')
    for spine in axes[1].spines.values():
        spine.set_edgecolor('#1e1e2e')

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor='#13131a', dpi=120)
    buf.seek(0)
    graph = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    words_html = ''.join([
        f'<span style="background:#7c6cfc22;color:#7c6cfc;padding:5px 12px;border-radius:20px;margin:4px;display:inline-block;font-size:13px">{w} ({c})</span>'
        for w, c in top_words
    ]) or '<p style="color:#6b6b80">Kafi messages nahi hain!</p>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Analytics</title>
        <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Sora', sans-serif; background: #0a0a0f; color: #e8e8f0; padding: 40px 20px; }}
            .container {{ max-width: 900px; margin: 0 auto; }}
            h1 {{ text-align: center; margin-bottom: 30px; font-size: 28px; }}
            .accent {{ background: linear-gradient(135deg, #7c6cfc, #fc6cb4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
            .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }}
            .card {{ background: #13131a; border: 1px solid #1e1e2e; border-radius: 16px; padding: 24px; text-align: center; }}
            .card h2 {{ font-size: 40px; color: #7c6cfc; margin-bottom: 6px; }}
            .card p {{ color: #6b6b80; font-size: 13px; }}
            .section {{ background: #13131a; border: 1px solid #1e1e2e; border-radius: 16px; padding: 24px; margin-bottom: 20px; }}
            .section h3 {{ margin-bottom: 16px; color: #7c6cfc; font-size: 16px; }}
            img {{ width: 100%; border-radius: 12px; }}
            .back {{ display: inline-block; margin-top: 10px; color: #7c6cfc; text-decoration: none; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 <span class="accent">Chat Analytics</span></h1>

            <div class="cards">
                <div class="card"><h2>{total_msgs}</h2><p>Total Messages</p></div>
                <div class="card"><h2>{len(user_msgs)}</h2><p>User Messages</p></div>
                <div class="card"><h2>{avg_bot_len}</h2><p>Bot Avg Length</p></div>
            </div>

            <div class="section">
                <h3>📈 Charts (Matplotlib + NumPy)</h3>
                <img src="data:image/png;base64,{graph}" alt="Charts">
            </div>

            <div class="section">
                <h3>🔤 Top Words (Pandas)</h3>
                {words_html}
            </div>

            <a class="back" href="/">← Return to the Chat</a>
        </div>
    </body>
    </html>
    """


# ─────────────────────────────────────────
# Run
# ─────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
