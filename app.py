import requests
import sqlite3
from flask import Flask, request
from datetime import datetime, timedelta
import os

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS schedule (
    bot_token TEXT,
    date TEXT,
    time TEXT,
    is_open INTEGER
)
""")

conn.commit()

# --- SETTINGS ---
WORK_DAYS = [0,1,2,3,4,5]

DAY_SLOTS = {
    i: [f"{h:02d}:00" for h in range(8,18)]
    for i in range(6)
}

# --- TELEGRAM ---
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
    send_keyboard(token, chat_id,
    "💖 Вітаю в салоні!",
    [
        ["📅 Записатися"],
        ["💅 Ціни"]
    ])

# --- SCHEDULE ---
def set_day_off(token, date):
    cursor.execute("DELETE FROM schedule WHERE bot_token=? AND date=?", (token, date))
    for t in [f"{h:02d}:00" for h in range(8,18)]:
        cursor.execute("INSERT INTO schedule VALUES (?, ?, ?, 0)", (token, date, t))
    conn.commit()

def close_time(token, date, time):
    cursor.execute("DELETE FROM schedule WHERE bot_token=? AND date=? AND time=?", (token,date,time))
    cursor.execute("INSERT INTO schedule VALUES (?, ?, ?, 0)", (token, date, time))
    conn.commit()

def open_time(token, date, time):
    cursor.execute("DELETE FROM schedule WHERE bot_token=? AND date=? AND time=?", (token,date,time))
    conn.commit()

def is_open(token, date, time):
    cursor.execute("SELECT is_open FROM schedule WHERE bot_token=? AND date=? AND time=?", (token,date,time))
    r = cursor.fetchone()
    return True if not r else r[0] == 1

# --- ADMIN ---
admins = {}
admin_mode = {}
admin_states = {}

def is_admin(token, user_id):
    return admins.get(token) == user_id

def set_admin(token, user_id):
    admins[token] = user_id

# --- ADMIN CALENDAR ---
def show_admin_dates(token, chat_id):
    today = datetime.now()
    buttons = []

    for i in range(7):
        d = today + timedelta(days=i)
        buttons.append([d.strftime("%d.%m")])

    buttons.append(["⬅️ Назад"])

    send_keyboard(token, chat_id, "📅 Обери день:", buttons)

def show_admin_times(token, chat_id, date):
    weekday = datetime.strptime(date,"%d.%m").weekday()
    slots = DAY_SLOTS.get(weekday, [])

    buttons = []

    for t in slots:
        if is_taken(token, date, t):
            status = "🔴"
        elif not is_open(token, date, t):
            status = "❌"
        else:
            status = "🟢"

        buttons.append([f"{t} {status}"])

    buttons.append(["⬅️ Назад"])

    send_keyboard(token, chat_id, f"🕒 {date}", buttons)

# --- ADMIN ---
def handle_admin(token,chat_id,text):

    if text == "/admin":
        set_admin(token,chat_id)
        admin_mode[chat_id] = True

        send_keyboard(token,chat_id,
        "🔐 Адмін режим",
        [
            ["➕ Додати послугу"],
            ["📅 Календар"],
            ["🏠 Вийти"]
        ])
        return True

    if not is_admin(token,chat_id):
        return False

    if text in ["🏠 Вийти","/start"]:
        admin_mode.pop(chat_id, None)
        admin_states.pop(chat_id, None)
        show_menu(token,chat_id)
        return True

    if not admin_mode.get(chat_id):
        return False

    # --- календар ---
    if text == "📅 Календар":
        admin_states[chat_id] = {"step":"date"}
        show_admin_dates(token, chat_id)
        return True

    state = admin_states.get(chat_id)

    if state:
        if state["step"] == "date":
            state["date"] = text
            state["step"] = "time"
            show_admin_times(token, chat_id, text)
            return True

        if state["step"] == "time":

            if text == "⬅️ Назад":
                show_admin_dates(token, chat_id)
                state["step"] = "date"
                return True

            time = text.split()[0]
            date = state["date"]

            if is_open(token, date, time):
                close_time(token, date, time)
            else:
                open_time(token, date, time)

            show_admin_times(token, chat_id, date)
            return True

    # --- додавання послуг ---
    parts = text.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        name = " ".join(parts[:-1])
        price = parts[-1]
        cursor.execute("INSERT INTO services VALUES (?, ?, ?)", (token, name, price))
        conn.commit()

        send_keyboard(token,chat_id,f"✅ {name} — {price}",[["🏠 Вийти"]])
        return True

    return True

# --- SERVICES ---
def get_services(token):
    cursor.execute("SELECT name, price FROM services WHERE bot_token=?", (token,))
    return cursor.fetchall()

def show_services(token, chat_id):
    services = get_services(token)
    buttons = [[s[0]] for s in services]
    buttons.append(["🏠 Меню"])
    send_keyboard(token,chat_id,"💅 Обери послугу:",buttons)

# --- BOOKINGS ---
user_states = {}

def is_taken(token,date,time):
    cursor.execute("SELECT 1 FROM bookings WHERE bot_token=? AND date=? AND time=?", (token,date,time))
    return cursor.fetchone()

def save_booking(token,user_id,service,date,time):
    cursor.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?)", (token,user_id,service,date,time))
    conn.commit()

# --- DATE ---
def show_dates(token, chat_id):
    today = datetime.now()
    buttons = []

    for i in range(5):
        d = today + timedelta(days=i)

        if d.weekday() not in WORK_DAYS:
            continue

        buttons.append([d.strftime("%d.%m")])

    send_keyboard(token,chat_id,"📅 Обери дату:",buttons)

# --- TIME ---
def show_times(token, chat_id, date):

    date_clean = date

    weekday = datetime.strptime(date_clean,"%d.%m").weekday()

    if weekday not in WORK_DAYS:
        send_keyboard(token,chat_id,"❌ Вихідний",[["🏠 Меню"]])
        return

    slots = DAY_SLOTS.get(weekday, [])

    free = [
        t for t in slots
        if not is_taken(token, date_clean, t)
        and is_open(token, date_clean, t)
    ]

    if not free:
        send_keyboard(token,chat_id,"❌ Немає місць",[["🏠 Меню"]])
        return

    send_keyboard(token,chat_id,"🕒 Обери час:", [[t] for t in free])

# --- FLOW ---
def handle_booking(token,chat_id,text):

    key=f"{token}_{chat_id}"
    state=user_states.get(key)

    if text == "📅 Записатися":
        user_states[key]={"step":"service"}
        show_services(token,chat_id)
        return True

    if not state:
        return False

    if state["step"]=="service":
        state["service"]=text
        state["step"]="date"
        show_dates(token,chat_id)
        return True

    elif state["step"]=="date":
        state["date"]=text
        state["step"]="time"
        show_times(token,chat_id,text)
        return True

    elif state["step"]=="time":
        save_booking(token,chat_id,state["service"],state["date"],text)

        send_keyboard(token,chat_id,
        f"✅ {state['service']}\n📅 {state['date']} {text}",
        [["🏠 Меню"]])

        user_states.pop(key,None)
        return True

    return False

# --- COMMANDS ---
def handle_commands(token,chat_id,text):

    if text in ["/start","🏠 Меню"]:
        show_menu(token,chat_id)
        return True

    if text == "💅 Ціни":
        services=get_services(token)
        msg="\n".join([f"{s[0]} — {s[1]} Kč" for s in services]) or "❌ Пусто"
        send_keyboard(token,chat_id,msg,[["🏠 Меню"]])
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

    show_menu(token,chat_id)
    return "ok"

# --- START ---
def connect_bot(token):
    url = f"https://telegram-ai-bot-7qbx.onrender.com/webhook/{token}"
    requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={url}")

if __name__ == "__main__":
    TOKEN = "ТВІЙ_ТОКЕН"
    connect_bot(TOKEN)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
