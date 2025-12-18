from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def arachis_bot():
    msg = request.values.get("Body", "").strip().lower()
    resp = MessagingResponse()

    if msg in ["hi", "hello", "start", "menu"]:
        resp.message(
            "👋 *Tinokugamuchirai ku ARACHIS ONLINE TRAINING*\n\n"
            "Tinodzidzisa:\n"
            "🧴 Detergent Making\n"
            "🥤 Concentrate Drinks\n\n"
            "Pindura nenhamba:\n"
            "1️⃣ About Training\n"
            "2️⃣ Free Training\n"
            "3️⃣ Paid Training\n"
            "4️⃣ Payment Info\n"
            "5️⃣ Taura neAdmin"
        )

    elif msg == "1":
        resp.message(
            "ARACHIS Online Training inodzidzisa ma detergents "
            "nemaconcentrate drinks kubva pakutanga kusvika pakutengesa."
        )

    elif msg == "2":
        resp.message(
            "🎁 *FREE TRAINING*\n"
            "Join group pano:\n"
            "https://chat.whatsapp.com/EUKSnlpG33vDEa34Vhx9Lz"
        )

    elif msg == "3":
        resp.message(
            "💼 *PAID TRAINING*\n"
            "✔ Full formulas\n"
            "✔ Step-by-step lessons\n"
            "✔ Student handbook (PDF)\n"
            "✔ Certificate"
        )

    elif msg == "4":
        resp.message(
            "💰 *PAYMENT INFO*\n"
            "EcoCash / OneMoney\n"
            "Send proof after payment."
        )

    elif msg == "5":
        resp.message(
            "📞 Taura neAdmin pano:\n"
            "+263773208904"
        )

    else:
        resp.message(
            "Handina kunyatsonzwisisa.\n"
            "Reply *START* kuti uone menu."
        )

    return str(resp)

if __name__ == "__main__":
    app.run()
