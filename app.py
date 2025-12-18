from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import os

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Arachis WhatsApp bot is running"

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').lower()

    resp = MessagingResponse()
    msg = resp.message()

    if "detergent" in incoming_msg:
        msg.body(
            "🧼 *Arachis Training*\n"
            "Tinodzidzisa kugadzira:\n"
            "- Dishwash\n"
            "- Foam bath\n"
            "- Pine gel\n\n"
            "Nyora *JOIN* kuti ubatane."
        )
    elif "join" in incoming_msg:
        msg.body(
            "✅ Wakugamuchirwa!\n"
            "Trainee handbook ichatumirwa.\n"
            "Bhadhara kuti uwane full training."
        )
    else:
        msg.body(
            "👋 Makadii!\n"
            "Ndiri *Arachis WhatsApp Bot*\n\n"
            "Nyora:\n"
            "• *DETERGENT*\n"
            "• *JOIN*"
        )

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


