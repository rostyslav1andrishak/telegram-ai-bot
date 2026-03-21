import requests
import sqlite3
from flask import Flask, request
import os
import json

TOKEN = "8658895357:AAGCcvoiqwQGPCgpuXWAmSeQiM3IDHq4sRc"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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

# --- TELEGRAM SENDERS ---
def send_message(chat_id, text):
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

    return text if text else "немає даних"

# --- SMART MEMORY ---
def analyze_and_save(user_id, text):
    try:
        if len(text) < 8:
            return

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
Виділи тільки важливі факти.

Формат JSON:
{"категорія": {"ключ": "значення"}}

Якщо нічого → {}
"""},
                    {"role": "user", "content": text}
                ]
            }
        )

        data = response.json()
        if "choices" not in data:
            return

        content = data["choices"][0]["message"]["content"]

        try:
            facts = json.loads(content)
        except:
            print("JSON ERROR:", content)
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

# --- IMAGE ANALYSIS ---
def analyze_image(file_id):
    file = requests.get(
        f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
    ).json()

    file_path = file["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Опиши це фото"},
                    {"type": "input_image", "image_url": file_url}
                ]
            }]
        }
    )

    data = response.json()
    return data["output"][0]["content"][0]["text"]

# --- VOICE ---
def handle_voice(file_id):
    return "🎤 Голос отримав (додамо скоро)"

# --- AI ---
def ask_ai(user_id, message):

    history = get_history(user_id)
    memory = get_memory(user_id)

    messages = [{
        "role": "system",
        "content": f"""
Ти AI асистент.

ТИ МАЄШ ПАМʼЯТЬ:
{memory}

Будь коротким, розумним і практичним.
"""
    }]

    messages += history
    messages.append({"role": "user", "content": message})

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
        return f"Помилка: {data}"

    return data["choices"][0]["message"]["content"]

# --- COMMANDS ---
def handle_commands(chat_id, text):

    t = text.lower()

    if "графік" in t:
        send_photo(chat_id,
            "https://www.coinglass.com/pro/funding_rate",
            "📊 Графік funding rate")
        return True

    if "відео" in t:
        send_video(chat_id,
            "https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4",
            "🎬 Приклад відео")
        return True

    if "документ" in t:
        send_document(chat_id,
            "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
            "📄 Приклад файлу")
        return True

    return False

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

    elif "photo" in message:
        file_id = message["photo"][-1]["file_id"]
        text = analyze_image(file_id)

    elif "voice" in message:
        file_id = message["voice"]["file_id"]
        text = handle_voice(file_id)

    else:
        text = "Не підтримую"

    save_message(chat_id, "user", text)
    analyze_and_save(chat_id, text)

    reply = ask_ai(chat_id, text)

    save_message(chat_id, "assistant", reply)
    send_message(chat_id, reply)

    return "ok"

app.run(host="0.0.0.0", port=10000)
