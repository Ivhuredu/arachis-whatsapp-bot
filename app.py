from flask import Flask, request, jsonify
import requests
import sqlite3
import os

app = Flask(__name__)

# =========================
# WHATSAPP CLOUD API CONFIG
# =========================

VERIFY_TOKEN = "arachis-arachisbot-2025"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")


# =========================
# SEND MESSAGE FUNCTION
# =========================

def send_message(phone, text):
    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "to": phone.replace("whatsapp:", "").replace("+", ""),
        "type": "text",
        "text": {"body": text}
    }

    requests.post(url, headers=headers, json=data)


# =========================
# DATABASE SETUP
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
        payment_status TEXT DEFAULT 'none',
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

def set_payment_status(phone, status):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET payment_status=? WHERE phone=?", (status, phone))
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
# HEALTH CHECK
# =========================

@app.route("/", methods=["GET"])
def home():
    return "Arachis WhatsApp Bot Running"


# =========================
# WEBHOOK VERIFICATION (GET)
# =========================

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification failed", 403


# =========================
# WEBHOOK MESSAGES (POST)
# =========================

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = message["from"]
        incoming = message["text"]["body"].strip().lower()

    except Exception:
        return jsonify({"status": "ignored"}), 200

    create_user(phone)
    user = get_user(phone)

    # RESET / MENU
    if incoming in ["menu", "start", "hi", "hello", "makadini"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"}), 200

    # PAYMENT FLOW
    if incoming == "pay":
        set_payment_status(phone, "waiting_proof")
        send_message(
            phone,
            "💳 *ECOCASH PAYMENT*\n\nAmount: $5\nNumber: 0773 208904\nName: Beloved Nkomo\n\n📸 Tumira payment proof pano."
        )
        return jsonify({"status": "ok"}), 200

    if user["payment_status"] == "waiting_proof":
        set_payment_status(phone, "pending_approval")
        send_message(phone, "✅ Proof yatambirwa.\nMirira kusimbiswa ⏳")
        return jsonify({"status": "ok"}), 200

    # MAIN MENU HANDLING
    if user["state"] == "main":

        if incoming == "1":
            set_state(phone, "detergent_menu")
            send_message(phone, "🧼 Detergents\n1️⃣ Free\n2️⃣ Paid")

        elif incoming == "2":
            set_state(phone, "drink_menu")
            send_message(phone, "🥤 Drinks\n1️⃣ Free\n2️⃣ Paid")

        elif incoming == "3":
            send_message(phone, "💵 Mari: $5\nNyora PAY kuti ubhadhare")

        elif incoming == "4":
            send_message(phone, free_detergent())

        elif incoming in ["5", "join"]:
            send_message(phone, "Nyora PAY kuti utange kubhadhara")

        elif incoming == "6":
            send_message(phone, "📞 Trainer: 0773 208904")

        else:
            send_message(phone, "Nyora MENU")

    # DETERGENT MENU
    elif user["state"] == "detergent_menu":

        if incoming == "1":
            send_message(phone, free_detergent())

        elif incoming == "2":
            if user["is_paid"] == 1:
                set_state(phone, "detergent_lessons")
                send_message(phone, "Nyora LESSON kuti utange")
            else:
                send_message(phone, "🔒 Bhadhara kuti uwane full access")

    # DRINK MENU
    elif user["state"] == "drink_menu":

        if incoming == "1":
            send_message(phone, free_drink())

        elif incoming == "2":
            if user["is_paid"] == 1:
                set_state(phone, "drink_lessons")
                send_message(phone, "Nyora DRINK kuti utange")
            else:
                send_message(phone, "🔒 Bhadhara kuti uwane full access")

    # LESSON STATES
    elif user["state"] == "detergent_lessons" and incoming == "lesson":
        lesson = next_detergent_lesson(user)
        send_message(phone, lesson if lesson else "🎉 Wapedza detergent lessons")

    elif user["state"] == "drink_lessons" and incoming == "drink":
        lesson = next_drink_lesson(user)
        send_message(phone, lesson if lesson else "🎉 Wapedza drink lessons")

    # ADMIN APPROVAL
    elif incoming.startswith("addpaid") and phone.endswith("263773208904"):
        number = incoming.replace("addpaid", "").strip()
        mark_paid(number)
        set_payment_status(number, "approved")
        send_message(phone, f"✅ {number} APPROVED")

    else:
        send_message(phone, "Nyora MENU")

    return jsonify({"status": "ok"}), 200


# =========================
# RUN
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)











