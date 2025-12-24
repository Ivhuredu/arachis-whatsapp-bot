from fastapi import FastAPI, Request
import requests

app = FastAPI()

# 🔐 Hard-coded token (NO Render env needed)
VERIFY_TOKEN = "arachis-arachisbot-2025"

# ⚠️ Replace these two with your actual values when ready
WHATSAPP_TOKEN = "YOUR_WHATSAPP_ACCESS_TOKEN"
WHATSAPP_PHONE_ID = "YOUR_PHONE_NUMBER_ID"


# =========================
#  WEBHOOK VERIFICATION
# =========================
@app.get("/")
async def verify_webhook(request: Request):
    params = request.query_params

    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    token = params.get("hub.verify_token")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)

    return {"status": "verification failed"}


# =========================
#  RECEIVE MESSAGES
# =========================
@app.post("/")
async def whatsapp_webhook(request: Request):
    data = await request.json()

    try:
        entry = data["entry"][0]["changes"][0]["value"]
        messages = entry.get("messages", [])

        if not messages:
            return {"status": "no message"}

        msg = messages[0]
        from_number = msg["from"]

        if "text" in msg:
            user_message = msg["text"]["body"].strip().lower()
        else:
            user_message = ""

        # ======================
        #  SIMPLE MENU RESPONSE
        # ======================
        if user_message in ["hi", "menu", "hello", "start"]:
            reply = (
                "*Welcome to Arachis Brands Training Bot*\n\n"
                "Reply with a number:\n"
                "1️⃣ Detergents Training\n"
                "2️⃣ Concentrate Drinks Training\n"
                "3️⃣ Pricing & Business Support\n"
                "4️⃣ Join Premium Paid Lessons"
            )

        elif user_message == "1":
            reply = (
                "*🧴 Detergents Training Modules*\n"
                "- Dishwash\n"
                "- Foam Bath\n"
                "- Pine Gel\n"
                "- Thick Bleach\n\n"
                "Reply *PAID* to unlock full lessons."
            )

        elif user_message == "2":
            reply = (
                "*🥤 Concentrate Drink Training*\n"
                "- Orange\n"
                "- Raspberry\n"
                "- Pineapple\n\n"
                "Reply *PAID* to unlock full lessons."
            )

        elif user_message == "4" or user_message == "paid":
            reply = (
                "*💰 Premium Paid Lessons*\n"
                "Includes full recipes, costing, scaling & business training.\n\n"
                "Reply *JOIN* to enroll."
            )

        else:
            reply = (
                "Send *menu* to see options.\n"
                "Or reply with a number 1–4."
            )

        send_whatsapp_message(from_number, reply)

    except Exception as e:
        print("Error handling message:", e)

    return {"status": "message processed"}


# =========================
#  SEND MESSAGE FUNCTION
# =========================
def send_whatsapp_message(to, message):

    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }

    requests.post(url, headers=headers, json=payload)













