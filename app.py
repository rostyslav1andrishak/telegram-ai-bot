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
    0: ["10:00","12:00","14:00","16:00"],
    1: ["10:00","12:00","14:00","16:00"],
    2: ["10:00","12:00","14:00","16:00"],
    3: ["10:00","12:00","14:00","16:00"],
    4: ["10:00","12:00","14:00","16:00"],
    5: ["10:00","12:00","14:00"],
}

# --- ADMIN ---
admins = {}
admin_mode = {}

def is_admin(token, user_id):
    return admins.get(token) == user_id

def set_admin(token, user_id):
    admins[token] = user_id

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
        ["💅 Ціни"],
        ["📖 Мій запис"],
        ["❌ Скасувати запис"]
    ])

# --- SCHEDULE ---
def set_day_off(token, date):
    cursor.execute("DELETE FROM schedule WHERE bot_token=? AND date=?", (token, date))
    for t in ["10:00","12:00","14:00","16:00"]:
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
def handle_admin(token,chat_id,text):

    if text == "/admin":
        set_admin(token,chat_id)
        admin_mode[chat_id] = True

        send_keyboard(token,chat_id,
        """🔐 Адмін режим

Манікюр 600

Вихідний 25.03
Закрити 14:00 26.03
Відкрити 14:00 26.03
""",
        [["🏠 Вийти"]])
        return True

    if not is_admin(token,chat_id):
        return False

    if text in ["🏠 Вийти","/start"]:
        admin_mode.pop(chat_id, None)
        show_menu(token,chat_id)
        return True

    if not admin_mode.get(chat_id):
        return False

    t = text.lower()

    # --- ГРАФІК ---
    try:
        if "вихідний" in t:
            date = text.split()[-1]
            set_day_off(token, date)
            send_keyboard(token,chat_id,f"🚫 {date} вихідний",[["🏠 Вийти"]])
            return True

        if "закрити" in t:
            time, date = text.split()[1:3]
            close_time(token, date, time)
            send_keyboard(token,chat_id,f"🚫 {date} {time} закрито",[["🏠 Вийти"]])
            return True

        if "відкрити" in t:
            time, date = text.split()[1:3]
            open_time(token, date, time)
            send_keyboard(token,chat_id,f"✅ {date} {time} відкрито",[["🏠 Вийти"]])
            return True
    except:
        pass

    # --- ПОСЛУГИ ---
    lines = text.split("\n")
    added = []

    for line in lines:
        parts = line.strip().split()
        if len(parts) < 2:
            continue

        price = parts[-1]
        if not price.replace(".", "").isdigit():
            continue

        name = " ".join(parts[:-1])
        cursor.execute("INSERT INTO services VALUES (?, ?, ?)", (token, name, price))
        added.append(f"✅ {name} — {price}")

    conn.commit()

    if added:
        send_keyboard(token,chat_id,"\n".join(added),[["🏠 Вийти"]])
        return True

    return False

# --- SERVICES ---
def get_services(token):
    cursor.execute("SELECT name, price FROM services WHERE bot_token=?", (token,))
    return cursor.fetchall()

def get_categories(token):
    categories = {}
    for name, price in get_services(token):
        key = name.split()[0]
        categories.setdefault(key, []).append((name, price))
    return categories

def show_categories(token, chat_id):
    categories = get_categories(token)

    if not categories:
        send_keyboard(token,chat_id,"❌ Немає послуг",[["🏠 Меню"]])
        return

    buttons = [[c] for c in categories] + [["🏠 Меню"]]
    send_keyboard(token,chat_id,"💅 Обери категорію:",buttons)

def show_services(token, chat_id, category):
    services = get_categories(token).get(category, [])
    buttons = [[s[0]] for s in services] + [["🔙 Назад"]]
    send_keyboard(token,chat_id,category,buttons)

# --- BOOKINGS ---
user_states = {}

def is_taken(token,date,time):
    cursor.execute("SELECT 1 FROM bookings WHERE bot_token=? AND date=? AND time=?", (token,date,time))
    return cursor.fetchone()

def save_booking(token,user_id,service,date,time):
    cursor.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?)", (token,user_id,service,date,time))
    conn.commit()

def delete_booking(token,user_id):
    cursor.execute("DELETE FROM bookings WHERE bot_token=? AND user_id=?",(token,user_id))
    conn.commit()

def get_user_booking(token,user_id):
    cursor.execute("SELECT service,date,time FROM bookings WHERE bot_token=? AND user_id=?",(token,user_id))
    return cursor.fetchone()

# --- DATE ---
def show_dates(token, chat_id):
    today = datetime.now()
    buttons = []

    for i in range(5):
        d = today + timedelta(days=i)
        if d.weekday() not in WORK_DAYS:
            continue

        label = d.strftime("%d.%m")
        if i == 0: label = "Сьогодні " + label
        elif i == 1: label = "Завтра " + label

        buttons.append([label])

    buttons.append(["🏠 Меню"])
    send_keyboard(token,chat_id,"📅 Обери дату:",buttons)

# --- TIME ---
def show_times(token, chat_id, date):

    date_clean = date.split()[-1]

    try:
        weekday = datetime.strptime(date_clean,"%d.%m").weekday()
    except:
        weekday = datetime.now().weekday()

    slots = DAY_SLOTS.get(weekday, [])

    free = [t for t in slots if not is_taken(token, date_clean, t) and is_open(token, date_clean, t)]

    if not free:
        send_keyboard(token,chat_id,"❌ Немає місць",[["🏠 Меню"]])
        return

    send_keyboard(token,chat_id,"🕒 Вільний час:", [[t] for t in free] + [["🏠 Меню"]])

# --- FLOW ---
def handle_booking(token,chat_id,text):

    key=f"{token}_{chat_id}"
    state=user_states.get(key)

    if text == "🏠 Меню":
        user_states.pop(key,None)
        show_menu(token,chat_id)
        return True

    if text == "📅 Записатися":
        user_states[key]={"step":"category"}
        show_categories(token,chat_id)
        return True

    if not state:
        return False

    if state["step"]=="category":
        state["category"]=text
        state["step"]="service"
        show_services(token,chat_id,text)
        return True

    elif state["step"]=="service":
        state["service"]=text
        state["step"]="date"
        show_dates(token,chat_id)
        return True

    elif state["step"]=="date":
        state["date"]=text.split()[-1]
        state["step"]="time"
        show_times(token,chat_id,text)
        return True

    elif state["step"]=="time":
        save_booking(token,chat_id,state["service"],state["date"],text)
        send_keyboard(token,chat_id,f"✅ {state['service']}\n{state['date']} {text}",[["🏠 Меню"]])
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

        msg="💅 Прайс:\n\n"
        for s in services:
            msg+=f"{s[0]} — {s[1]} Kč\n"

        send_keyboard(token,chat_id,msg,[["🏠 Меню"]])
        return True

    if text == "📖 Мій запис":
        b=get_user_booking(token,chat_id)

        if not b:
            send_keyboard(token,chat_id,"Немає запису",[["🏠 Меню"]])
            return True

        send_keyboard(token,chat_id,f"{b[0]}\n{b[1]} {b[2]}",[["🏠 Меню"]])
        return True

    if text == "❌ Скасувати запис":
        delete_booking(token,chat_id)
        send_keyboard(token,chat_id,"❌ Скасовано",[["🏠 Меню"]])
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
    TOKEN = "8741891429:AAF2IQ_6Mtx741sS2Jevu7eQgQaQGK7yCms"
    connect_bot(TOKEN)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
