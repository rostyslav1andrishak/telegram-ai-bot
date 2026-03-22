import requests
import sqlite3
from flask import Flask, request
import os
import json

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

# --- DB ---
conn = sqlite3.connect("memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    bot_token TEXT,
    user_id INTEGER,
    service TEXT,
    date TEXT,
    time TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    bot_token TEXT,
    user_id INTEGER,
    role TEXT,
    text TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS facts (
    bot_token TEXT,
    user_id INTEGER,
    category TEXT,
    key TEXT,
    value TEXT
)
""")

conn.commit()

# --- TELEGRAM ---
def send_message(token, chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]}
    )

def send_photo(token, chat_id, url, caption=""):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        json={"chat_id": chat_id, "photo": url, "caption": caption}
    )

# --- HISTORY ---
def save_message(token, user_id, role, text):
    cursor.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?)",
        (token, user_id, role, text)
    )
    conn.commit()

def get_history(token, user_id):
    cursor.execute("""
        SELECT role, text FROM messages
        WHERE bot_token=? AND user_id=?
        ORDER BY rowid DESC LIMIT 10
    """, (token, user_id))
    rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# --- MEMORY ---
def get_memory(token, user_id):
    cursor.execute("""
        SELECT category, key, value FROM facts
        WHERE bot_token=? AND user_id=?
    """, (token, user_id))
    rows = cursor.fetchall()

    return "\n".join([f"[{c}] {k}: {v}" for c,k,v in rows]) if rows else "немає"

def save_facts(token, user_id, facts):
    for category, values in facts.items():
        for k,v in values.items():
            cursor.execute("""
            DELETE FROM facts WHERE bot_token=? AND user_id=? AND category=? AND key=?
            """,(token,user_id,category,k))

            cursor.execute("""
            INSERT INTO facts VALUES (?, ?, ?, ?, ?)
            """,(token,user_id,category,k,v))
    conn.commit()

# --- SMART MEMORY ---
def analyze_and_save(token, user_id, text):
    if len(text) < 8:
        return

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages":[
                    {"role":"system","content":"Виділи важливі факти JSON"},
                    {"role":"user","content":text}
                ]
            }
        )

        data = response.json()
        if "choices" not in data:
            return

        content = data["choices"][0]["message"]["content"]

        try:
            facts = json.loads(content)
            save_facts(token,user_id,facts)
        except:
            pass
    except:
        pass

# --- BOOKINGS ---
AVAILABLE_SLOTS = ["10:00","12:00","14:00","16:00"]
user_states = {}

def is_taken(token,date,time):
    cursor.execute("""
    SELECT * FROM bookings WHERE bot_token=? AND date=? AND time=?
    """,(token,date,time))
    return cursor.fetchone()

def save_booking(token,user_id,service,date,time):
    cursor.execute(
        "INSERT INTO bookings VALUES (?, ?, ?, ?, ?)",
        (token,user_id,service,date,time)
    )
    conn.commit()

def get_bookings(token):
    cursor.execute("""
    SELECT service,date,time FROM bookings WHERE bot_token=?
    """,(token,))
    return cursor.fetchall()

# --- BOOKING FLOW ---
def handle_booking(token,chat_id,text):

    key=f"{token}_{chat_id}"
    state=user_states.get(key)

    if not state:
        if "запис" in text.lower():
            user_states[key]={"step":"service"}
            send_message(token,chat_id,"💅 Яка процедура?")
            return True
        return False

    if state["step"]=="service":
        state["service"]=text
        state["step"]="date"
        send_message(token,chat_id,"📅 Дата?")
        return True

    elif state["step"]=="date":
        state["date"]=text
        state["step"]="time"

        free=[t for t in AVAILABLE_SLOTS if not is_taken(token,text,t)]

        if not free:
            send_message(token,chat_id,"❌ Немає місць")
            user_states.pop(key,None)
            return True

        send_message(token,chat_id,"🕒 Вільно:\n"+ "\n".join(free))
        return True

    elif state["step"]=="time":

        if is_taken(token,state["date"],text):
            send_message(token,chat_id,"❌ Зайнято")
            return True

        save_booking(token,chat_id,state["service"],state["date"],text)

        send_message(token,chat_id,f"""✅ Запис підтверджено

💅 {state["service"]}
📅 {state["date"]}
🕒 {text}""")

        user_states.pop(key,None)
        return True

    return False

# --- IMAGE ---
def analyze_image(token,file_id):
    file=requests.get(
        f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
    ).json()

    file_path=file["result"]["file_path"]
    url=f"https://api.telegram.org/file/bot{token}/{file_path}"

    try:
        r=requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization":f"Bearer {OPENAI_API_KEY}"},
            json={
                "model":"gpt-4o-mini",
                "input":[
                    {
                        "role":"user",
                        "content":[
                            {"type":"input_text","text":"Опиши фото"},
                            {"type":"input_image","image_url":url}
                        ]
                    }
                ]
            }
        )
        return r.json()["output"][0]["content"][0]["text"]
    except:
        return "Не зміг обробити фото"

# --- VOICE ---
def handle_voice(token,file_id):
    try:
        file=requests.get(
            f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
        ).json()

        file_path=file["result"]["file_path"]
        url=f"https://api.telegram.org/file/bot{token}/{file_path}"

        audio=requests.get(url).content

        r=requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization":f"Bearer {OPENAI_API_KEY}"},
            files={
                "file":("voice.ogg",audio),
                "model":(None,"gpt-4o-mini-transcribe")
            }
        )

        return r.json().get("text","не розпізнано")
    except:
        return "Помилка голосу"

# --- COMMANDS ---
def handle_commands(token,chat_id,text):

    t=text.lower()

    if "прайс" in t:
        send_message(token,chat_id,
        "💅 Манікюр — 600 Kč\nПедикюр — 800 Kč\nВії — 1200 Kč")
        return True

    if "мої записи" in t:
        b=get_bookings(token)

        if not b:
            send_message(token,chat_id,"Немає записів")
            return True

        msg="📅 Записи:\n\n"
        for i in b:
            msg+=f"{i[0]} | {i[1]} | {i[2]}\n"

        send_message(token,chat_id,msg)
        return True

    return False

# --- AI ---
def ask_ai(token,user_id,message):

    history=get_history(token,user_id)
    memory=get_memory(token,user_id)

    messages=[{
        "role":"system",
        "content":f"""
Ти AI адміністратор салону.

ПАМʼЯТЬ:
{memory}

Відповідай коротко і приємно.
"""
    }]

    messages+=history
    messages.append({"role":"user","content":message})

    r=requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization":f"Bearer {OPENAI_API_KEY}",
            "Content-Type":"application/json"
        },
        json={
            "model":"gpt-4o-mini",
            "messages":messages
        }
    )

    data=r.json()

    if "choices" not in data:
        return "Помилка"

    return data["choices"][0]["message"]["content"]

# --- WEBHOOK ---
@app.route("/webhook/<token>",methods=["POST"])
def webhook(token):

    data=request.get_json()
    message=data.get("message")

    if not message:
        return "ok"

    chat_id=message["chat"]["id"]

    if "text" in message:
        text=message["text"]

    elif "photo" in message:
        file_id=message["photo"][-1]["file_id"]
        text=analyze_image(token,file_id)

    elif "voice" in message:
        file_id=message["voice"]["file_id"]
        text=handle_voice(token,file_id)

    else:
        text="Не підтримую"

    if handle_booking(token,chat_id,text):
        return "ok"

    if handle_commands(token,chat_id,text):
        return "ok"

    save_message(token,chat_id,"user",text)
    analyze_and_save(token,chat_id,text)

    reply=ask_ai(token,chat_id,text)

    save_message(token,chat_id,"assistant",reply)
    send_message(token,chat_id,reply)

    return "ok"

# --- CONNECT BOT ---
def connect_bot(token):
    url = f"https://telegram-ai-bot-7qbx.onrender.com/webhook/{token}"
    requests.get(
        f"https://api.telegram.org/bot{token}/setWebhook?url={url}"
    )

# 🔥 ПІДКЛЮЧАЄМО БОТА
connect_bot("8741891429:AAF2IQ_6Mtx741sS2Jevu7eQgQaQGK7yCms")

# 🚀 ЗАПУСК
app.run(host="0.0.0.0", port=10000)
