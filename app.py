
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

def mark_paid(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET is_paid=1, payment_status='approved' WHERE phone=?", (phone,))
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
        "3️⃣ Mitengo\n"
        "4️⃣ Free Lesson\n"
        "5️⃣ Join Full Training\n"
        "6️⃣ Taura na Trainer\n"
        "7️⃣ Full Course (Paid)"
    )

def free_detergent():
    return (
        "🧼 *FREE DETERGENT LESSON*\n\n"
        "Ingredients:\n"
        "✔ SLES\n✔ Salt\n✔ Dye\n✔ Perfume\n✔ Water\n\n"
        "⚠ Pfeka magloves nguva dzese.\n"
        "Nyora *JOIN* kuti uwane full course."
    )

# =========================
# FULL PAID LESSONS
# =========================
LESSONS = {
    "1": "*INTRODUCTION*\n\nUnodzidza kugadzira detergents dzinotevera:\n"
         "Cobra, Thick Bleach, Pine Gel, Dishwash, Foam Bath, Laundry Soap,\n"
         "Toilet Cleaner, Fabric Softener, Petroleum Jelly.\n\n"
         "Unodzidza paWhatsApp uye unobvunza mibvunzo live.",

    "2": "*MODULE 1: SAFETY*\n\n"
         "Pfeka gloves, mask, apron.\n"
         "Shanda panofefetera.\n"
         "Chengetedza makemikari kure nevana.\n"
         "Kukuvadza vanhu nemakemikari imhosva.",

    "3": "*MODULE 2: DISHWASH (20L)*\n\n"
         "SLES 1.5kg\nSulphonic acid 1L\nCaustic soda 3 tbsp\n"
         "Soda ash 3 tbsp\nSalt 500g\nBermacol 3 tbsp\n"
         "Amido 100ml\nDye 20g\nPerfume 33ml\nWater 17.5L\n\n"
         "Mix in order, top up water, add preservative last.",

    "4": "*MODULE 3: THICK BLEACH*\n\n"
         "SLES 1.2kg\nHypochlorite 3kg\nCaustic soda 300g\nWater 15L\n\n"
         "Mix until thick. Adjust water slowly.",

    "5": "*MODULE 4: FOAM BATH*\n\n"
         "SLES 2kg\nCDE 500ml\nGlycerin 500ml\nSalt 1 cup\n"
         "Dye 20g\nFormalin 10ml\nPerfume\nAmido\n\n"
         "Mix well until smooth."
}

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    phone = request.form.get("From", "").replace("whatsapp:", "")
    msg = request.form.get("Body", "").strip().lower()

    if not phone or not msg:
        return jsonify({"status": "ignored"}), 200

    create_user(phone)
    user = get_user(phone)

    if msg in ["menu", "hi", "hello", "start"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # PAYMENT
    if msg == "pay":
        send_message(
            phone,
            "💳 *PAYMENT*\nAmount: $10\nEcoCash: 0773 208904\nName: Beloved Nkomo\n"
            "Send proof after payment."
        )
        return jsonify({"status": "ok"})

    if msg.startswith("approve "):
        target = msg.replace("approve ", "").strip()
        mark_paid(target)
        send_message(target, "✅ Payment approved. Full access granted.")
        return jsonify({"status": "ok"})

    # MAIN MENU
    if user["state"] == "main":
        if msg == "4":
            send_message(phone, free_detergent())
        elif msg in ["5", "join"]:
            send_message(phone, "Nyora PAY kuti ubhadhare.")
        elif msg == "6":
            send_message(phone, "📞 Trainer: 0773 208904")
        elif msg == "7":
            if user["is_paid"]:
                set_state(phone, "lesson_menu")
                send_message(
                    phone,
                    "📚 *FULL COURSE MODULES*\n"
                    "1️⃣ Introduction\n"
                    "2️⃣ Safety\n"
                    "3️⃣ Dishwash\n"
                    "4️⃣ Thick Bleach\n"
                    "5️⃣ Foam Bath\n\n"
                    "Reply with number"
                )
            else:
                send_message(phone, "🔒 Paid members only. Nyora PAY.")
        else:
            send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # LESSON MENU
    if user["state"] == "lesson_menu":
        if not user["is_paid"]:
            send_message(phone, "🔒 Access denied. Nyora PAY.")
        elif msg in LESSONS:
            send_message(phone, LESSONS[msg])
            send_message(phone, "Nyora MENU kudzokera kumusoro.")
        else:
            send_message(phone, "Sarudza module number kana MENU.")
        return jsonify({"status": "ok"})

    return jsonify({"status": "ok"})

@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
































