import requests
import sqlite3
from flask import Flask, request
import os
import json
from datetime import datetime, timedelta
import threading
import time

TOKEN = "8658895357:AAGCcvoiqwQGPCgpuXWAmSeQiM3IDHq4sRc"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

# --- БАЗА ---
conn = sqlite3.connect("memory.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
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
        text TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        user_id INTEGER,
        text TEXT,
        remind_time DATETIME,
        priority TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mood (
        user_id INTEGER,
        mood TEXT,
        created DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        user_id INTEGER,
        text TEXT,
        status TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS insights (
        user_id INTEGER,
        text TEXT,
        created DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()

init_db()

# --- TELEGRAM ---
def send_message(chat_id, text):
    if not text:
        return
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]}
    )

def send_photo(chat_id, url, caption=""):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
        json={"chat_id": chat_id, "photo": url, "caption": caption}
    )

def send_video(chat_id, url, caption=""):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendVideo",
        json={"chat_id": chat_id, "video": url, "caption": caption}
    )

def send_document(chat_id, url, caption=""):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendDocument",
        json={"chat_id": chat_id, "document": url, "caption": caption}
    )

# --- HISTORY ---
def save_message(user_id, role, text):
    cursor.execute(
        "INSERT INTO messages (user_id, role, text) VALUES (?, ?, ?)",
        (user_id, role, text)
    )
    conn.commit()

def get_history(user_id, limit=10):
    cursor.execute("""
        SELECT role, text FROM messages
        WHERE user_id=? ORDER BY timestamp DESC LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# --- MEMORY ---
def get_memory(user_id):
    cursor.execute("SELECT category, key, value FROM facts WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    return "\n".join([f"[{c}] {k}: {v}" for c, k, v in rows]) if rows else "немає даних"

# --- MOOD ---
def detect_mood(user_id, text):
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
                    {"role": "system", "content": "happy, sad, stressed, neutral"},
                    {"role": "user", "content": text}
                ]
            }
        )

        data = response.json()
        mood = data["choices"][0]["message"]["content"]

        cursor.execute(
            "INSERT INTO mood (user_id, mood) VALUES (?, ?)",
            (user_id, mood)
        )
        conn.commit()
    except:
        pass

# --- SMART MEMORY ---
def analyze_and_save(user_id, text):
    if len(text) < 8:
        return

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
                    {"role": "system", "content": "JSON only or {}"},
                    {"role": "user", "content": text}
                ]
            }
        )

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        try:
            facts = json.loads(content)
        except:
            return

        for category, values in facts.items():
            for k, v in values.items():
                cursor.execute("""
                DELETE FROM facts WHERE user_id=? AND category=? AND key=?
                """, (user_id, category, k))

                cursor.execute("""
                INSERT INTO facts VALUES (?, ?, ?, ?)
                """, (user_id, category, k, v))

        conn.commit()

    except:
        pass

# --- REMINDERS ---
def check_reminders():
    now = datetime.now()

    cursor.execute("""
    SELECT rowid, user_id, text, priority FROM reminders
    WHERE remind_time <= ?
    """, (now,))

    for row_id, user_id, text, priority in cursor.fetchall():
        emoji = "🔥" if priority == "high" else "🔔"
        send_message(user_id, f"{emoji} Нагадування:\n{text}")

        cursor.execute("DELETE FROM reminders WHERE rowid=?", (row_id,))

    conn.commit()

# --- COMMANDS ---
def handle_commands(chat_id, text):
    t = text.lower()

    # REMINDER
    if "нагадай" in t or "запам" in t:
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
                        {"role": "system", "content": "JSON reminder"},
                        {"role": "user", "content": text}
                    ]
                }
            )

            parsed = json.loads(response.json()["choices"][0]["message"]["content"])
            event_time = datetime.strptime(parsed["datetime"], "%Y-%m-%d %H:%M")

            for h in parsed["reminders"]:
                remind_time = event_time - timedelta(hours=h)

                cursor.execute(
                    "INSERT INTO reminders VALUES (?, ?, ?, ?)",
                    (chat_id, parsed["text"], remind_time, parsed["priority"])
                )

            conn.commit()
            send_message(chat_id, "🔥 Запамʼятала!")

        except:
            send_message(chat_id, "❌ Помилка")

        return True

    # GOAL
    if t.startswith("ціль"):
        goal = text.replace("ціль", "").strip()
        cursor.execute("INSERT INTO goals VALUES (?, ?, ?)", (chat_id, goal, "active"))
        conn.commit()
        send_message(chat_id, f"🎯 Ціль: {goal}")
        return True

    return False

# --- AI ---
def ask_ai(user_id, message):

    history = get_history(user_id)
    memory = get_memory(user_id)

    messages = [{
    "role": "system",
    "content": f"""
Ти персональний AI-асистент з памʼяттю.

ТИ:
- памʼятаєш всі попередні повідомлення
- аналізуєш користувача
- маєш доступ до історії
- поводишся як живий помічник

ТИ НІКОЛИ НЕ КАЖЕШ:
"я не памʼятаю"
"я не маю доступу"

Навіть якщо мало даних — поводься як той, хто памʼятає.

ПАМʼЯТЬ:
{memory}

ІСТОРІЯ:
{history}

Будь розумним, живим і корисним.
"""
}]

    messages += history
    messages.append({"role": "user", "content": message})

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={"model": "gpt-4o-mini", "messages": messages}
        )

        return response.json()["choices"][0]["message"]["content"]

    except:
        return "Помилка AI"

# --- WEBHOOK ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message")

    if not message:
        return "ok"

    chat_id = message["chat"]["id"]

    if "text" in message:
        text = message["text"]

        if handle_commands(chat_id, text):
            return "ok"

    else:
        text = "Не підтримую"

    save_message(chat_id, "user", text)
    analyze_and_save(chat_id, text)
    detect_mood(chat_id, text)

    reply = ask_ai(chat_id, text)

    save_message(chat_id, "assistant", reply)
    send_message(chat_id, reply)

    return "ok"

# --- LOOP ---
def reminder_loop():
    while True:
        check_reminders()
        time.sleep(30)

threading.Thread(target=reminder_loop).start()

# --- START ---
def set_webhook():
    url = "https://telegram-ai-bot-7qbx.onrender.com/webhook"
    requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}")

set_webhook()

app.run(host="0.0.0.0", port=10000)
