from flask import Flask, request, jsonify
from twilio.rest import Client
import sqlite3, os

app = Flask(__name__)

# =========================
# TWILIO CONFIG
# =========================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

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
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        state TEXT DEFAULT 'main',
        payment_status TEXT DEFAULT 'none',
        is_paid INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

init_db()

def mark_paid(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_paid=1, payment_status='approved' WHERE phone=?",
        (phone,)
    )
    conn.commit()
    conn.close()

# =========================
# HELPERS
# =========================
def send_message(phone, text):
    try:
        client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{phone}",
            body=text
        )
    except Exception as e:
        print("SEND ERROR:", e)

def send_pdf(phone, pdf_url, caption):
    try:
        client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{phone}",
            body=caption,
            media_url=[pdf_url]
        )
    except Exception as e:
        print("PDF SEND ERROR:", e)

def get_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE phone=?", (phone,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (phone) VALUES (?)", (phone,))
    conn.commit()
    conn.close()

def set_state(phone, state):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET state=? WHERE phone=?", (state, phone))
    conn.commit()
    conn.close()

def set_payment_status(phone, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET payment_status=? WHERE phone=?", (status, phone))
    conn.commit()
    conn.close()

# =========================
# MENUS
# =========================
def main_menu():
    return (
        "👋 *TINOKUGAMUCHIRAI KU ARACHIS ONLINE TRAINING*\n\n"
        "1️⃣ Detergents\n"
        "2️⃣ Concentrate Drinks\n"
        "3️⃣ Mitengo & Kubhadhara\n"
        "4️⃣ Free Lesson\n"
        "5️⃣ Join Full Training\n"
        "6️⃣ Taura na Trainer"
    )

def free_detergent():
    return (
        "🧼 *FREE DETERGENT LESSON*\n\n"
        "Dishwash basics:\n"
        "✔ SLES\n✔ Salt\n✔ Dye\n✔ Perfume\n✔ Mvura\n\n"
        "⚠ Pfeka magloves, mask ne apron."
    )

def free_drink():
    return (
        "🥤 *FREE DRINK LESSON*\n\n"
        "✔ Citric Acid\n✔ Colour\n✔ Flavour\n✔ Sugar\n✔ Mvura"
    )

# =========================
# AI FAQ
# =========================
def ai_faq_reply(msg):
    if any(k in msg for k in ["price", "cost", "fee", "marii"]):
        return "💵 Full training: $10 once-off\nNyora *PAY*"
    if "certificate" in msg:
        return "🎓 Ehe — unowana certificate."
    return None

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    phone = request.form.get("From", "").replace("whatsapp:", "")
    incoming = request.form.get("Body", "").strip().lower()

    if not phone or not incoming:
        return jsonify({"status": "ignored"}), 200

    create_user(phone)
    user = get_user(phone)

    # AI FAQ (ignore menu commands)
    if incoming not in ["1","2","3","4","5","6","pay","menu","join","start"]:
        faq = ai_faq_reply(incoming)
        if faq:
            send_message(phone, faq)
            return jsonify({"status": "ok"})

    # ADMIN APPROVAL
    if incoming.startswith("approve "):
        target = incoming.replace("approve ", "").strip()
        mark_paid(target)
        send_message(target, "🎉 *Payment Approved!*\nYou now have full access.")
        return jsonify({"status": "ok"})

    # RESET
    if incoming in ["menu", "start"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # PAYMENT
    if incoming == "pay":
        set_payment_status(phone, "waiting_proof")
        send_message(phone, "💳 Pay $10 to 0773 208904\nSend proof here.")
        return jsonify({"status": "ok"})

    # =========================
    # MAIN MENU HANDLER (FIXED)
    # =========================
    if user["state"] == "main":

        if incoming == "1":
            set_state(phone, "detergent_menu")
            send_message(phone, "🧼 1️⃣ Free lesson\n2️⃣ Paid lessons")
            return jsonify({"status": "ok"})

        if incoming == "2":
            send_message(phone, "🥤 Concentrate drinks coming soon.")
            return jsonify({"status": "ok"})

        if incoming == "3":
            send_message(phone, "💵 Full training: $10 once-off")
            return jsonify({"status": "ok"})

        if incoming == "4":
            send_message(phone, free_detergent())
            return jsonify({"status": "ok"})

        if incoming == "5":
            send_message(phone, "👉 Nyora *PAY* kuti ubhadhare")
            return jsonify({"status": "ok"})

        if incoming == "6":
            send_message(phone, "📞 Trainer: 0773 208904")
            return jsonify({"status": "ok"})

    # =========================
    # DETERGENT MENU
    # =========================
    if user["state"] == "detergent_menu":

        if incoming == "1":
            send_message(phone, free_detergent())
            return jsonify({"status": "ok"})

        if incoming == "2":
            if user["is_paid"]:
                send_pdf(
                    phone,
                    "https://arachis-whatsapp-bot-2.onrender.com/static/lessons/dishwash.pdf",
                    "🧼 *MODULE 2: DISHWASH*"
                )
                send_pdf(
                    phone,
                    "https://arachis-whatsapp-bot-2.onrender.com/static/lessons/thick_bleach.pdf",
                    "🧴 *MODULE 3: THICK BLEACH*"
                )
            else:
                send_message(phone, "🔒 Paid only — Nyora *PAY*")
            return jsonify({"status": "ok"})

    send_message(phone, "Nyora *MENU*")
    return jsonify({"status": "ok"})

@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))












































