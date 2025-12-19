
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import os

app = Flask(__name__)

# Store lesson progress (temporary memory)
user_lessons = {}
user_drink_lessons = {}

# ---------------- MAIN MENU ----------------
def main_menu():
    return (
        "👋 Makadii! Tinokugamuchirai ku *ARACHIS ONLINE TRAINING* 🇿🇼\n\n"
        "Tinodzidzisa kugadzira:\n"
        "🧼 Detergents\n"
        "🥤 Concentrate Drinks\n"
        "📦 Packaging & Business\n\n"
        "Sarudza nhamba 👇🏽\n\n"
        "1️⃣ Detergent Training\n"
        "2️⃣ Concentrate Drinks Training\n"
        "3️⃣ Mitengo & Kubhadhara\n"
        "4️⃣ Free Lessons\n"
        "5️⃣ Join Full Training\n"
        "6️⃣ Bata Trainer\n\n"
        "📘 Nyora *LESSON* (Detergents)\n"
        "🥤 Nyora *DRINK* (Concentrates)"
    )

# ---------------- DETERGENT LESSONS ----------------
def lesson_content(day):
    lessons = {
        1: "📘 *LESSON 1: SAFETY*\nPfeka magirovhosi, shanda munzvimbo ine mweya.\nNyora *LESSON* mangwana.",
        2: "📘 *LESSON 2: DISHWASH*\nMvura + SLES + Salt + Fragrance.\nNyora *LESSON* mangwana.",
        3: "📘 *LESSON 3: FOAM BATH*\nSLES + CDE + Glycerine + Salt.\nNyora *LESSON* mangwana.",
        4: "📘 *LESSON 4: PINE GEL*\nPine oil + Surfactant + Dye + Water.\nNyora *LESSON* mangwana.",
        5: "📘 *LESSON 5: BUSINESS*\nPackaging, pricing, selling.\n🎉 Free lessons dzapera.\nNyora *JOIN*."
    }
    return lessons.get(day, "🎉 Free detergent lessons dzapera. Nyora *JOIN*.")

# ---------------- DRINK LESSONS ----------------
def drink_lesson_content(day):
    lessons = {
        1: "🥤 *DRINK LESSON 1: INTRO*\nConcentrates anosanganiswa nemvura.\nNyora *DRINK* mangwana.",
        2: "🥤 *DRINK LESSON 2: INGREDIENTS*\nWater, Sugar, Flavour, Citric Acid.\nNyora *DRINK* mangwana.",
        3: "🥤 *DRINK LESSON 3: MIXING*\nMix zvishoma nezvishoma kusvika yanyungudika.\nNyora *DRINK* mangwana.",
        4: "🥤 *DRINK LESSON 4: BOTTLING*\nMabhodhoro akachena + label.\nNyora *DRINK* mangwana.",
        5: "🥤 *DRINK LESSON 5: BUSINESS*\nStart small, sell local.\n🎉 Free drink lessons dzapera.\nNyora *JOIN*."
    }
    return lessons.get(day, "🎉 Free drink lessons dzapera. Nyora *JOIN*.")

# ---------------- ROUTES ----------------
@app.route("/", methods=["GET"])
def home():
    return "Arachis WhatsApp bot is running"

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip().lower()
    resp = MessagingResponse()
    msg = resp.message()

    if incoming_msg in ["hi", "hello", "menu", "start", "makadini"]:
        msg.body(main_menu())

    elif incoming_msg == "lesson":
        user = request.values.get("From")
        day = user_lessons.get(user, 0) + 1
        user_lessons[user] = day
        msg.body(lesson_content(day))

    elif incoming_msg == "drink":
        user = request.values.get("From")
        day = user_drink_lessons.get(user, 0) + 1
        user_drink_lessons[user] = day
        msg.body(drink_lesson_content(day))

    elif incoming_msg == "pay":
        msg.body(
            "💳 *PAYMENT DETAILS*\nEcoCash: 0773 208904\nZita: Beloved Nkomo\nTumira proof pano."
        )

    else:
        msg.body(main_menu())

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)








