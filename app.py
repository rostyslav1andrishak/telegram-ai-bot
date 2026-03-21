import requests
import sqlite3
from flask import Flask, request

TOKEN = "8658895357:AAGCcvoiqwQGPCgpuXWAmSeQiM3IDHq4sRc"
OPENAI_API_KEY = "OPENAI_API_KEY"

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

# --- ФІНАНСИ ---
def get_finance_summary(user_id):
    cursor.execute("SELECT value FROM facts WHERE user_id=? AND category='фінанси'", (user_id,))
    rows = cursor.fetchall()

    total = 0
    for r in rows:
        try:
            total += int(''.join(filter(str.isdigit, r[0])))
        except:
            pass

    return f"💰 Загальні витрати: {total}"

# --- SMART MEMORY ---
def analyze_and_save(user_id, text):
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": """
Виділи важливі факти про користувача.

Формат JSON:
{category: {key: value}}

Категорії:
- фінанси
- плани
- особисте
- робота

Якщо нічого → {}
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

    if "скільки я витратив" in message.lower():
        return get_finance_summary(user_id)

    history = get_history(user_id)
    memory = get_memory(user_id)

    messages = [
        {"role": "system", "content": f"""
Ти персональний AI користувача.

Ти:
- пам’ятаєш історію
- аналізуєш
- допомагаєш

Ось памʼять:
{memory}
"""}
    ] + history + [
        {"role": "user", "content": message}
    ]

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4o-mini",
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
