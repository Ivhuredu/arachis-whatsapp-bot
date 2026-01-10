from flask import Flask, request, jsonify
from twilio.rest import Client
import sqlite3
import os

app = Flask(__name__)

# =========================
# TWILIO CONFIG
# =========================
ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP = os.environ.get("TWILIO_WHATSAPP_NUMBER")

client = Client(ACCOUNT_SID, AUTH_TOKEN)

# =========================
# DATABASE
# =========================
def db():
    return sqlite3.connect("bot.db", check_same_thread=False)

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY,
            state TEXT,
            is_paid INTEGER DEFAULT 0,
            payment_status TEXT
        )
    """)
    con.commit()

init_db()

def create_user(phone):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (phone, state, is_paid, payment_status) VALUES (?, 'main', 0, '')",
        (phone,)
    )
    con.commit()

def get_user(phone):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT phone, state, is_paid, payment_status FROM users WHERE phone=?", (phone,))
    row = cur.fetchone()
    return {
        "phone": row[0],
        "state": row[1],
        "is_paid": bool(row[2]),
        "payment_status": row[3]
    }

def set_state(phone, state):
    con = db()
    con.execute("UPDATE users SET state=? WHERE phone=?", (state, phone))
    con.commit()

def mark_paid(phone):
    con = db()
    con.execute("UPDATE users SET is_paid=1, payment_status='' WHERE phone=?", (phone,))
    con.commit()

def set_payment_status(phone, status):
    con = db()
    con.execute("UPDATE users SET payment_status=? WHERE phone=?", (status, phone))
    con.commit()

# =========================
# MESSAGING
# =========================
def send_message(to, body):
    client.messages.create(
        from_=TWILIO_WHATSAPP,
        to=f"whatsapp:{to}",
        body=body
    )

# =========================
# MENUS
# =========================
def main_menu():
    return (
        "👋 *ARACHIS ONLINE TRAINING*\n\n"
        "1️⃣ Detergents lessons\n"
        "2️⃣ Drinks lessons\n"
        "3️⃣ Prices\n"
        "4️⃣ Free detergent lesson\n"
        "5️⃣ Join full course\n"
        "6️⃣ Contact trainer\n"
        "7️⃣ Paid lessons\n\n"
        "Reply with number"
    )

def free_detergent():
    return (
        "*FREE DISHWASH LESSON*\n\n"
        "Ingredients:\n"
        "• SLES\n• Salt\n• Colour\n• Perfume\n\n"
        "Steps:\n"
        "1. Mix SLES + water\n"
        "2. Add salt slowly\n"
        "3. Add colour & perfume\n\n"
        "For full course nyora *PAY*"
    )

def free_drink():
    return (
        "*FREE DRINK LESSON*\n\n"
        "You will learn how to make a simple cordial base.\n\n"
        "For full recipes nyora *PAY*"
    )

# =========================
# PAID LESSON CONTENT
# =========================
PAID_LESSONS = {
    "intro": """*ARACHIS ONLINE TRAINING – INTRODUCTION*

You will learn to make:
• Dishwash
• Foam Bath
• Thick Bleach
• Pine Gel
• Toilet Cleaner
• Fabric Softener
• Petroleum Jelly
• Drinks & Cordials

Study at your own pace.
Ask questions anytime.
""",

    "safety": """*MODULE 1: SAFETY & REQUIREMENTS*

Equipment:
• Buckets
• Measuring scale
• Mixing stick
• Gloves & goggles

Safety:
• Work in ventilated area
• Avoid skin & eyes
• Keep chemicals away from children
""",

    "dishwash": """*MODULE 2: DISHWASH (20L)*

Ingredients:
• SLES – 1.5kg
• Sulphonic acid – 1L
• Caustic soda – 3 tbsp
• Soda ash – 3 tbsp
• Salt – 500g
• Bermacol – 3 tbsp
• Amido – 100ml
• Dye & perfume
• Water – 17.5L

Steps:
1. Add water
2. Add SLES
3. Add sulphonic acid
4. Neutralize
5. Thicken
6. Add perfume
""",

    "bleach": """*MODULE 3: THICK BLEACH*

Ingredients:
• Hypochlorite
• Caustic soda
• Water

Steps:
• Mix carefully
• Avoid metal containers
""",

    "foam": """*MODULE 4: FOAM BATH*

Ingredients:
• SLES
• CDE
• Glycerin
• Salt
• Perfume

Steps:
• Mix slowly
• Thicken with salt
"""
}

# =========================
# AI FAQ (SAFE)
# =========================
def ai_faq_reply(text):
    faqs = {
        "sles": "SLES is a foaming agent used in detergents.",
        "profit": "You can make 3–5x profit if priced correctly."
    }
    for k in faqs:
        if k in text:
            return faqs[k]
    return None

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    phone = request.form.get("From", "").replace("whatsapp:", "")
    incoming = request.form.get("Body", "").strip().lower()

    if not phone or not incoming:
        return jsonify({"status": "ignored"})

    create_user(phone)
    user = get_user(phone)

    # ---------- RESET ----------
    if incoming in ["menu", "start", "hi", "hello"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # ---------- PAYMENT ----------
    if incoming == "pay":
        set_payment_status(phone, "waiting_proof")
        send_message(phone, "💳 Pay $5 to 0773 208904\nSend proof here")
        return jsonify({"status": "ok"})

    if user["payment_status"] == "waiting_proof":
        set_payment_status(phone, "pending")
        send_message(phone, "✅ Proof received. Await approval.")
        return jsonify({"status": "ok"})

    # ---------- ADMIN APPROVAL ----------
    if incoming.startswith("approve "):
        raw = incoming.replace("approve ", "").strip()
        if raw.startswith("0"):
            target = "+263" + raw[1:]
        else:
            target = raw
        mark_paid(target)
        send_message(target, "🎉 Payment approved! Nyora MENU")
        send_message(phone, "✅ Approved successfully")
        return jsonify({"status": "ok"})

    # ---------- AI FAQ (NOT NUMBERS) ----------
    if not incoming.isdigit():
        faq = ai_faq_reply(incoming)
        if faq:
            send_message(phone, faq)
            return jsonify({"status": "ok"})

    # ---------- MAIN MENU ----------
    if user["state"] == "main":
        if incoming == "1":
            set_state(phone, "detergent_menu")
            send_message(phone, "1️⃣ Free\n2️⃣ Paid")
        elif incoming == "2":
            set_state(phone, "drink_menu")
            send_message(phone, "1️⃣ Free\n2️⃣ Paid")
        elif incoming == "3":
            send_message(phone, "💵 Full course $5\nNyora PAY")
        elif incoming == "4":
            send_message(phone, free_detergent())
        elif incoming == "5":
            send_message(phone, "Nyora PAY to join")
        elif incoming == "6":
            send_message(phone, "📞 0773 208904")
        elif incoming == "7":
            if user["is_paid"]:
                set_state(phone, "paid_lessons")
                send_message(phone, "1️⃣ Intro\n2️⃣ Safety\n3️⃣ Dishwash\n4️⃣ Bleach\n5️⃣ Foam bath")
            else:
                send_message(phone, "🔒 Paid only. Nyora PAY")
        else:
            send_message(phone, "Nyora MENU")
        return jsonify({"status": "ok"})

    # ---------- SUB MENUS ----------
    if user["state"] == "detergent_menu":
        if incoming == "1":
            send_message(phone, free_detergent())
        elif incoming == "2":
            send_message(phone, "Nyora PAY")
        return jsonify({"status": "ok"})

    if user["state"] == "drink_menu":
        if incoming == "1":
            send_message(phone, free_drink())
        elif incoming == "2":
            send_message(phone, "Nyora PAY")
        return jsonify({"status": "ok"})

    # ---------- PAID LESSONS ----------
    if user["state"] == "paid_lessons":
        if not user["is_paid"]:
            send_message(phone, "Access denied")
            return jsonify({"status": "ok"})

        lessons = {
            "1": PAID_LESSONS["intro"],
            "2": PAID_LESSONS["safety"],
            "3": PAID_LESSONS["dishwash"],
            "4": PAID_LESSONS["bleach"],
            "5": PAID_LESSONS["foam"]
        }

        send_message(phone, lessons.get(incoming, "Sarudza 1–5"))
        return jsonify({"status": "ok"})

    send_message(phone, "Nyora MENU")
    return jsonify({"status": "ok"})


































