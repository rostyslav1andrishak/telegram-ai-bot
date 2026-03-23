# --- ADMIN ---
def handle_admin(token,chat_id,text):

    if text == "/admin":
        set_admin(token,chat_id)
        admin_mode[chat_id] = True

        send_keyboard(token,chat_id,
        """🔐 Адмін режим

📌 Додавай послуги:
Манікюр 600

📌 Графік:
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
    if "вихідний" in t:
        try:
            date = text.split()[-1]

            cursor.execute("DELETE FROM schedule WHERE bot_token=? AND date=?", (token, date))

            for tm in ["10:00","12:00","14:00","16:00"]:
                cursor.execute("INSERT INTO schedule VALUES (?, ?, ?, 0)", (token, date, tm))

            conn.commit()

            send_keyboard(token,chat_id,f"🚫 {date} вихідний",[["🏠 Вийти"]])
            return True
        except:
            send_keyboard(token,chat_id,"❌ Помилка формату",[["🏠 Вийти"]])
            return True

    if "закрити" in t:
        try:
            parts = text.split()
            time = parts[1]
            date = parts[2]

            cursor.execute("DELETE FROM schedule WHERE bot_token=? AND date=? AND time=?", (token,date,time))
            cursor.execute("INSERT INTO schedule VALUES (?, ?, ?, 0)", (token, date, time))
            conn.commit()

            send_keyboard(token,chat_id,f"🚫 {date} {time} закрито",[["🏠 Вийти"]])
            return True
        except:
            send_keyboard(token,chat_id,"❌ Закрити 14:00 26.03",[["🏠 Вийти"]])
            return True

    if "відкрити" in t:
        try:
            parts = text.split()
            time = parts[1]
            date = parts[2]

            cursor.execute("DELETE FROM schedule WHERE bot_token=? AND date=? AND time=?", (token,date,time))
            conn.commit()

            send_keyboard(token,chat_id,f"✅ {date} {time} відкрито",[["🏠 Вийти"]])
            return True
        except:
            send_keyboard(token,chat_id,"❌ Відкрити 14:00 26.03",[["🏠 Вийти"]])
            return True

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

    # 🔥 ВАЖЛИВО
    return False
