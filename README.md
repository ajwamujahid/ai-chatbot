# OpenAI Agents SDK Flask Chatbot

Ye project Flask par bana simple chatbot hai jo OpenAI Agents SDK use karta hai.

## Features

- OpenAI Agents SDK `Agent` + `Runner`
- Groq fallback when OpenAI API quota is unavailable
- Agent selector: General, Coding, Study, and Business
- Provider badges on assistant replies
- Streaming replies in the chat UI
- File upload Q&A for text/code/CSV/PDF files
- CSV auto analytics with rows, columns, missing values, and numeric summaries
- Export chat history as a `.txt` file
- Multiple chat sessions with a session switcher and New Chat button
- Auto-generated session titles from the first message
- Custom function tool: `get_chat_stats`
- SQLite chat history that survives server restarts
- Analytics page with Pandas, NumPy, and Matplotlib

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env.example` ko follow karke `.env` mein apni key set karein:

```bash
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4.1-mini
GROQ_API_KEY=gsk-your-groq-api-key
GROQ_MODEL=llama-3.3-70b-versatile
```

OpenAI API quota/billing available na ho to app automatically Groq fallback use karega, agar `GROQ_API_KEY` set ho.

## Run

```bash
python app.py
```

Phir browser mein open karein:

```text
http://127.0.0.1:5000
```

## Project Structure

```text
app.py                  Flask routes and agent orchestration
templates/index.html    Chat UI HTML
static/styles.css       Chat UI styling
static/chat.js          Browser chat, streaming, upload logic
services/storage.py     SQLite chat sessions and history helpers
services/file_context.py File, CSV, and PDF parsing helpers
```
