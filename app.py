import requests
from flask import Flask, request

TOKEN = 8658895357:AAF9ZSFv4Fe18yU4KfE9NeAqsxNCxSOnvho
OPENROUTER_API_KEY = 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

app = Flask(__name__)

def ask_ai(message):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "mistralai/mistral-7b-instruct",
            "messages": [
                {"role": "system", "content": "Ти мій AI помічник. Допомагаєш з продажами, авто і пишеш чеською."},
                {"role": "user", "content": message}
            ]
        }
    )
    return response.json()["choices"][0]["message"]["content"]

@app.route("/", methods=["POST"])
def webhook():
    data = request.json
    message = data.get("message", {})
    
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text")

    if text:
        reply = ask_ai(text)
        send_message(chat_id, reply)

    return "ok"

def send_message(chat_id, text):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

app.run(host="0.0.0.0", port=10000)
