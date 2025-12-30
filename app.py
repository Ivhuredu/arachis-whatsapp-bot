
from flask import Flask, request, jsonify
from twilio.rest import Client
import sqlite3
import os

app = Flask(__name__)

# =========================
# TWILIO CONFIG
# =========================
TWILIO_ACCOUNT_SID = os.getenv("AC15ba4e65e4d435d3cc06b847509e7085")
TWILIO_AUTH_TOKEN = os.getenv("81f0091b8de6a2043013b570935dacd6")
TWILIO_WHATSAPP_NUMBER = os.getenv("whatsapp:+14155238886
")  # e.g whatsapp:+14155238886

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


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
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{phone}",
        body=text
    )


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
# HEALTH CHECK
# =========================
@app.route("/ping", methods=["GET"])
def ping():
    return "OK", 200


# =========================
# TWILIO WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    # numbers from Twilio come like whatsapp:+2637xxxx
    phone = request.form.get("From", "").replace("whatsapp:", "")
    incoming = request.form.get("Body", "").strip().lower()

    if not phone or not incoming:
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
            "💳 *ECOCASH PAYMENT*\n\n"
            "Amount: $5\n"
            "Number: 0773 208904\n"
            "Name: Beloved Nkomo\n\n"
            "📸 Tumira proof pano."
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
    return "Arachis WhatsApp Bot (Twilio) Running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))




















