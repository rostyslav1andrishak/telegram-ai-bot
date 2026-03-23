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
admin_states = {}

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

# --- ADMIN MENU ---
def show_admin_menu(token, chat_id):
    send_keyboard(token, chat_id,
    "⚙️ Адмінка",
    [
        ["➕ Додати послугу"],
        ["🗑 Очистити послуги"],
        ["📋 Список послуг"],
        ["🏠 Меню"]
    ])

# --- SERVICES ---
def add_service(token, name, price):
    cursor.execute("INSERT INTO services VALUES (?, ?, ?)", (token, name, price))
    conn.commit()

def get_services(token):
    cursor.execute("SELECT name, price FROM services WHERE bot_token=?", (token,))
    return cursor.fetchall()

def clear_services(token):
    cursor.execute("DELETE FROM services WHERE bot_token=?", (token,))
    conn.commit()

# --- CATEGORY ---
def get_services_structured(token):
    services = get_services(token)

    categories = {}

    for name, price in services:
        key = name.split()[0]

        if key not in categories:
            categories[key] = []

        categories[key].append((name, price))

    return categories

def show_categories(token, chat_id):
    categories = get_services_structured(token)

    buttons = [[c] for c in categories]
    buttons.append(["🏠 Меню"])

    send_keyboard(token, chat_id, "💅 Обери категорію:", buttons)

def show_services_by_category(token, chat_id, category):
    categories = get_services_structured(token)
    services = categories.get(category, [])

    buttons = [[s[0]] for s in services]
    buttons.append(["🔙 Назад"])

    send_keyboard(token, chat_id, category, buttons)

# --- DATE (BOOKSY STYLE) ---
def show_dates(token, chat_id):
    today = datetime.now()

    buttons = []

    for i in range(5):
        d = today + timedelta(days=i)

        if d.weekday() not in WORK_DAYS:
            continue

        label = d.strftime("%d.%m")

        if i == 0:
            label = "Сьогодні " + label
        elif i == 1:
            label = "Завтра " + label

        buttons.append([label])

    buttons.append(["🏠 Меню"])

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

# --- TIME ---
def show_times(token, chat_id, date):

    date_clean = date.split()[-1]

    try:
        weekday = datetime.strptime(date_clean,"%d.%m").weekday()
    except:
        weekday = datetime.now().weekday()

    slots = DAY_SLOTS.get(weekday, [])

    free = [t for t in slots if not is_taken(token, date_clean, t)]

    if not free:
        send_keyboard(token, chat_id, "❌ Немає місць", [["🏠 Меню"]])
        return

    buttons = [[t] for t in free]
    buttons.append(["🏠 Меню"])

    send_keyboard(token, chat_id, "🕒 Вільний час:", buttons)

# --- BOOKING FLOW ---
def handle_booking(token,chat_id,text):

    key=f"{token}_{chat_id}"
    state=user_states.get(key)

    if text == "🏠 Меню":
        user_states.pop(key, None)
        show_menu(token, chat_id)
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
        show_services_by_category(token,chat_id,text)
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

        if is_taken(token,state["date"],text):
            send_keyboard(token,chat_id,"❌ Зайнято",[["🏠 Меню"]])
            return True

        save_booking(token,chat_id,state["service"],state["date"],text)

        send_keyboard(token,chat_id,f"""✅ Запис підтверджено

💅 {state["service"]}
📅 {state["date"]}
🕒 {text}
""",[["🏠 Меню"]])

        user_states.pop(key,None)
        return True

    return False

# --- ADMIN HANDLER ---
def handle_admin(token,chat_id,text):

    if text == "/admin":
        set_admin(token,chat_id)
        show_admin_menu(token,chat_id)
        return True

    if not is_admin(token,chat_id):
        return False

    if text == "➕ Додати послугу":
        admin_states[chat_id] = "add_service"
        send_keyboard(token,chat_id,"Напиши: Назва 1000",[["🏠 Меню"]])
        return True

    if text == "🗑 Очистити послуги":
        clear_services(token)
        send_keyboard(token,chat_id,"✅ Очищено",[["🏠 Меню"]])
        return True

    if text == "📋 Список послуг":
        s=get_services(token)

        msg="📋 Послуги:\n\n"
        for i in s:
            msg+=f"{i[0]} — {i[1]}\n"

        send_keyboard(token,chat_id,msg,[["🏠 Меню"]])
        return True

    # додавання через текст
    if admin_states.get(chat_id) == "add_service":
        try:
            parts = text.split()
            price = parts[-1]
            name = " ".join(parts[:-1])

            add_service(token,name,price)

            send_keyboard(token,chat_id,f"✅ {name} — {price}",[["🏠 Меню"]])
            admin_states.pop(chat_id)
            return True
        except:
            send_keyboard(token,chat_id,"❌ Помилка",[["🏠 Меню"]])
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

        send_keyboard(token,chat_id,f"""
📅 Запис:

💅 {b[0]}
📅 {b[1]}
🕒 {b[2]}
""",[["🏠 Меню"]])
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

# --- CONNECT ---
def connect_bot(token):
    url = f"https://telegram-ai-bot-7qbx.onrender.com/webhook/{token}"
    requests.get(
        f"https://api.telegram.org/bot{token}/setWebhook?url={url}"
    )

connect_bot("8741891429:AAF2IQ_6Mtx741sS2Jevu7eQgQaQGK7yCms")

app.run(host="0.0.0.0", port=10000)
