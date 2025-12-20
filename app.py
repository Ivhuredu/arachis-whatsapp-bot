

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import sqlite3
import os

app = Flask(__name__)

# =========================
# DATABASE SETUP (SQLite)
# =========================

def get_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        is_paid INTEGER DEFAULT 0,
        detergent_lesson INTEGER DEFAULT 0,
        drink_lesson INTEGER DEFAULT 0,
        state TEXT DEFAULT 'main'
    )
    """)
    conn.commit()
    conn.close()

init_db()

# =========================
# USER HELPERS
# =========================

def get_user(phone):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE phone=?", (phone,))
    user = cur.fetchone()
    conn.close()
    return user

def create_user(phone):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (phone) VALUES (?)", (phone,))
    conn.commit()
    conn.close()

def set_state(phone, state):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET state=? WHERE phone=?", (state, phone))
    conn.commit()
    conn.close()

def mark_paid(phone):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_paid=1 WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

# =========================
# MENUS & CONTENT
# =========================

def main_menu():
    return (
        "👋 *ARACHIS ONLINE TRAINING*\n\n"
        "Sarudza 👇🏽\n"
        "1️⃣ Detergents\n"
        "2️⃣ Concentrate Drinks\n"
        "3️⃣ Mitengo & Kubhadhara\n"
        "4️⃣ Free Lesson\n"
        "5️⃣ Join Full Training\n"
        "6️⃣ Bata Trainer"
    )

def free_detergent():
    return (
        "🧼 *FREE LESSON*\n\n"
        "Dishwash inogadzirwa ne:\n"
        "• Water\n• SLES\n• Salt\n• Fragrance\n\n"
        "Nyora *JOIN* kuti uwane full formulas."
    )

def free_drink():
    return (
        "🥤 *FREE DRINK LESSON*\n\n"
        "Concentrate drinks anosanganiswa nemvura.\n"
        "Akanakira bhizinesi.\n\n"
        "Nyora *JOIN* kuti uwane full formulas."
    )

# =========================
# LESSON LOGIC
# =========================

def next_detergent_lesson(user):
    day = user["detergent_lesson"] + 1
    lessons = {
        1: "📘 Detergent Lesson 1\nSafety & Equipment",
        2: "📘 Detergent Lesson 2\nDishwash Formula",
        3: "📘 Detergent Lesson 3\nFoam Bath Formula",
        4: "📘 Detergent Lesson 4\nPine Gel Formula"
    }

    if day not in lessons:
        return None

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET detergent_lesson=? WHERE phone=?",
        (day, user["phone"])
    )
    conn.commit()
    conn.close()

    return lessons[day]

def next_drink_lesson(user):
    day = user["drink_lesson"] + 1
    lessons = {
        1: "🥤 Drink Lesson 1\nIngredients & Brix",
        2: "🥤 Drink Lesson 2\nMixing Method",
        3: "🥤 Drink Lesson 3\nPreservation",
        4: "🥤 Drink Lesson 4\nPackaging & Pricing"
    }

    if day not in lessons:
        return None

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET drink_lesson=? WHERE phone=?",
        (day, user["phone"])
    )
    conn.commit()
    conn.close()

    return lessons[day]

# =========================
# ROUTES
# =========================

@app.route("/", methods=["GET"])
def home():
    return "Arachis WhatsApp Bot Running"

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming = request.values.get("Body", "").strip().lower()
    phone = request.values.get("From")

    resp = MessagingResponse()
    msg = resp.message()

    create_user(phone)
    user = get_user(phone)

    # RESET
    if incoming in ["menu", "start", "hi", "hello", "makadini"]:
        set_state(phone, "main")
        msg.body(main_menu())
        return str(resp)

    # =========================
    # MAIN MENU
    # =========================
    if user["state"] == "main":

        if incoming == "1":
            set_state(phone, "detergent_menu")
            msg.body("🧼 Detergents\n1️⃣ Free\n2️⃣ Paid")

        elif incoming == "2":
            set_state(phone, "drink_menu")
            msg.body("🥤 Drinks\n1️⃣ Free\n2️⃣ Paid")

        elif incoming == "3":
            msg.body("💵 Mari: $5\nEcoCash: 0773 208904\nNyora PAY")

        elif incoming == "4":
            msg.body(free_detergent())

        elif incoming in ["5", "join"]:
            msg.body("Bhadhara $5 wobva watumira proof pano.")

        elif incoming == "6":
            msg.body("📞 Trainer: 0773 208904")

        else:
            msg.body("Nyora MENU")

    # =========================
    # DETERGENT MENU
    # =========================
    elif user["state"] == "detergent_menu":

        if incoming == "1":
            msg.body(free_detergent())

        elif incoming == "2":
            if user["is_paid"] == 1:
                set_state(phone, "detergent_lessons")
                msg.body("Nyora LESSON kuti utange")
            else:
                msg.body("🔒 Bhadhara kuti uwane full access")

    # =========================
    # DRINK MENU
    # =========================
    elif user["state"] == "drink_menu":

        if incoming == "1":
            msg.body(free_drink())

        elif incoming == "2":
            if user["is_paid"] == 1:
                set_state(phone, "drink_lessons")
                msg.body("Nyora DRINK kuti utange")
            else:
                msg.body("🔒 Bhadhara kuti uwane full access")

    # =========================
    # LESSON STATES
    # =========================
    elif user["state"] == "detergent_lessons" and incoming == "lesson":
        lesson = next_detergent_lesson(user)
        msg.body(lesson if lesson else "🎉 Wapedza detergent lessons")

    elif user["state"] == "drink_lessons" and incoming == "drink":
        lesson = next_drink_lesson(user)
        msg.body(lesson if lesson else "🎉 Wapedza drink lessons")

    # =========================
    # ADMIN – MARK PAID
    # =========================
    elif incoming.startswith("addpaid") and phone == "whatsapp:+263773208904":
        number = incoming.replace("addpaid", "").strip()
        mark_paid(number)
        msg.body(f"✅ {number} now PAID")

    else:
        msg.body("Nyora MENU")

    return str(resp)

# =========================
# RUN
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)








