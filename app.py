import requests
import sqlite3
from flask import Flask, request
from datetime import datetime, timedelta

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
CREATE TABLE IF NOT EXISTS services (
    bot_token TEXT,
    name TEXT,
    price TEXT
)
""")

conn.commit()

# --- ГРАФІК ---
WORK_DAYS = [0,1,2,3,4,5]

DAY_SLOTS = {
    0: ["10:00","12:00","14:00","16:00"],
    1: ["10:00","12:00","14:00","16:00"],
    2: ["10:00","12:00","14:00","16:00"],
    3: ["10:00","12:00","14:00","16:00"],
    4: ["10:00","12:00","14:00","16:00"],
    5: ["10:00","12:00","14:00"],
}

# --- ADMIN ---
admins = {}

def is_admin(token, user_id):
    return admins.get(token) == user_id

def set_admin(token, user_id):
    admins[token] = user_id

# --- TELEGRAM ---
def send_message(token, chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

def send_keyboard(token, chat_id, text, buttons):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {
                "keyboard": buttons,
                "resize_keyboard": True
            }
        }
    )

# --- MENU ---
def show_menu(token, chat_id):
    send_keyboard(token, chat_id, "💅 Обери дію:", [
        ["📅 Записатися"],
        ["💅 Прайс"],
        ["📖 Мій запис"],
        ["❌ Скасувати запис"]
    ])

# --- SERVICES ---
def add_service(token, name, price):
    cursor.execute("INSERT INTO services VALUES (?, ?, ?)", (token, name, price))
    conn.commit()

def get_services(token):
    cursor.execute("SELECT name, price FROM services WHERE bot_token=?", (token,))
    return cursor.fetchall()

def show_services(token, chat_id):
    services = get_services(token)

    if not services:
        send_message(token, chat_id, "❌ Немає послуг")
        return

    buttons = [[s[0]] for s in services]
    buttons.append(["🔙 Назад"])

    send_keyboard(token, chat_id, "💅 Обери послугу:", buttons)

# --- ДАТИ ---
def show_dates(token, chat_id):
    today = datetime.now()
    buttons = []

    for i in range(7):
        d = today + timedelta(days=i)

        if d.weekday() not in WORK_DAYS:
            continue

        buttons.append([d.strftime("%d.%m")])

    buttons.append(["🔙 Назад"])

    send_keyboard(token, chat_id, "📅 Обери дату:", buttons)

# --- BOOKINGS ---
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

def get_user_booking(token,user_id):
    cursor.execute("""
    SELECT service,date,time FROM bookings
    WHERE bot_token=? AND user_id=?
    """,(token,user_id))
    return cursor.fetchone()

def delete_booking(token,user_id):
    cursor.execute("""
    DELETE FROM bookings WHERE bot_token=? AND user_id=?
    """,(token,user_id))
    conn.commit()

# --- ЧАС ---
def show_times(token, chat_id, date):

    try:
        weekday = datetime.strptime(date,"%d.%m").weekday()
    except:
        weekday = datetime.now().weekday()

    slots = DAY_SLOTS.get(weekday, [])

    free = [t for t in slots if not is_taken(token, date, t)]

    if not free:
        send_message(token, chat_id, "❌ Немає місць")
        show_menu(token, chat_id)
        return

    buttons = [[t] for t in free]
    buttons.append(["🔙 Назад"])

    send_keyboard(token, chat_id, "🕒 Обери час:", buttons)

# --- BOOKING FLOW ---
def handle_booking(token,chat_id,text):

    key=f"{token}_{chat_id}"
    state=user_states.get(key)

    if text == "🔙 Назад":
        user_states.pop(key, None)
        show_menu(token, chat_id)
        return True

    if text == "📅 Записатися":
        user_states[key]={"step":"service"}
        show_services(token,chat_id)
        return True

    if not state:
        return False

    if state["step"]=="service":
        state["service"]=text
        state["step"]="date"
        show_dates(token, chat_id)
        return True

    elif state["step"]=="date":
        state["date"]=text
        state["step"]="time"
        show_times(token,chat_id,text)
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
        show_menu(token,chat_id)
        return True

    return False

# --- ADMIN ---
def handle_admin(token,chat_id,text):

    if "/admin" in text:
        set_admin(token,chat_id)
        send_message(token,chat_id,"🔐 Ти адмін")
        return True

    if not is_admin(token,chat_id):
        return False

    if "додай послугу" in text:
        try:
            parts = text.split()
            price = parts[-1]
            name = " ".join(parts[2:-1])

            add_service(token,name,price)
            send_message(token,chat_id,f"✅ {name} — {price}")
            return True
        except:
            pass

    return False

# --- COMMANDS ---
def handle_commands(token,chat_id,text):

    if text == "/start":
        show_menu(token,chat_id)
        return True

    if text == "💅 Прайс":
        services=get_services(token)

        if not services:
            send_message(token,chat_id,"Прайс пустий")
            return True

        msg="💅 Прайс:\n\n"
        for s in services:
            msg+=f"{s[0]} — {s[1]} Kč\n"

        send_message(token,chat_id,msg)
        return True

    if text == "📖 Мій запис":
        b=get_user_booking(token,chat_id)

        if not b:
            send_message(token,chat_id,"Немає запису")
            return True

        send_message(token,chat_id,f"""
📅 Твій запис:

💅 {b[0]}
📅 {b[1]}
🕒 {b[2]}
""")
        return True

    if text == "❌ Скасувати запис":
        delete_booking(token,chat_id)
        send_message(token,chat_id,"❌ Запис скасовано")
        show_menu(token,chat_id)
        return True

    return False

# --- WEBHOOK ---
@app.route("/webhook/<token>",methods=["POST"])
def webhook(token):

    data=request.get_json()
    message=data.get("message")

    if not message:
        return "ok"

    chat_id=message["chat"]["id"]
    text=message.get("text","")

    if handle_admin(token,chat_id,text):
        return "ok"

    if handle_booking(token,chat_id,text):
        return "ok"

    if handle_commands(token,chat_id,text):
        return "ok"

    send_message(token,chat_id,"Напиши /start")
    return "ok"

# --- CONNECT ---
def connect_bot(token):
    url = f"https://telegram-ai-bot-7qbx.onrender.com/webhook/{token}"
    requests.get(
        f"https://api.telegram.org/bot{token}/setWebhook?url={url}"
    )

connect_bot("8741891429:AAF2IQ_6Mtx741sS2Jevu7eQgQaQGK7yCms")

app.run(host="0.0.0.0", port=10000)
