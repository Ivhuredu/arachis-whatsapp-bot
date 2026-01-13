

from flask import Flask, request, jsonify
from twilio.rest import Client
import sqlite3, os

app = Flask(__name__)

# =========================
# CONFIG
# =========================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

ADMIN_NUMBER = "263773208904"  # admin WhatsApp number (no prefix)

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
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{phone}",
        body=text
    )

def send_pdf(phone, pdf_url, caption):
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{phone}",
        body=caption,
        media_url=[pdf_url]
    )

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

def free_lesson():
    return (
        "🎁 *FREE LESSON*\n\n"
        "Dishwash basics:\n"
        "✔ SLES\n✔ Salt\n✔ Dye\n✔ Perfume\n✔ Mvura\n\n"
        "⚠ Pfeka magloves, mask ne apron."
    )

# =========================
# AI FAQ (RETAINS YOUR FAQ)
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

    # -------------------------
    # AI FAQ
    # -------------------------
    faq = ai_faq_reply(incoming)
    if faq and incoming not in ["1","2","3","4","5","6","menu","pay","join","admin"]:
        send_message(phone, faq)
        return jsonify({"status": "ok"})

    # -------------------------
    # ADMIN DASHBOARD
    # -------------------------
    if incoming == "admin" and phone == ADMIN_NUMBER:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_paid=1")
        paid = c.fetchone()[0]
        conn.close()

        send_message(
            phone,
            f"📊 *ADMIN DASHBOARD*\n\n"
            f"👥 Users: {total}\n"
            f"💰 Paid: {paid}"
        )
        return jsonify({"status": "ok"})

    if incoming.startswith("approve ") and phone == ADMIN_NUMBER:
        target = incoming.replace("approve ", "").strip()
        mark_paid(target)
        send_message(target, "🎉 Payment Approved!\nYou now have full access.")
        send_message(phone, f"✅ Approved: {target}")
        return jsonify({"status": "ok"})

    # -------------------------
    # GLOBAL COMMANDS
    # -------------------------
    if incoming in ["menu", "start"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    if incoming == "pay":
        set_payment_status(phone, "waiting_proof")
        send_message(phone, "💳 Pay $10 to 0773 208904\nSend proof here.")
        return jsonify({"status": "ok"})

    # -------------------------
    # MAIN MENU
    # -------------------------
    if user["state"] == "main":

        if incoming == "1":
            set_state(phone, "detergent_menu")
            send_message(
                phone,
                "🧼 *DETERGENTS – PAID LESSONS*\n\n"
                "1️⃣ Dishwash\n"
                "2️⃣ Thick Bleach\n"
                "3️⃣ Foam Bath\n"
                "4️⃣ Pine Gel\n\n"
                "Nyora *MENU* kudzokera kumusoro"
            )
            return jsonify({"status": "ok"})

        if incoming == "2":
            send_message(phone, "🥤 Concentrate Drinks module coming soon.")
            return jsonify({"status": "ok"})

        if incoming == "3":
            send_message(phone, "💵 Full training: $10 once-off\nNyora *PAY*")
            return jsonify({"status": "ok"})

        if incoming == "4":
            send_message(phone, free_lesson())
            return jsonify({"status": "ok"})

        if incoming == "5":
            send_message(phone, "📝 Join full training — Nyora *PAY*")
            return jsonify({"status": "ok"})

        if incoming == "6":
            send_message(phone, "📞 Trainer: 0773 208904")
            return jsonify({"status": "ok"})

    # -------------------------
    # DETERGENT MENU (STEP A)
    # -------------------------
    if user["state"] == "detergent_menu":

        if not user["is_paid"]:
            send_message(
                phone,
                "🔒 *Paid Members Only*\n\n"
                "Full detergent course: $10\n"
                "Nyora *PAY* kuti ubhadhare."
            )
            return jsonify({"status": "ok"})

        if incoming == "1":
            send_pdf(
                phone,
                "https://arachis-whatsapp-bot-2.onrender.com/static/lessons/dishwash.pdf",
                "🧼 MODULE: DISHWASH"
            )
            return jsonify({"status": "ok"})

        if incoming == "2":
            send_pdf(
                phone,
                "https://arachis-whatsapp-bot-2.onrender.com/static/lessons/thick_bleach.pdf",
                "🧴 MODULE: THICK BLEACH"
            )
            return jsonify({"status": "ok"})

        if incoming == "3":
            send_message(phone, "📘 Foam Bath PDF coming soon.")
            return jsonify({"status": "ok"})

        if incoming == "4":
            send_message(phone, "📘 Pine Gel PDF coming soon.")
            return jsonify({"status": "ok"})

    send_message(phone, "Nyora *MENU*")
    return jsonify({"status": "ok"})

# =========================
# HEALTH CHECK
# =========================
@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))












































