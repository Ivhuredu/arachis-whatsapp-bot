

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
        payment_status TEXT DEFAULT 'none'
    )
    """)
    conn.commit()
    conn.close()

init_db()


# ensure paid field exists
def ensure_paid_column():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA table_info(users)")
    cols = [row["name"] for row in c.fetchall()]
    if "is_paid" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN is_paid INTEGER DEFAULT 0")
        conn.commit()
    conn.close()

ensure_paid_column()


def mark_paid(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET is_paid=1 WHERE phone=?", (phone,))
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
        "Dishwash formula basics\n\n"
        "Kuti ugadzire Dishwash panodiwa:\n"
        "✔ SLES\n✔ Salt\n✔ Dye\n✔ Perfume\n✔ Mvura\n\n"
        "⚠ Chengetedzo:\n"
        "Pfeka gloves, mask uye apron paunenge uchishanda.\n\n"
        "Nyora *JOIN* kuti uwane maformula akazara."
    )


def free_drink():
    return (
        "🥤 *FREE DRINK LESSON*\n\n"
        "Concentrate drinks basics\n\n"
        "Madrinks anogadzirwa anosanganisira:\n"
        "✔ Raspberry\n✔ Lemon & Lime\n✔ Orange\n✔ Blackberry\n\n"
        "Zvinodiwa:\n"
        "✔ Citric Acid\n✔ Color\n✔ Flavour\n✔ Sugar\n✔ Mvura\n\n"
        "⚠ Gara wakapfeka gloves, mask ne apron — mishonga inogona kukuvadza.\n\n"
        "Nyora *JOIN* kuti uwane maformula akazara."
    )


# =========================
# HEALTH CHECK
# =========================
@app.route("/ping")
def ping():
    return "OK", 200


# =========================
# WHATSAPP WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    phone = request.form.get("From", "").replace("whatsapp:", "")
    incoming = request.form.get("Body", "").strip().lower()

    if not phone or not incoming:
        return jsonify({"status": "ignored"}), 200

    create_user(phone)
    user = get_user(phone)

    if not user:
        set_state(phone, "main")

    # =========================
    # ADMIN PAYMENT APPROVAL
    # =========================
    if incoming.startswith("approve "):
        target = incoming.replace("approve ", "").strip()
        mark_paid(target)
        set_payment_status(target, "approved")
        send_message(
            target,
            "🎉 *Payment Approved!*\n\n"
            "You now have FULL ACCESS to all lessons."
        )
        send_message(phone, "👍 User approved")
        return jsonify({"status": "ok"})

    # =========================
    # RESET / MAIN
    # =========================
    if incoming in ["menu", "start", "hi", "hello", "makadini"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # =========================
    # PAYMENT FLOW
    # =========================
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
        send_message(
            phone,
            "✅ Proof yatambirwa.\n"
            "Admin achakuudza kuti aona payment munguva pfupi ⏳"
        )
        return jsonify({"status": "ok"})

    # =========================
    # MAIN MENU
    # =========================
    if user["state"] == "main":

        if incoming == "1":
            set_state(phone, "detergent_menu")
            send_message(
                phone,
                "🧼 *DETERGENTS LESSONS*\n"
                "1️⃣ Free lesson\n"
                "2️⃣ Paid full course"
            )
            return jsonify({"status": "ok"})

        if incoming == "2":
            set_state(phone, "drink_menu")
            send_message(
                phone,
                "🥤 *DRINKS LESSONS*\n"
                "1️⃣ Free lesson\n"
                "2️⃣ Paid full course"
            )
            return jsonify({"status": "ok"})

        if incoming == "3":
            send_message(
                phone,
                "💵 *MITENGO*\n\n"
                "Full training: $5 once off.\n"
                "👉 Kana wakatobhadhara unowana lesson dzese automatically.\n"
                "Nyora MENU kudzokera kumusoro."
            )
            return jsonify({"status": "ok"})

        if incoming == "4":
            send_message(phone, free_detergent())
            return jsonify({"status": "ok"})

        if incoming in ["5", "join"]:
            send_message(phone, "To join full training nyora *PAY* 👍")
            return jsonify({"status": "ok"})

        if incoming == "6":
            send_message(phone, "📞 Trainer: 0773 208904")
            return jsonify({"status": "ok"})

        send_message(phone, "Nyora *MENU* kuti utange zvakare")
        return jsonify({"status": "ok"})


    # =========================
    # DETERGENTS SUB MENU
    # =========================
    if user["state"] == "detergent_menu":

        if incoming == "1":
            send_message(phone, free_detergent())
            return jsonify({"status": "ok"})

        if incoming == "2":
            if user["is_paid"]:
                send_message(
                    phone,
                    "🧼 *Full Detergent Course*\n"
                    "✔ Dishwash\n✔ Foam bath\n✔ Thick bleach\n✔ Pine gel\n\n"
                    "Nyora MENU kudzokera kumusoro."
                )
            else:
                send_message(
                    phone,
                    "🔒 Lesson iyi ndeye *Paid Members Only*\n\n"
                    "Fee: $5\nNyora *PAY* kuti ubhadhare."
                )
            return jsonify({"status": "ok"})

        send_message(phone, "Sarudza 1 kana 2 kana nyora MENU")
        return jsonify({"status": "ok"})


    # =========================
    # DRINKS SUB MENU
    # =========================
    if user["state"] == "drink_menu":

        if incoming == "1":
            send_message(phone, free_drink())
            return jsonify({"status": "ok"})

        if incoming == "2":
            if user["is_paid"]:
                send_message(
                    phone,
                    "🥤 *Full Drinks Course*\n"
                    "✔ Drink Concentrates\n✔ Soft Drinks\n✔ Mawuyu Drink\n\n"
                    "Nyora MENU kudzokera kumusoro."
                )
            else:
                send_message(
                    phone,
                    "🔒 Lesson iyi ndeye *Paid Members Only*\n\n"
                    "Fee: $5\nNyora *PAY* kuti ubhadhare."
                )
            return jsonify({"status": "ok"})

        send_message(phone, "Sarudza 1 kana 2 kana nyora MENU")
        return jsonify({"status": "ok"})


    # fallback
    send_message(phone, "Nyora *MENU* kuti utange zvakare")
    return jsonify({"status": "ok"})


@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))




























