"""
AI Chatbot - Flask Application
Clean, readable code with chat history + analytics
"""

from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
from groq import Groq
from collections import Counter
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Server pe graph banana
import matplotlib.pyplot as plt
import io
import base64
import os

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
load_dotenv()

app = Flask(__name__)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "llama-3.3-70b-versatile"
MAX_HISTORY = 20  # kitne messages yaad rakhe

# In-memory chat history
chat_history = []

# ─────────────────────────────────────────
# HTML Template
# ─────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Chatbot</title>
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg:        #0a0a0f;
            --surface:   #13131a;
            --border:    #1e1e2e;
            --accent:    #7c6cfc;
            --accent2:   #fc6cb4;
            --text:      #e8e8f0;
            --text-muted:#6b6b80;
            --user-bg:   linear-gradient(135deg, #7c6cfc, #fc6cb4);
            --bot-bg:    #1a1a28;
            --radius:    16px;
            --shadow:    0 8px 32px rgba(124,108,252,0.15);
        }

        body {
            font-family: 'Sora', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background-image:
                radial-gradient(ellipse at 20% 50%, rgba(124,108,252,0.08) 0%, transparent 60%),
                radial-gradient(ellipse at 80% 20%, rgba(252,108,180,0.06) 0%, transparent 60%);
        }

        .chat-container {
            width: 100%;
            max-width: 780px;
            height: 90vh;
            max-height: 760px;
            display: flex;
            flex-direction: column;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 24px;
            overflow: hidden;
            box-shadow: var(--shadow);
        }

        .chat-header {
            padding: 20px 28px;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .avatar {
            width: 44px; height: 44px;
            background: var(--user-bg);
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 20px; flex-shrink: 0;
        }

        .header-info h1 { font-size: 17px; font-weight: 600; color: var(--text); }

        .status {
            display: flex; align-items: center; gap: 6px;
            font-size: 12px; color: var(--text-muted); margin-top: 2px;
        }

        .status-dot {
            width: 7px; height: 7px;
            background: #4ade80; border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        .header-btns { margin-left: auto; display: flex; gap: 8px; }

        .header-btns a, .clear-btn {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 8px 14px;
            border-radius: 10px;
            font-size: 12px; cursor: pointer;
            font-family: 'Sora', sans-serif;
            transition: all 0.2s;
            text-decoration: none;
        }

        .header-btns a:hover, .clear-btn:hover {
            border-color: var(--accent);
            color: var(--accent);
        }

        #chat-box {
            flex: 1; overflow-y: auto;
            padding: 24px 28px;
            display: flex; flex-direction: column;
            gap: 16px; scroll-behavior: smooth;
        }

        #chat-box::-webkit-scrollbar { width: 4px; }
        #chat-box::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

        .message { display: flex; gap: 10px; animation: fadeSlide 0.3s ease; }

        @keyframes fadeSlide {
            from { opacity: 0; transform: translateY(10px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        .message.user { flex-direction: row-reverse; }

        .msg-avatar {
            width: 32px; height: 32px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 14px; flex-shrink: 0; margin-top: 2px;
        }

        .message.bot .msg-avatar { background: var(--bot-bg); border: 1px solid var(--border); }
        .message.user .msg-avatar { background: var(--user-bg); }

        .msg-content { max-width: 72%; }

        .msg-bubble {
            padding: 12px 16px; border-radius: var(--radius);
            font-size: 14px; line-height: 1.6; word-break: break-word;
        }

        .message.bot .msg-bubble {
            background: var(--bot-bg); border: 1px solid var(--border);
            border-bottom-left-radius: 4px; color: var(--text);
        }

        .message.user .msg-bubble {
            background: var(--user-bg);
            border-bottom-right-radius: 4px; color: white;
        }

        .msg-time { font-size: 11px; color: var(--text-muted); margin-top: 4px; padding: 0 4px; }
        .message.user .msg-time { text-align: right; }

        .typing-indicator {
            display: none; gap: 5px; padding: 14px 16px;
            background: var(--bot-bg); border: 1px solid var(--border);
            border-radius: var(--radius); border-bottom-left-radius: 4px;
            width: fit-content;
        }

        .typing-indicator.show { display: flex; }

        .typing-dot {
            width: 7px; height: 7px;
            background: var(--text-muted); border-radius: 50%;
            animation: typing 1.2s infinite;
        }

        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes typing {
            0%, 100% { transform: translateY(0); opacity: 0.4; }
            50% { transform: translateY(-5px); opacity: 1; }
        }

        .input-area {
            padding: 20px 28px; border-top: 1px solid var(--border);
            display: flex; gap: 12px; align-items: flex-end;
        }

        #user-input {
            flex: 1; background: var(--bg);
            border: 1px solid var(--border); border-radius: 14px;
            padding: 14px 18px; color: var(--text);
            font-size: 14px; font-family: 'Sora', sans-serif;
            resize: none; outline: none;
            transition: border-color 0.2s;
            min-height: 52px; max-height: 140px;
        }

        #user-input::placeholder { color: var(--text-muted); }
        #user-input:focus { border-color: var(--accent); }

        #send-btn {
            width: 52px; height: 52px;
            background: var(--user-bg); border: none;
            border-radius: 14px; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            transition: all 0.2s; flex-shrink: 0;
        }

        #send-btn:hover { transform: scale(1.05); opacity: 0.9; }
        #send-btn:active { transform: scale(0.95); }
        #send-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
        #send-btn svg { width: 20px; height: 20px; }

        .footer-text {
            text-align: center; font-size: 11px;
            color: var(--text-muted); padding-bottom: 8px;
            font-family: 'JetBrains Mono', monospace;
        }
    </style>
</head>
<body>
<div class="chat-container">

    <!-- Header -->
    <div class="chat-header">
        <div class="avatar">🤖</div>
        <div class="header-info">
            <h1>AI Assistant</h1>
            <div class="status">
                <div class="status-dot"></div>
                Online · Llama 3.3 70B
            </div>
        </div>
        <div class="header-btns">
            <a href="/analytics">📊 Analytics</a>
            <button class="clear-btn" onclick="clearChat()">Clear Chat</button>
        </div>
    </div>

    <!-- Messages -->
    <div id="chat-box">
        <div class="message bot">
            <div class="msg-avatar">🤖</div>
            <div class="msg-content">
                <div class="msg-bubble">Assalam o Alaikum! Main aapka AI Assistant hun. Kuch bhi poochein! 😊</div>
                <div class="msg-time">Just now</div>
            </div>
        </div>

        <div class="message bot" id="typing-wrapper" style="display:none">
            <div class="msg-avatar">🤖</div>
            <div class="typing-indicator show">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    </div>

    <!-- Input -->
    <div class="input-area">
        <textarea id="user-input" placeholder="Yahan likho..." rows="1"
            onkeydown="handleKey(event)"
            oninput="autoResize(this)"></textarea>
        <button id="send-btn" onclick="sendMessage()">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
        </button>
    </div>
    <div class="footer-text">Powered by Groq · LLaMA 3.3</div>
</div>

<script>
    function getTime() {
        return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    function autoResize(el) {
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 140) + 'px';
    }

    function handleKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    function scrollToBottom() {
        const box = document.getElementById('chat-box');
        box.scrollTop = box.scrollHeight;
    }

    function addMessage(text, role) {
        const box = document.getElementById('chat-box');
        const typing = document.getElementById('typing-wrapper');
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.innerHTML = `
            <div class="msg-avatar">${role === 'user' ? '👤' : '🤖'}</div>
            <div class="msg-content">
                <div class="msg-bubble">${text.replace(/\\n/g, '<br>')}</div>
                <div class="msg-time">${getTime()}</div>
            </div>`;
        box.insertBefore(div, typing);
        scrollToBottom();
    }

    async function sendMessage() {
        const input = document.getElementById('user-input');
        const btn = document.getElementById('send-btn');
        const message = input.value.trim();
        if (!message) return;

        addMessage(message, 'user');
        input.value = '';
        input.style.height = 'auto';

        btn.disabled = true;
        document.getElementById('typing-wrapper').style.display = 'flex';
        scrollToBottom();

        try {
            const res = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });
            const data = await res.json();
            document.getElementById('typing-wrapper').style.display = 'none';
            addMessage(data.response, 'bot');
        } catch (e) {
            document.getElementById('typing-wrapper').style.display = 'none';
            addMessage('Kuch masla ho gaya! Dobara try karo.', 'bot');
        }

        btn.disabled = false;
        input.focus();
    }

    async function clearChat() {
        await fetch('/clear', { method: 'POST' });
        const box = document.getElementById('chat-box');
        Array.from(box.children).forEach(child => {
            if (child.id !== 'typing-wrapper') child.remove();
        });
        addMessage('Chat clear ho gaya! 😊', 'bot');
    }
</script>
</body>
</html>
"""


# ─────────────────────────────────────────
# Routes
# ─────────────────────────────────────────

@app.route('/')
def home():
    """Main chat page"""
    return render_template_string(HTML)


@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages with history"""
    user_message = request.json.get('message', '').strip()
    if not user_message:
        return jsonify({"response": "Kuch likho please!"}), 400

    chat_history.append({"role": "user", "content": user_message})

    if len(chat_history) > MAX_HISTORY:
        chat_history.pop(0)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant. Be concise and friendly."},
                *chat_history
            ]
        )
        bot_reply = response.choices[0].message.content
        chat_history.append({"role": "assistant", "content": bot_reply})
        return jsonify({"response": bot_reply})

    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"}), 500


@app.route('/clear', methods=['POST'])
def clear():
    """Clear chat history"""
    chat_history.clear()
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

            <a class="back" href="/">← Wapas Chat Pe</a>
        </div>
    </body>
    </html>
    """


# ─────────────────────────────────────────
# Run
# ─────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)