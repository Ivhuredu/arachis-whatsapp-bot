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

# =========================
# FREE LESSONS
# =========================
def free_detergent():
    return (
        "🧼 *FREE DETERGENT LESSON*\n\n"
        "Dishwash basics\n"
        "✔ SLES\n✔ Salt\n✔ Dye\n✔ Perfume\n✔ Mvura\n\n"
        "⚠ Pfeka magloves, mask & apron\n\n"
        "Nyora *JOIN* kuti uwane maformula akazara."
    )

def free_drink():
    return (
        "🥤 *FREE DRINK LESSON*\n\n"
        "✔ Raspberry\n✔ Lemon\n✔ Orange\n\n"
        "Zvinodiwa: Citric acid, flavour, sugar, mvura\n\n"
        "Nyora *JOIN* kuti uwane zvidzidzo zvese."
    )

# =========================
# FULL PAID LESSON (MODULES)
# =========================
def full_detergent_course():
    return (
        "🎓 *ARACHIS ONLINE TRAINING – FULL COURSE*\n\n"
        "MODULE 1: SAFETY & SETUP\n"
        "✔ Buckets eplastic\n✔ Measuring scale\n✔ Gloves, goggles, mask\n"
        "✔ Ventilation yakakwana\n\n"
        "MODULE 2: DISHWASH (20L)\n"
        "SLES 1.5kg\nSulphonic 1L\nCaustic soda 3 tbsp\n"
        "Soda ash 3 tbsp\nSalt 500g\nBermacol 3 tbsp\n"
        "Amido 100ml\nPerfume 33ml\nDye 20g\n"
        "Mvura 17.5L\n\n"
        "MODULE 3: THICK BLEACH\n"
        "SLES 1.2kg\nHypochlorite 3kg\nCaustic soda 300g\n"
        "Mvura 15L\n\n"
        "MODULE 4: FOAM BATH\n"
        "SLES 2kg\nCDE 500ml\nGlycerin 500ml\n"
        "Salt 1 cup\nDye 20g\nFormalin 10ml\nPerfume\nAmido\n\n"
        "📞 Unogona kubvunza mibvunzo chero nguva pano."
    )

def full_drinks_course():
    return (
        "🥤 *FULL DRINKS TRAINING*\n\n"
        "✔ Cordials\n✔ Concentrates\n✔ Mawuyu drink\n\n"
        "Zvinodiwa:\n"
        "Citric acid\nFlavour\nColour\nSugar\nPreservatives\n\n"
        "📦 Packaging & storage guidance\n"
        "📞 Support iripo paWhatsApp"
    )

# =========================
# AI FAQ (TEXT ONLY)
# =========================
def ai_faq_reply(msg):
    if msg.isdigit():
        return None

    if "price" in msg or "marii" in msg:
        return "💵 Full course inoita *$10 once-off*. Nyora *PAY* kuti ubhadhare."

    if "certificate" in msg:
        return "🎓 Certificate inopihwa mushure mekupedza course."

    if "location" in msg or "kupi" in msg:
        return "📍 Training ndeye online paWhatsApp — unodzidza chero kwauri."

    return None

# =========================
# HEALTH CHECK
# =========================
@app.route("/ping")
def ping():
    return "OK", 200

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

    # AI FAQ (text only)
    faq = ai_faq_reply(incoming)
    if faq:
        send_message(phone, faq)
        return jsonify({"status": "ok"})

    # ADMIN APPROVAL
    if incoming.startswith("approve "):
        target = incoming.replace("approve ", "").strip()
        mark_paid(target)
        send_message(target, "🎉 Payment approved. Full access granted.")
        return jsonify({"status": "ok"})

    # RESET
    if incoming in ["menu", "start", "hi", "hello"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # PAY
    if incoming == "pay":
        set_payment_status(phone, "waiting_proof")
        send_message(
            phone,
            "💳 *ECOCASH PAYMENT*\nAmount: $10\nNumber: 0773 208904\n"
            "Name: Beloved Nkomo\n📸 Tumira proof pano."
        )
        return jsonify({"status": "ok"})

    if user["payment_status"] == "waiting_proof":
        set_payment_status(phone, "pending_approval")
        send_message(phone, "✅ Proof yatambirwa. Mirira approval.")
        return jsonify({"status": "ok"})

    # MAIN MENU
    if user["state"] == "main":
        if incoming == "1":
            set_state(phone, "detergent_menu")
            send_message(phone, "1️⃣ Free lesson\n2️⃣ Paid full course")
            return jsonify({"status": "ok"})

        if incoming == "2":
            set_state(phone, "drink_menu")
            send_message(phone, "1️⃣ Free lesson\n2️⃣ Paid full course")
            return jsonify({"status": "ok"})

        if incoming == "3":
            send_message(phone, "💵 Full training: *$10 once-off*")
            return jsonify({"status": "ok"})

        if incoming == "4":
            send_message(phone, free_detergent())
            return jsonify({"status": "ok"})

        if incoming == "5":
            send_message(phone, "Nyora *PAY* kuti ubhadhare")
            return jsonify({"status": "ok"})

        if incoming == "6":
            send_message(phone, "📞 Trainer: 0773 208904")
            return jsonify({"status": "ok"})

    # SUB MENUS
    if user["state"] == "detergent_menu":
        if incoming == "1":
            send_message(phone, free_detergent())
        elif incoming == "2":
            send_message(phone, full_detergent_course() if user["is_paid"] else "🔒 Nyora PAY")
        return jsonify({"status": "ok"})

    if user["state"] == "drink_menu":
        if incoming == "1":
            send_message(phone, free_drink())
        elif incoming == "2":
            send_message(phone, full_drinks_course() if user["is_paid"] else "🔒 Nyora PAY")
        return jsonify({"status": "ok"})

    send_message(phone, "Nyora MENU")
    return jsonify({"status": "ok"})

# =========================
# HOME + PORT (RENDER FIX)
# =========================
@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)




































