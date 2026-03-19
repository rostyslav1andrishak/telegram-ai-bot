import requests
from flask import Flask, request

TOKEN = "8658895357:AAEAMx-QoDfk2Cl3q4NlveBM36o1LoJzvnA"
OPENROUTER_API_KEY = "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"

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
                {"role": "system", "content": "Ти AI помічник"},
                {"role": "user", "content": message}
            ]
        }
    )

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

    try:
        data = response.json()
    except:
        return "Помилка: не JSON відповідь"

    print("FULL RESPONSE:", data)

    if "choices" not in data:
        return f"Помилка AI: {data}"

    return data["choices"][0]["message"]["content"]


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    message = data.get("message") or data.get("edited_message")
    if not message:
        return "ok"

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text")

    if text:
        reply = ask_ai(text)
        send_message(chat_id, reply)

    return "ok"


def send_message(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        }
    )


app.run(host="0.0.0.0", port=10000)
