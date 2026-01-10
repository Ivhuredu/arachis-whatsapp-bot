
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
    c.execute("UPDATE users SET is_paid=1, payment_status='approved' WHERE phone=?", (phone,))
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
        "Sarudza zvauri kuda 👇🏽\n"
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
        "⚠ Pfeka magloves, mask ne apron.\n\n"
        "Nyora *JOIN* kuti uwane full course."
    )

def free_drink():
    return (
        "🥤 *FREE DRINK LESSON*\n\n"
        "✔ Citric Acid\n✔ Colour\n✔ Flavour\n✔ Sugar\n✔ Mvura\n\n"
        "⚠ Pfeka magloves, mask ne apron.\n\n"
        "Nyora *JOIN* kuti uwane full course."
    )

# =========================
# AI FAQ (RULE-BASED)
# =========================
def ai_faq_reply(msg):
    msg = msg.lower()

    if any(k in msg for k in ["price", "cost", "fee", "marii"]):
        return "💵 *Full Training Fee*\n$10 once-off\nNyora *PAY* kuti ubhadhare."

    if any(k in msg for k in ["how long", "duration", "nguva"]):
        return "⏳ Une *lifetime access* — hapana expiry."

    if "certificate" in msg:
        return "🎓 Ehe — unowana certificate mushure mekupedza."

    if any(k in msg for k in ["where", "location", "kupi"]):
        return "📍 Tiri ku Mataga, Zimbabwe — asi training ndeye online."

    if any(k in msg for k in ["thanks", "thank you", "tatenda"]):
        return "🙏 Tatenda!"

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
    # SYSTEM COMMANDS (skip AI)
    # -------------------------
    system_commands = ["menu", "start", "pay", "join", "1", "2", "3", "4", "5", "6"]

    if incoming not in system_commands:
        faq = ai_faq_reply(incoming)
        if faq:
            send_message(phone, faq)
            return jsonify({"status": "ok"})

    # -------------------------
    # ADMIN APPROVAL
    # -------------------------
    if incoming.startswith("approve "):
        target = incoming.replace("approve ", "").strip()
        mark_paid(target)
        send_message(target, "🎉 *Payment Approved!*\nYou now have full access.")
        send_message(phone, "✅ User approved")
        return jsonify({"status": "ok"})

    # -------------------------
    # RESET
    # -------------------------
    if incoming in ["menu", "start", "hi", "hello"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # -------------------------
    # PAYMENT
    # -------------------------
    if incoming == "pay":
        set_payment_status(phone, "waiting_proof")
        send_message(
            phone,
            "💳 *ECOCASH PAYMENT*\n\n"
            "Amount: $10\n"
            "Number: 0773 208904\n"
            "Name: Beloved Nkomo\n\n"
            "📸 Tumira proof pano."
        )
        return jsonify({"status": "ok"})

    if user["payment_status"] == "waiting_proof" and len(incoming) > 5:
        set_payment_status(phone, "pending_approval")
        send_message(phone, "✅ Proof yatambirwa. Tichakuzivisai.")
        return jsonify({"status": "ok"})

    # -------------------------
    # MAIN MENU
    # -------------------------
    if user["state"] == "main":

        if incoming == "1":
            set_state(phone, "detergent_menu")
            send_message(phone, "🧼 1️⃣ Free lesson\n2️⃣ Paid full course")
            return jsonify({"status": "ok"})

        if incoming == "2":
            set_state(phone, "drink_menu")
            send_message(phone, "🥤 1️⃣ Free lesson\n2️⃣ Paid full course")
            return jsonify({"status": "ok"})

        if incoming == "3":
            send_message(phone, "💵 Full training: $10 once-off")
            return jsonify({"status": "ok"})

        if incoming == "4":
            send_message(phone, free_detergent())
            return jsonify({"status": "ok"})

        if incoming in ["5", "join"]:
            send_message(phone, "Nyora *PAY* kuti ubhadhare 👍")
            return jsonify({"status": "ok"})

        if incoming == "6":
            send_message(phone, "📞 Trainer: 0773 208904")
            return jsonify({"status": "ok"})

    # -------------------------
    # SUB MENUS
    # -------------------------
    if user["state"] == "detergent_menu":
        if incoming == "1":
            send_message(phone, free_detergent())
        elif incoming == "2":
            if user["is_paid"]:
                send_message(phone, "🧼 Dishwash, Foam bath, Bleach, Pine gel")
            else:
                send_message(phone, "🔒 Paid only — Nyora *PAY*")
        return jsonify({"status": "ok"})

    if user["state"] == "drink_menu":
        if incoming == "1":
            send_message(phone, free_drink())
        elif incoming == "2":
            if user["is_paid"]:
                send_message(phone, "🥤 Concentrates, Soft drinks, Mawuyu")
            else:
                send_message(phone, "🔒 Paid only — Nyora *PAY*")
        return jsonify({"status": "ok"})

    send_message(phone, "Nyora *MENU* kuti utange zvakare")
    return jsonify({"status": "ok"})

@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))








































