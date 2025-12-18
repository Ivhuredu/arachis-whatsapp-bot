from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import os
user_lessons = {}

app = Flask(__name__)

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
        "6️⃣ Bata Trainer"
    )
def lesson_content(day):
    lessons = {
        1: (
            "📘 *LESSON 1: INTRODUCTION & SAFETY*\n\n"
            "Detergent making ibhizinesi rakanaka.\n"
            "Asi chengetedzo yakakosha:\n"
            "✔ Pfeka magirovhosi\n"
            "✔ Usasanganisa makemikari zvisiri izvo\n"
            "✔ Shanda munzvimbo ine mweya\n\n"
            "Mangwana nyora *LESSON* kuti uenderere mberi."
        ),
        2: (
            "📘 *LESSON 2: DISHWASH*\n\n"
            "Zvinodiwa:\n"
            "• Mvura\n"
            "• SLES\n"
            "• Salt (thickener)\n"
            "• Fragrance\n\n"
            "Mix zvishoma nezvishoma kusvika yaita gobvu.\n\n"
            "Mangwana nyora *LESSON*."
        ),
        3: (
            "📘 *LESSON 3: FOAM BATH*\n\n"
            "Zvinodiwa:\n"
            "• SLES\n"
            "• CDE\n"
            "• Glycerine\n"
            "• Salt\n\n"
            "Inoshandiswa kugeza muviri.\n\n"
            "Mangwana nyora *LESSON*."
        ),
        4: (
            "📘 *LESSON 4: PINE GEL*\n\n"
            "Zvinodiwa:\n"
            "• Pine oil\n"
            "• Surfactant\n"
            "• Dye\n"
            "• Water\n\n"
            "Inoshandiswa kuchenesa pasi, toilet.\n\n"
            "Mangwana nyora *LESSON*."
        ),
        5: (
            "📘 *LESSON 5: PACKAGING & BUSINESS*\n\n"
            "✔ Shandisa mabhodhoro akachena\n"
            "✔ Isa label rine zita & contact\n"
            "✔ Tanga nemusika wemuno\n\n"
            "🎉 Makorokoto! Wapedza free lessons.\n"
            "Nyora *JOIN* kuti uwane full formulas."
        )
    }
    return lessons.get(day, "🎉 Free lessons dzapera. Nyora *JOIN*.")

@app.route("/", methods=["GET"])
def home():
    return "Arachis WhatsApp bot is running"

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip().lower()
    resp = MessagingResponse()
    msg = resp.message()

    # MAIN MENU TRIGGERS
    if incoming_msg in ["hi", "hello", "menu", "start""makadini"]:
        msg.body(main_menu())

    # OPTION 1
    elif incoming_msg == "1":
        msg.body(
            "🧼 *DETERGENT TRAINING*\n\n"
            "Tinodzidzisa kugadzira:\n"
            "✔ Dishwash\n"
            "✔ Foam Bath\n"
            "✔ Pine Gel\n"
            "✔ Bleach\n"
            "✔ Handwash\n\n"
            "Zvinokodzera kutengesa kana kushandisa pamba.\n\n"
            "Nyora *JOIN* kana *FREE*"
        )

    # OPTION 2
    elif incoming_msg == "2":
        msg.body(
            "🥤 *CONCENTRATE DRINKS TRAINING*\n\n"
            "Tinodzidzisa:\n"
            "✔ Orange\n"
            "✔ Raspberry\n"
            "✔ Pineapple\n"
            "✔ Mango\n"
            "✔ Drink re Mawuyu\n\n"
            "Nyora *JOIN* kana *FREE*"
        )

    # OPTION 3
    elif incoming_msg == "3":
        msg.body(
            "💰 *MITENGO & KUBHADHARA*\n\n"
            "📘 Full Training inosanganisira:\n"
            "• Detergents + Drinks\n"
            "• Student Handbook (PDF)\n"
            "• Business guidance\n\n"
            "💵 Mari: $5\n\n"
            "Nzira dzekubhadhara:\n"
            "• EcoCash\n"
            "• OneMoney\n"
            "• Mukuru\n"
            "• Bank\n\n"
            "Nyora *PAY* kuti uwane details"
        )

    # OPTION 4
    elif incoming_msg == "4" or incoming_msg == "free":
        msg.body(
            "🎁 *FREE LESSON*\n\n"
            "Lesson 1:\n"
            "Dishwash inogadzirwa nemvura, SLES, salt uye fragrance.\n"
            "Inoshandiswa kugeza ndiro, makapu nemapoto.\n\n"
            "⚠️ Full formulas & support zvinowanikwa kune vakabhadhara chete.\n\n"
            "Nyora *JOIN* kuti uenderere mberi"
        )

    # OPTION 5
    elif incoming_msg == "5" or incoming_msg == "join":
        msg.body(
            "✅ *JOIN FULL TRAINING*\n\n"
            "Matanho:\n"
            "1️⃣ Bhadhara\n"
            "2️⃣ Tumira proof\n"
            "3️⃣ Unopihwa full access\n\n"
            "Nyora *PAY* kuti utumirwe payment details"
        )

    # OPTION 6
    elif incoming_msg == "6":
        msg.body(
            "📞 *Taura nemudzidzisi*\n\n"
            "WhatsApp: 0773208904\n"
            "Time: 8am – 6pm\n\n"
            "Tinofara kukubatsira 🙏🏽"
        )

    # PAYMENT DETAILS
    elif incoming_msg == "pay":
        msg.body(
            "💳 *PAYMENT DETAILS*\n\n"
            "EcoCash: 0773 208904\n"
            "Zita: Beloved Nkomo\n\n"
            "Tumira proof pano mushure mekubhadhara."
        )
    elif incoming_msg == "lesson":
        user = request.values.get("From")
        current_day = user_lessons.get(user, 0) + 1
        user_lessons[user] = current_day
        msg.body(lesson_content(current_day))

    # DEFAULT RESPONSE
    else:
        msg.body(main_menu())

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

