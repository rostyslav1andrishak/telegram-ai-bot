import requests
import sqlite3
from flask import Flask, request

TOKEN = "8658895357:AAGCcvoiqwQGPCgpuXWAmSeQiM3IDHq4sRc"
OPENROUTER_API_KEY = "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"

app = Flask(__name__)

# --- БАЗА ---
conn = sqlite3.connect("memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS facts (
    user_id INTEGER,
    category TEXT,
    key TEXT,
    value TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    user_id INTEGER,
    role TEXT,
    text TEXT
)
""")

conn.commit()

# --- TELEGRAM ---
def send_message(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

# --- HISTORY ---
def save_message(user_id, role, text):
    cursor.execute("INSERT INTO messages VALUES (?, ?, ?)", (user_id, role, text))
    conn.commit()

def get_history(user_id, limit=10):
    cursor.execute("""
        SELECT role, text FROM messages
        WHERE user_id=? ORDER BY rowid DESC LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# --- MEMORY ---
def get_memory(user_id):
    cursor.execute("SELECT category, key, value FROM facts WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()

    text = ""
    for c, k, v in rows:
        text += f"[{c}] {k}: {v}\n"

    return text

# --- SMART MEMORY ---
def analyze_and_save(user_id, text):
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": """
Виділи тільки ВАЖЛИВІ факти про користувача.

НЕ зберігай:
- випадкові фрази
- дрібниці

Зберігай:
- цілі
- гроші
- звички
- плани

Формат JSON:
{category: {key: value}}

Якщо нічого важливого → {}
"""},
                    {"role": "user", "content": text}
                ]
            }
        )

        data = response.json()

        if "choices" not in data:
            return

        import json
        content = data["choices"][0]["message"]["content"]
        facts = json.loads(content)

        for category, values in facts.items():
            for k, v in values.items():

                # 🔥 ОНОВЛЕННЯ (як у людини)
                cursor.execute("""
                DELETE FROM facts 
                WHERE user_id=? AND category=? AND key=?
                """, (user_id, category, k))

                cursor.execute("""
                INSERT INTO facts VALUES (?, ?, ?, ?)
                """, (user_id, category, k, v))

        conn.commit()

    except:
        pass

# --- AI ---
def ask_ai(user_id, message):
    history = get_history(user_id)
    memory = get_memory(user_id)

    messages = [
        {"role": "system", "content": f"""
Ти персональний AI користувача.

Ти:
- пам’ятаєш його історію
- аналізуєш поведінку
- даєш поради
- порівнюєш минуле і теперішнє

Якщо бачиш закономірності — скажи про них.
Якщо можеш допомогти — запропонуй.

Ось дані:
{memory}
"""}
    ] + history + [
        {"role": "user", "content": message}
    ]

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/gpt-4o-mini",
            "messages": messages
        }
    )

    data = response.json()

    if "choices" not in data:
        return f"Помилка AI: {data}"

    return data["choices"][0]["message"]["content"]

# --- WEBHOOK ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    message = data.get("message") or data.get("edited_message")
    if not message:
        return "ok"

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    save_message(chat_id, "user", text)
    analyze_and_save(chat_id, text)

    reply = ask_ai(chat_id, text)

    save_message(chat_id, "assistant", reply)
    send_message(chat_id, reply)

    return "ok"

app.run(host="0.0.0.0", port=10000)
