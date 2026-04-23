from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
from groq import Groq
import os

load_dotenv()
app = Flask(__name__)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>My AI Chatbot</title>
    <style>
        body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; background: #f0f2f5; }
        h1 { color: #1a73e8; text-align: center; }
        #chat-box { background: white; height: 400px; overflow-y: auto; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .user-msg { background: #1a73e8; color: white; padding: 10px 15px; border-radius: 15px; margin: 5px 0; text-align: right; }
        .bot-msg { background: #e8eaed; padding: 10px 15px; border-radius: 15px; margin: 5px 0; }
        #input-area { display: flex; gap: 10px; }
        #user-input { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }
        button { background: #1a73e8; color: white; border: none; padding: 12px 25px; border-radius: 8px; cursor: pointer; font-size: 16px; }
    </style>
</head>
<body>
    <h1>🤖 My AI Chatbot</h1>
    <div id="chat-box">
        <div class="bot-msg">Assalam o Alaikum! Kuch bhi poochein! 😊</div>
    </div>
    <div id="input-area">
        <input type="text" id="user-input" placeholder="Yahan likho..." onkeypress="if(event.key==='Enter') sendMessage()">
        <button onclick="sendMessage()">Send 🚀</button>
    </div>
    <script>
        async function sendMessage() {
            const input = document.getElementById('user-input');
            const chatBox = document.getElementById('chat-box');
            const message = input.value.trim();
            if (!message) return;
            chatBox.innerHTML += `<div class="user-msg">${message}</div>`;
            input.value = '';
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message })
                });
                const data = await response.json();
                chatBox.innerHTML += `<div class="bot-msg">${data.response}</div>`;
            } catch(e) {
                chatBox.innerHTML += `<div class="bot-msg">Error: Dobara try karo!</div>`;
            }
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message')
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": user_message}]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})

if __name__ == '__main__':
    app.run(debug=True)