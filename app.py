from flask import Flask, request, jsonify
import requests
import sqlite3
import os

app = Flask(__name__)

VERIFY_TOKEN = "arachis-arachisbot-2025"
WHATSAPP_TOKEN = "PASTE_YOUR_USER_ACCESS_TOKEN_HERE"
WHATSAPP_PHONE_ID = "PASTE_YOUR_PHONE_NUMBER_ID_HERE"

# =========================
# DATABASE
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
# HELPERS
# =========================
def send_message(phone, text):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text}
    }

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    requests.post(url, json=payload, headers=headers)


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
# MENUS
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
# WHATSAPP WEBHOOK VERIFY
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
# WHATSAPP MESSAGE HANDLER
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.json

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = message["from"]
        incoming = message["text"]["body"].strip().lower()
    except:
        return jsonify({"status": "ignored"}), 200

    create_user(phone)
    user = get_user(phone)

    # Reset
    if incoming in ["menu", "start", "hi", "hello", "makadini"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # Payment
    if incoming == "pay":
        set_payment_status(phone, "waiting_proof")
        send_message(
            phone,
            "💳 *ECOCASH PAYMENT*\n\nAmount: $5\nNumber: 0773 208904\nName: Beloved Nkomo\n\n📸 Tumira proof pano."
        )
        return jsonify({"status": "ok"})

    if user["payment_status"] == "waiting_proof":
        set_payment_status(phone, "pending_approval")
        send_message(phone, "✅ Proof yatambirwa. Mirira kusimbiswa ⏳")
        return jsonify({"status": "ok"})

    # Main Menu Logic
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

    return jsonify({"status": "ok"})


@app.route("/", methods=["GET"])
def home():
    return "Arachis WhatsApp Cloud Bot Running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))















