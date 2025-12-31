from flask import Flask, request, jsonify
from twilio.rest import Client
import sqlite3
import os

app = Flask(__name__)

# =========================
# TWILIO WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    phone = request.form.get("From", "").replace("whatsapp:", "")
    incoming = request.form.get("Body", "").strip().lower()

    if not phone or not incoming:
        return jsonify({"status": "ignored"}), 200

    # Make sure user exists
    create_user(phone)
    user = get_user(phone)

    # ========= RESET or MAIN MENU =========
    if incoming in ["menu", "start", "hi", "hello", "makadini"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    # ========= PAYMENT FLOW =========
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

    # when user sends image/text after pay
    if user["payment_status"] == "waiting_proof":
        set_payment_status(phone, "pending_approval")
        send_message(phone, "✅ Proof yatambirwa. Mirira kusimbiswa ⏳")
        return jsonify({"status": "ok"})

    # ========= MAIN MENU HANDLER =========
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
                "👉 Nyora *PAY* kuti ubhadhare."
            )
            return jsonify({"status": "ok"})

        if incoming == "4":
            send_message(phone, free_detergent())
            return jsonify({"status": "ok"})

        if incoming in ["5", "join"]:
            send_message(phone, "To join full training nyora *PAY* 👍")
            return jsonify({"status": "ok"})

        if incoming == "6":
            send_message(phone, "📞 Bata trainer pa: 0773 208904")
            return jsonify({"status": "ok"})

        # fallback
        send_message(phone, "Nyora *MENU* kuti utange zvakare")
        return jsonify({"status": "ok"})

    # ========= DETERGENT SUB-MENU =========
    if user["state"] == "detergent_menu":

        if incoming == "1":
            send_message(phone, free_detergent())
            return jsonify({"status": "ok"})

        if incoming == "2":
            send_message(
                phone,
                "🧼 *Full Detergent Course*\n"
                "✔️ Dishwash\n✔️ Foam bath\n✔️ Thick bleach\n"
                "✔️ Pine gel\n\n"
                "👉 Nyora *PAY* kuti ubhadhare."
            )
            return jsonify({"status": "ok"})

        send_message(phone, "Sarudza 1 kana 2 kana nyora MENU")
        return jsonify({"status": "ok"})

    # ========= DRINKS SUB-MENU =========
    if user["state"] == "drink_menu":

        if incoming == "1":
            send_message(phone, free_drink())
            return jsonify({"status": "ok"})

        if incoming == "2":
            send_message(
                phone,
                "🥤 *Full Drinks Course*\n"
                "✔️ Freezits\n✔️ Maheu base\n✔️ Cordials\n\n"
                "👉 Nyora *PAY* kuti ubhadhare."
            )
            return jsonify({"status": "ok"})

        send_message(phone, "Sarudza 1 kana 2 kana nyora MENU")
        return jsonify({"status": "ok"})

    # fallback universal
    send_message(phone, "Nyora *MENU* kuti utange zvakare")
    return jsonify({"status": "ok"})

























