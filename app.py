import PyPDF2
import requests
from flask import Flask, request, jsonify, redirect, url_for
from database import get_db, release_db, init_db
import os
import json
import base64
from werkzeug.utils import secure_filename
from functools import wraps
from flask import Response
from dataclasses import dataclass
from menus import *
from config import *
from ai import *
from utils import safe_text
from services import *

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

def check_auth(username, password):
    return username == "admin" and password == ADMIN_PASSWORD
    
def authenticate():
    return Response(
        'Login required', 401,
        {'WWW-Authenticate': 'Basic realm="Admin Login"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

import random
from datetime import datetime

def generate_booking_number(event_id):
    today = datetime.now().strftime("%y%m%d")
    rand = random.randint(1000, 9999)
    return f"AR-{event_id}-{today}-{rand}"


app = Flask(__name__)

app.config["MARKETPLACE_FOLDER"] = MARKETPLACE_FOLDER
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["APK_FOLDER"] = APK_FOLDER

# =========================
# CONFIG
# =========================
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
# =========================
# HELPERS
# =========================
def normalize_phone(phone):
    return phone if phone.startswith("+") else "+" + phone

def is_admin_phone(phone):
    return phone in ADMIN_NUMBERS
    
from datetime import date

def whatsapp_media_disabled_for(phone):
    if phone in ADMIN_NUMBERS:
        return False

    today = date.today()
    cutoff = date.fromisoformat(DISABLE_WHATSAPP_MEDIA_FROM)

    return today >= cutoff
    
def send_message(phone, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    if text is None:
        text = ""

    text = safe_text(text).strip()

    chunks = []
    max_len = 3000

    while len(text) > max_len:
        cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len

        chunks.append(text[:cut].strip())
        text = text[cut:].strip()

    if text:
        chunks.append(text)

    for i, chunk in enumerate(chunks, start=1):

        if len(chunks) > 1:
            chunk = f"Part {i}/{len(chunks)}\n\n{chunk}"

        payload = {
            "messaging_product": "whatsapp",
            "to": phone.replace("+", ""),
            "type": "text",
            "text": {"body": chunk}
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=15
            )

            print("MESSAGE STATUS:", response.status_code)
            print("MESSAGE RESPONSE:", response.text)

            try:
                data = response.json()
                message_id = data["messages"][0]["id"]

                conn = get_db()
                c = conn.cursor()
                c.execute("""
                    INSERT INTO outbound_messages (phone, whatsapp_message_id, message_type, status)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (whatsapp_message_id)
                    DO UPDATE SET status='accepted', updated_at=CURRENT_TIMESTAMP
                """, (phone, message_id, "text", "accepted"))

                conn.commit()
                release_db(conn)

            except Exception as e:
                print("OUTBOUND SAVE ERROR:", e)

            if response.status_code != 200:
                log_activity(phone, "send_message_failed", response.text[:500])

        except Exception as e:
            print("SEND MESSAGE ERROR:", e)
            log_activity(phone, "send_message_exception", str(e)[:500])

def send_image(phone, image_url, caption=""):
    """
    Sends a marketplace product picture through WhatsApp Cloud API.

    The image_url must be public HTTPS, for example:
    https://arachis-whatsapp-bot-2.onrender.com/static/marketplace/dishwash_starter.jpg
    """

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+", ""),
        "type": "image",
        "image": {
            "link": image_url,
            "caption": safe_text(caption)[:1000]
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        print("IMAGE STATUS:", response.status_code)
        print("IMAGE RESPONSE:", response.text)

        if response.status_code != 200:
            log_activity(phone, "send_image_failed", response.text[:500])

    except Exception as e:
        print("SEND IMAGE ERROR:", e)
        log_activity(phone, "send_image_exception", str(e)[:500])

def send_image_by_id(phone, media_id, caption=""):
    """
    Sends a WhatsApp image using a stored WhatsApp media ID.
    Useful for customer-uploaded product pictures.
    """

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+", ""),
        "type": "image",
        "image": {
            "id": media_id,
            "caption": safe_text(caption)[:1000]
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        print("IMAGE ID STATUS:", response.status_code)
        print("IMAGE ID RESPONSE:", response.text)

        if response.status_code != 200:
            log_activity(phone, "send_image_id_failed", response.text[:500])

    except Exception as e:
        print("SEND IMAGE ID ERROR:", e)
        log_activity(phone, "send_image_id_exception", str(e)[:500])

def download_whatsapp_image(media_id):

    url = f"https://graph.facebook.com/v18.0/{media_id}"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }

    r = requests.get(url, headers=headers)
    media_url = r.json()["url"]

    image = requests.get(media_url, headers=headers)

    path = f"/tmp/{media_id}.jpg"

    with open(path, "wb") as f:
        f.write(image.content)

    return path

def seed_prices():
    conn = get_db()
    c = conn.cursor()

    prices = [
        ("SLES", 3.50, "kg"),
        ("Caustic Soda", 3.00, "kg"),
        ("Sulphonic Acid", 4.50, "litre"),
        ("Perfume", 1.0, "30ml"),
        ("Bermacol", 7.0, "kg"),
        ("Amido", 1.0, "100ml"),
        ("CAPB", 2.50, "500g"),
        ("Soda Ash", 2.00, "kg"),
        ("Glycerine", 5.0, "kg"),
        ("Petroleum Jelly", 3.50, "kg"),
        ("Perfume", 1.0, "30ml"),
        ("Dye Yellow-Oil based", 2.0, "10ml"),
        ("White Oil", 2.25, "500g"),
        ("Pine Oil", 10.0, "litre"),
        ("Sodium Hypochlorite", 2.0, "kg"),
        ("Butyl Glycol", 7.0, "kg"),
        ("Sodium Metasillicate", 0.75, "250g"),
        ("Bermacol", 0.50, "20g"),
        ("Acid Stable Perfume", 1.0, "30ml"),
        ("Ardogen", 7.0, "kg"),
        ("Citric Acid", 5.0, "kg"),
        ("Ethanol", 3.0, "kg"),
        ("Paraffin Oil", 4.50, "kg"),
        ("Fragrance Oil", 1.0, "30ml"),
        ("Pine Gel Container", 0.25, "1litre"),
        ("Dishwash Container", 0.25, "750ml"),
        ("Foam Bath Container", 0.30, "1litre"),
        ("NP9", 5.5, "kg"),
        ("NP6", 6.0, "kg")
    ]

    for p in prices:
        c.execute("""
        INSERT INTO ingredient_prices (name, price_per_unit, unit)
        VALUES (%s,%s,%s)
        ON CONFLICT (name) DO UPDATE
        SET price_per_unit = EXCLUDED.price_per_unit
        """, p)

    conn.commit()
    release_db(conn)

def get_all_prices():

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT name, price_per_unit, unit FROM ingredient_prices")

    rows = c.fetchall()
    release_db(conn)

    price_text = ""

    for r in rows:
        price_text += f"{r[0]}: ${r[1]} per {r[2]}\n"

    return price_text


def send_pdf(phone, pdf_url, caption):

    if whatsapp_media_disabled_for(phone):
        send_message(
            phone,
            "📱 *ARACHIS APP REQUIRED / APP YAVA KUSHANDISWA*\n\n"
            "🇬🇧 *English Instructions:*\n"
            "PDF notes are no longer sent directly on WhatsApp.\n\n"
            "To read this lesson:\n"
            "1️⃣ Go back to the main menu by typing *MENU*\n"
            "2️⃣ Choose option *10 - Download App*\n"
            "3️⃣ Download and install the Arachis App\n"
            "4️⃣ Open the app\n"
            "5️⃣ Log in using your approved WhatsApp number\n"
            "6️⃣ Open your lessons inside the app\n\n"
            "🇿🇼 *Mirairo yeShona:*\n"
            "Hatichatumiri maPDF notes paWhatsApp.\n\n"
            "Kuti uverenge lesson iyi:\n"
            "1️⃣ Nyora *MENU* kuti udzokere ku main menu\n"
            "2️⃣ Sarudza option *10 - Download App*\n"
            "3️⃣ Download woisa Arachis App mufoni yako\n"
            "4️⃣ Vhura app\n"
            "5️⃣ Log in nenumber yako yakatenderwa yawakashandisa paWhatsApp\n"
            "6️⃣ Wobva wavhura ma lessons ako muApp\n\n"
            "🤖 AI support ichiri kushanda pano paWhatsApp."
        )
        return

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+", ""),
        "type": "document",
        "document": {
            "link": pdf_url,
            "caption": caption
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=15)
    print(response.text)

def send_voice(phone, audio_url):

    if whatsapp_media_disabled_for(phone):
        return

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+", ""),
        "type": "audio",
        "audio": {
            "link": audio_url
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=15)

    print("VOICE STATUS:", response.status_code)
    print("VOICE RESPONSE:", response.text)

def send_app_download(phone):
    render_apk_url = "https://arachis-whatsapp-bot-2.onrender.com/static/apk/arachis.apk"

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    send_message(
        phone,
        "📱 *ARACHIS ONLINE TRAINING APP*\n\n"
        "The app file is being sent below.\n\n"
        "After downloading:\n"
        "1️⃣ Tap the APK file\n"
        "2️⃣ Allow installation if asked\n"
        "3️⃣ Open the app\n"
        "4️⃣ Login using your approved WhatsApp number"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+", ""),
        "type": "document",
        "document": {
            "link": render_apk_url,
            "filename": "Arachis_Online_Training.apk",
            "caption": "📱 Arachis Online Training App"
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)

    print("APK SEND STATUS:", response.status_code)
    print("APK SEND RESPONSE:", response.text)

    send_message(
        phone,
        "Alternative download from APKPure:\n"
        f"{APKPURE_URL}"
    )

import time

def send_audio_series(phone, module):

    if whatsapp_media_disabled_for(phone):
        return

    base_url = "https://arachis-whatsapp-bot-2.onrender.com/static/audio"

    found = False

    for i in range(1, 10):

        # file WITHOUT cache first
        clean_url = f"{base_url}/{module}_{i}.ogg"

        r = requests.get(clean_url)

        if r.status_code == 200:
            found = True

            # tell user which part
            send_message(phone, f"▶️ Part {i}")

            # 🔥 CACHE FIX (VERY IMPORTANT)
            versioned_url = clean_url + f"?v={int(time.time())}"

            send_voice(phone, versioned_url)

        else:
            break

    # fallback (if no parts exist)
    if not found:
        clean_url = f"{base_url}/{module}.ogg"
        versioned_url = clean_url + f"?v={int(time.time())}"
        send_voice(phone, versioned_url)

# =========================
# ADMIN ALERTS
# =========================
def send_admin_alert(title, body):

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    text = f"🔔 {title}\n\n{body}"

    for admin in ADMIN_NUMBERS:
        payload = {
            "messaging_product": "whatsapp",
            "to": admin.replace("+",""),
            "type": "text",
            "text": {"body": text}
        }

        try:
            requests.post(url, headers=headers, json=payload, timeout=10)
        except Exception as e:
            print(f"ADMIN ALERT FAILED for {admin}:", e)
    
def send_template(phone, template_name):

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+", ""),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"}
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=15)

    print("🔥 TEMPLATE STATUS:", response.status_code)
    print("🔥 TEMPLATE RESPONSE:", response.text)

    try:
        data = response.json()
        message_id = data["messages"][0]["id"]

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO template_messages (phone, template_name, whatsapp_message_id, status)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (whatsapp_message_id)
            DO UPDATE SET status='accepted', updated_at=CURRENT_TIMESTAMP
        """, (phone, template_name, message_id, "accepted"))

        conn.commit()
        release_db(conn)

    except Exception as e:
        print("TEMPLATE SAVE ERROR:", e)

    return response.status_code, response.text
    
def update_metrics(phone, event):
    conn = get_db()
    c = conn.cursor()

    # ensure row exists
    c.execute("""
        INSERT INTO student_metrics (phone)
        VALUES (%s)
        ON CONFLICT (phone) DO NOTHING
    """, (phone,))

    if event == "message":
        c.execute("""
            UPDATE student_metrics
            SET total_messages = total_messages + 1,
                last_active = CURRENT_TIMESTAMP
            WHERE phone=%s
        """, (phone,))

    elif event == "ai":
        c.execute("""
            UPDATE student_metrics
            SET ai_questions = ai_questions + 1,
                last_active = CURRENT_TIMESTAMP
            WHERE phone=%s
        """, (phone,))

    elif event == "module":
        c.execute("""
            UPDATE student_metrics
            SET modules_opened = modules_opened + 1,
                last_active = CURRENT_TIMESTAMP
            WHERE phone=%s
        """, (phone,))

    conn.commit()
    release_db(conn)

def mark_paid(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_paid=1, payment_status='approved' WHERE phone=%s",
        (phone,)
    )
    conn.commit()
    release_db(conn)

def revoke_access(phone):
    conn = get_db()
    c = conn.cursor()

    # remove paid access
    c.execute("""
        UPDATE users
        SET is_paid=0,
            payment_status='revoked',
            package='none',
            active_module=NULL
        WHERE phone=%s
    """, (phone,))

    # remove opened lesson access
    c.execute("DELETE FROM module_access WHERE phone=%s", (phone,))

    # remove custom selected modules
    c.execute("DELETE FROM custom_module_access WHERE phone=%s", (phone,))

    # remove AI memory
    c.execute("DELETE FROM ai_memory WHERE phone=%s", (phone,))

    conn.commit()
    release_db(conn)
    
    log_activity(phone, "access_revoked", "admin")

def already_processed_message(message_id, phone, incoming):
    conn = get_db()
    c = conn.cursor()

    try:
        c.execute("""
            INSERT INTO processed_messages (whatsapp_message_id, phone, incoming)
            VALUES (%s, %s, %s)
            ON CONFLICT (whatsapp_message_id) DO NOTHING
            RETURNING whatsapp_message_id
        """, (message_id, phone, incoming))

        inserted = c.fetchone()
        conn.commit()
        release_db(conn)

        return inserted is None

    except Exception as e:
        print("DEDUP ERROR:", e)
        conn.rollback()
        release_db(conn)
        return False
        
import re

def extract_ecocash_details(text):
    """
    Extract payment amount and EcoCash reference from a real EcoCash confirmation SMS.

    This function deliberately rejects app shortcut messages such as:
    ARACHIS_APP_PAYMENT_CONFIRMATION

    The app message must only move the user into awaiting_payment.
    It must never approve payment by itself.
    """

    if not text:
        return None, None, None

    original_text = text
    text = text.replace(",", "")
    lower_text = text.lower()

    # Never treat app commands as payment proof
    blocked_app_commands = [
        "arachis_app_payment_confirmation",
        "arachis_marketplace_order",
        "arachis_marketplace_sell"
    ]

    if any(cmd in lower_text for cmd in blocked_app_commands):
        return None, None, None

    # Must look like a real EcoCash message
    ecocash_keywords = [
        "ecocash",
        "you have received",
        "received",
        "transfer",
        "transaction",
        "txn",
        "ref",
        "reference"
    ]

    if not any(k in lower_text for k in ecocash_keywords):
        return None, None, None

    # Amount patterns commonly seen in EcoCash messages
    amount_match = re.search(
        r"(?:usd|zwg|\$)\s*(\d+(?:\.\d{1,2})?)|amount[:\s]*(\d+(?:\.\d{1,2})?)",
        text,
        re.I
    )

    amount = None

    if amount_match:
        amount_text = amount_match.group(1) or amount_match.group(2)
        amount = float(amount_text)

    # Reference must be explicit and reasonably long
    ref_match = re.search(
        r"(?:reference|ref|transaction\s*id|txn\s*id|code)[:\s#-]*([A-Za-z0-9]{6,})",
        text,
        re.I
    )

    reference = ref_match.group(1).strip() if ref_match else None

    # Optional sender number
    phone_match = re.search(r"07\d{8}", original_text)
    sender = phone_match.group(0) if phone_match else None

    return amount, reference, sender

def verify_and_apply_payment(phone, message):

    amount, reference, sender = extract_ecocash_details(message)

    if not reference:
        return False, "Handina kuona reference number mu message."

    if not amount:
        return False, "Handina kuona mari yatumirwa muSMS."

    ecocash_keywords = ["ecocash", "transfer", "paid", "you have received", "transaction", "cash out"]

    if not any(k in message.lower() for k in ecocash_keywords):
        return False, "Tumira EcoCash confirmation SMS chaiyo."

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT 1 FROM payments WHERE reference=%s", (reference,))
    if c.fetchone():
        release_db(conn)
        return False, "Reference yakamboshandiswa kare."

    c.execute("SELECT package FROM users WHERE phone=%s", (phone,))
    package_row = c.fetchone()
    selected_package = package_row[0] if package_row else "none"

    c.execute("SELECT package, pending_purchase FROM users WHERE phone=%s", (phone,))
    package_row = c.fetchone()

    current_package = package_row[0] if package_row else "none"
    pending_purchase = package_row[1] if package_row else None

    if pending_purchase == "advanced_full":
        if amount < ADVANCED_PRICE:
            release_db(conn)
            return False, "Mari ishoma. Advanced Full Package iri $20."
        package = "advanced"

    elif pending_purchase == "spices_full":
        if amount < SPICES_PRICE:
            release_db(conn)
            return False, "Mari ishoma. Spices & Seasonings package iri $10."
        package = "spices"

    elif pending_purchase == "upgrade_basic_to_premium":
        if amount < UPGRADE_BASIC_TO_PREMIUM:
            release_db(conn)
            return False, "Mari ishoma. Upgrade yeBasic to Premium iri $5."
        package = "premium"

    elif pending_purchase == "upgrade_basic_to_spices":
        if amount < UPGRADE_BASIC_TO_SPICES:
            release_db(conn)
            return False, "Mari ishoma. Add Spices iri $5."
        package = current_package

    elif pending_purchase == "upgrade_basic_to_advanced":
        if amount < UPGRADE_BASIC_TO_ADVANCED:
            release_db(conn)
            return False, "Mari ishoma. Basic to Advanced upgrade iri $10."
        package = "advanced"

    elif pending_purchase == "upgrade_premium_to_spices":
        if amount < UPGRADE_PREMIUM_TO_SPICES:
            release_db(conn)
            return False, "Mari ishoma. Premium add Spices iri $5."
        package = current_package

    elif pending_purchase == "upgrade_premium_to_advanced":
        if amount < UPGRADE_PREMIUM_TO_ADVANCED:
            release_db(conn)
            return False, "Mari ishoma. Premium to Advanced upgrade iri $7."
        package = "advanced"

    elif current_package == "custom":
        selected_modules = get_custom_modules(phone)
        expected_amount = len(selected_modules) * CUSTOM_PRICE_PER_MODULE

        if expected_amount <= 0:
            release_db(conn)
            return False, "Hausati wasarudza ma formula eCustom Package."

        if amount < expected_amount:
            release_db(conn)
            return False, f"Mari ishoma. Custom package yako iri ${expected_amount:.2f}."

        package = "custom"

    elif current_package == "basic":
        if amount < BASIC_PRICE:
            release_db(conn)
            return False, f"Mari ishoma. Basic package iri ${BASIC_PRICE:.2f}."
        package = "basic"

    elif current_package == "premium":
        if amount < PREMIUM_PRICE:
            release_db(conn)
            return False, f"Mari ishoma. Premium package iri ${PREMIUM_PRICE:.2f}."
        package = "premium"
        
    c.execute("""
        INSERT INTO payments (phone, reference, amount, raw_text)
        VALUES (%s,%s,%s,%s)
    """, (phone, reference, amount, message))

    conn.commit()
    release_db(conn)

    mark_paid(phone)

    if package == "custom":

        selected_modules = get_custom_modules(phone)

        conn = get_db()
        c = conn.cursor()

        for module in selected_modules:
            c.execute("""
                INSERT INTO module_access (phone, module)
                VALUES (%s, %s)
                ON CONFLICT (phone, module) DO NOTHING
            """, (phone, module))

        conn.commit()
        release_db(conn)

    conn = get_db()
    c = conn.cursor()
    has_spices = 0
    has_advanced = 0

    if pending_purchase in ["spices_full", "upgrade_basic_to_spices", "upgrade_premium_to_spices"]:
        has_spices = 1

    if pending_purchase in ["advanced_full", "upgrade_basic_to_advanced", "upgrade_premium_to_advanced"]:
        has_spices = 1
        has_advanced = 1

    if package == "advanced":
        has_spices = 1
        has_advanced = 1

    c.execute("""
        UPDATE users
        SET package=%s,
            has_spices = CASE WHEN %s=1 THEN 1 ELSE has_spices END,
            has_advanced = CASE WHEN %s=1 THEN 1 ELSE has_advanced END,
            pending_purchase=NULL
        WHERE phone=%s
    """, (package, has_spices, has_advanced, phone))
    conn.commit()
    release_db(conn)

    send_admin_alert(
        "AUTO PAYMENT APPROVED",
        f"Phone: {phone}\nPaid: ${amount}\nPackage: {package.upper()}\nRef: {reference}"
    )

    return True, f"🎉 Payment confirmed!\nPackage: {package.upper()}\nWava kukwanisa kuvhura ma lessons."

def admin_training_events():

    events = get_all_training_events()

    if not events:
        return "❌ No training events found."

    msg = "📅 *TRAINING EVENTS*\n\n"

    for e in events:

        (
            event_id,
            title,
            city,
            venue,
            event_date,
            start_time,
            fee,
            deposit,
            status,
            booked,
            seats
        ) = e

        available = seats - booked

        msg += (
            f"🆔 {event_id}\n"
            f"📌 {title}\n"
            f"🏙 City: {city}\n"
            f"📍 Venue: {venue}\n"
            f"📅 Date: {event_date}\n"
            f"🕘 Time: {start_time}\n"
            f"💵 Fee: ${fee}\n"
            f"💰 Deposit: ${deposit}\n"
            f"👥 Seats: {booked}/{seats}\n"
            f"✅ Available: {available}\n"
            f"📖 Status: {status}\n"
            "-----------------------------\n"
        )

    return msg

def add_training_event(
    title,
    city,
    venue,
    event_date,
    start_time,
    end_time,
    fee,
    deposit,
    products,
    seats
):

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO training_events(
            title,
            city,
            venue,
            event_date,
            start_time,
            end_time,
            fee,
            deposit,
            products_taught,
            total_seats
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """,(
        title,
        city,
        venue,
        event_date,
        start_time,
        end_time,
        fee,
        deposit,
        products,
        seats
    ))

    conn.commit()
    release_db(conn)

def extract_pdf_text(pdf_filename):

    try:
        path = os.path.join("static/lessons", pdf_filename)

        with open(path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            text = ""

            for page in reader.pages:
                text += page.extract_text() + "\n"

        return text

    except Exception as e:
        print("PDF READ ERROR:", e)
        return ""

def clean_pdf_text(text: str) -> str:
    if not text:
        return ""

    
    text = safe_text(text)

    # remove null bytes (critical for postgres)
    text = text.replace("\x00", "")

    # remove other invisible control chars except newline/tab
    text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\t")

    # compress excessive whitespace
    text = " ".join(text.split())

    return text

def save_pdf_to_db(module_name, pdf_filename):

    raw_text = extract_pdf_text(pdf_filename)
    text = clean_pdf_text(raw_text)

    if not text:
        print("No text extracted")
        return

    conn = get_db()
    c = conn.cursor()

    text = text[:15000]

    c.execute("""
        INSERT INTO lesson_content (module, content)
        VALUES (%s, %s)
        ON CONFLICT (module)
        DO UPDATE SET content = EXCLUDED.content
    """, (module_name, text))

    conn.commit()
    release_db(conn)

    print(f"Saved {module_name} to database")

def auto_sync_lessons():

    folder = "static/lessons"

    if not os.path.exists(folder):
        return

    conn = get_db()
    c = conn.cursor()

    for file in os.listdir(folder):

        if not file.endswith(".pdf"):
            continue

        module = file.replace(".pdf","")

        c.execute("SELECT 1 FROM lesson_content WHERE module=%s",(module,))
        exists = c.fetchone()

        if not exists:
            print("Auto learning lesson:", module)
            save_pdf_to_db(module, file)

    release_db(conn)

def get_lesson_from_db(module_name):

    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT content FROM lesson_content WHERE module=%s",
        (module_name,)
    )

    row = c.fetchone()
    release_db(conn)

    if row:
        return row[0]

    return ""

def get_relevant_lesson_chunk(module, question):

    lesson = get_lesson_from_db(module)

    if not lesson:
        return ""

    chunks = lesson.split("\n")
    question_words = question.lower().split()

    scored_chunks = []

    for chunk in chunks:
        text = chunk.lower()
        score = sum(1 for w in question_words if w in text)

        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(reverse=True)

    top_chunks = [c[1] for c in scored_chunks[:3]]

    return "\n".join(top_chunks) if top_chunks else lesson[:1000]
   
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def load_lessons():

    lessons = {}

    folder = "static/lessons"

    if not os.path.exists(folder):
        return lessons

    for file in os.listdir(folder):

        if file.endswith(".pdf"):

            module = file.replace(".pdf", "")

            label = module.replace("_", " ").title()

            lessons[module] = (file, f"📘 {label}")

    return lessons

ALL_MODULES = load_lessons()

def get_audio_url(module):
    return f"https://arachis-whatsapp-bot-2.onrender.com/static/audio/{module}.ogg"

def get_drink_modules():

    modules = load_lessons()

    return [
        k for k in modules
        if "drink" in k or "syrup" in k or "cordial" in k
    ]



def build_product_list_message(phone, products, title):
    if not products:
        return (
            f"🛒 *{title}*\n\n"
            "No products found yet.\n\n"
            "Type *SELL* to upload your own product.\n"
            "Type *MARKET* to go back."
        )

    save_marketplace_temp(
        phone,
        "results:" + ",".join([str(p[0]) for p in products])
    )

    text = f"🛒 *{title}*\n\n"

    for i, p in enumerate(products, start=1):
        product_id, name, category, price, unit, location = p
        text += f"{i}️⃣ {name}\n"
        text += f"   💵 {price} {unit}\n"
        text += f"   📍 {location}\n\n"

    text += (
        "Reply with product number to view details.\n"
        "Type *CART* to view selected products.\n"
        "Type *SEARCH* to search.\n"
        "Type *MARKET* to go back."
    )

    return text


def send_marketplace_product_details(phone, product_id):
    product = get_marketplace_product(product_id)

    if not product:
        send_message(phone, "❌ Product not found.")
        return

    (
        pid, category, name, description, price, unit,
        seller_name, seller_phone, seller_location,
        image_url, image_media_id, status
    ) = product

    caption = f"{name} | {price} {unit}"

    if image_media_id:
        send_image_by_id(phone, image_media_id, caption)

    elif image_url:
        send_image(phone, image_url, caption)

    text = (
        f"🛒 *{name}*\n\n"
        f"📂 Category: {category}\n"
        f"📝 Description: {description}\n\n"
        f"💵 Price: {price} {unit}\n\n"
        f"🏭 Seller: {seller_name}\n"
        f"📞 Contact: {seller_phone}\n"
        f"📍 Location: {seller_location}\n\n"
        "⚠️ Confirm stock, price and delivery with the seller before paying.\n\n"
        "Reply *ADD* to choose quantity and add this product to your cart.\n"
        "Reply *CART* to view your cart.\n"
        "Type *MARKET* to continue shopping."
    )

    save_marketplace_temp(phone, f"selected_product:{pid}")

    send_message(phone, text)


def add_marketplace_product(
    category,
    name,
    description,
    price,
    unit,
    seller_name,
    seller_phone,
    seller_location,
    image_media_id,
    created_by
):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO marketplace_products (
            category, name, description, price, unit,
            seller_name, seller_phone, seller_location,
            image_media_id, status, created_by
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)
        RETURNING id
    """, (
        category,
        name,
        description,
        price,
        unit,
        seller_name,
        seller_phone,
        seller_location,
        image_media_id,
        created_by
    ))

    product_id = c.fetchone()[0]

    conn.commit()
    release_db(conn)

    return product_id

def finalize_marketplace_product_upload(phone, image_media_id=None):
    """
    Finalizes a WhatsApp marketplace product upload.

    Works for:
    - product uploaded with photo
    - product uploaded with SKIP / no photo

    It saves product as pending, alerts all admin numbers,
    and gives seller the option to add another product.
    """

    temp = get_marketplace_temp(phone)

    data = {}

    for part in temp.split("|"):
        if "=" in part:
            key, value = part.split("=", 1)
            data[key] = value

    category = data.get("category", "Other")
    name = data.get("name", "Unnamed Product")
    description = data.get("description", "")
    price = data.get("price", "Contact seller")
    unit = data.get("unit", "")
    seller_name = data.get("seller_name", "Marketplace Seller")
    seller_location = data.get("seller_location", "Zimbabwe")

    product_id = add_marketplace_product(
        category=category,
        name=name,
        description=description,
        price=price,
        unit=unit,
        seller_name=seller_name,
        seller_phone=phone,
        seller_location=seller_location,
        image_media_id=image_media_id,
        created_by=phone
    )

    clear_marketplace_temp(phone)

    # Keep seller in a follow-up state so they can add another product quickly.
    set_state(phone, "marketplace_after_upload")

    photo_status = "Photo attached" if image_media_id else "No photo / placeholder will be used"

    send_message(
        phone,
        "✅ *PRODUCT SUBMITTED FOR REVIEW*\n\n"
        f"Product ID: {product_id}\n"
        f"Name: {name}\n"
        f"Category: {category}\n"
        f"Price: {price} {unit}\n"
        f"Photo: {photo_status}\n\n"
        "Your product has been sent to Admin for approval.\n"
        "It will appear in the marketplace after approval.\n\n"
        "What do you want to do next?\n\n"
        "1️⃣ Add another product\n"
        "2️⃣ Go to main menu\n\n"
        "Reply with *1* or *2*."
    )

    send_admin_alert(
        "NEW MARKETPLACE PRODUCT NEEDS APPROVAL",
        f"Product ID: {product_id}\n"
        f"Seller: {seller_name}\n"
        f"Seller Phone: {phone}\n"
        f"Category: {category}\n"
        f"Product: {name}\n"
        f"Description: {description}\n"
        f"Price: {price} {unit}\n"
        f"Location: {seller_location}\n"
        f"Photo: {photo_status}\n\n"
        f"✅ Approve using:\n"
        f"approve product {product_id}\n\n"
        f"❌ Reject using:\n"
        f"reject product {product_id}"
    )

    return product_id


def approve_marketplace_product(product_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE marketplace_products
        SET status='active'
        WHERE id=%s
        RETURNING name, seller_phone
    """, (product_id,))

    row = c.fetchone()

    conn.commit()
    release_db(conn)

    return row


def reject_marketplace_product(product_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE marketplace_products
        SET status='rejected'
        WHERE id=%s
        RETURNING name, seller_phone
    """, (product_id,))

    row = c.fetchone()

    conn.commit()
    release_db(conn)

    return row

import re

def parse_app_marketplace_order(raw_text):
    customer = ""
    delivery = ""
    note = ""
    items = []

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    for line in lines:
        low = line.lower()

        if low.startswith("customer:"):
            customer = line.split(":", 1)[1].strip()

        elif low.startswith("delivery:"):
            delivery = line.split(":", 1)[1].strip()

        elif low.startswith("note:"):
            note = line.split(":", 1)[1].strip()

        elif re.match(r"^\d+\.", line):
            parts = [p.strip() for p in line.split("|")]

            name = ""
            qty = "1"
            price = ""
            seller_name = ""
            seller_phone = ""

            first = parts[0]
            if "." in first:
                name = first.split(".", 1)[1].strip()
            else:
                name = first.strip()

            for p in parts[1:]:
                pl = p.lower()

                if pl.startswith("qty:"):
                    qty = p.split(":", 1)[1].strip()

                elif pl.startswith("price:"):
                    price = p.split(":", 1)[1].strip()

                elif pl.startswith("seller:"):
                    seller_name = p.split(":", 1)[1].strip()

                elif pl.startswith("seller phone:"):
                    seller_phone = normalize_phone(p.split(":", 1)[1].strip())

            items.append({
                "name": name,
                "qty": qty,
                "price": price,
                "seller_name": seller_name,
                "seller_phone": seller_phone
            })

    return {
        "customer": customer,
        "delivery": delivery,
        "note": note,
        "items": items
    }


def send_marketplace_order_to_admin_and_sellers(order_data, buyer_phone):
    items = order_data.get("items", [])
    customer = order_data.get("customer", buyer_phone)
    delivery = order_data.get("delivery", "")
    note = order_data.get("note", "")

    if not items:
        return False

    admin_text = "🛒 *NEW MARKETPLACE APP ORDER*\n\n"
    admin_text += f"Customer: {customer}\n"
    admin_text += f"WhatsApp: {buyer_phone}\n"

    if delivery:
        admin_text += f"Delivery: {delivery}\n"

    if note:
        admin_text += f"Note: {note}\n"

    admin_text += "\nItems:\n"

    for i, item in enumerate(items, start=1):
        admin_text += (
            f"{i}. {item['name']} | Qty: {item['qty']} | Price: {item['price']}\n"
            f"   Seller: {item['seller_name']} | {item['seller_phone']}\n"
        )

    send_admin_alert("MARKETPLACE ORDER", admin_text)

    grouped = {}

    for item in items:
        seller_phone = item.get("seller_phone", "").strip()

        if not seller_phone:
            continue

        if seller_phone not in grouped:
            grouped[seller_phone] = []

        grouped[seller_phone].append(item)

    for seller_phone, seller_items in grouped.items():
        seller_name = seller_items[0].get("seller_name", "Seller")

        seller_text = "🛒 *NEW PRODUCT ORDER*\n\n"
        seller_text += f"Customer: {customer}\n"
        seller_text += f"Customer WhatsApp: {buyer_phone}\n"

        if delivery:
            seller_text += f"Delivery: {delivery}\n"

        if note:
            seller_text += f"Note: {note}\n"

        seller_text += "\nProducts ordered from you:\n"

        for i, item in enumerate(seller_items, start=1):
            seller_text += f"{i}. {item['name']} | Qty: {item['qty']} | Price: {item['price']}\n"

        seller_text += "\nPlease contact the customer directly."

        send_message(seller_phone, seller_text)

    return True

def parse_marketplace_cart(cart_text):
    """
    Cart format stored in marketplace_carts.cart:
    12:2,15:1,20:4

    Means:
    product 12 qty 2
    product 15 qty 1
    product 20 qty 4
    """

    cart = {}

    if not cart_text:
        return cart

    raw = cart_text.replace("cart:", "").strip()

    if not raw:
        return cart

    for part in raw.split(","):
        if ":" not in part:
            continue

        product_id, qty = part.split(":", 1)

        if product_id.strip().isdigit() and qty.strip().isdigit():
            qty_value = int(qty.strip())

            if qty_value > 0:
                cart[int(product_id.strip())] = qty_value

    return cart


def save_marketplace_cart(phone, cart):
    """
    Saves cart in marketplace_carts so browsing/searching does not erase it.
    """

    cart_text = ",".join(
        [f"{product_id}:{qty}" for product_id, qty in cart.items() if qty > 0]
    )

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO marketplace_carts (phone, cart)
        VALUES (%s, %s)
        ON CONFLICT (phone)
        DO UPDATE SET cart = EXCLUDED.cart,
                      updated_at = CURRENT_TIMESTAMP
    """, (phone, cart_text))

    conn.commit()
    release_db(conn)


def get_marketplace_cart(phone):
    """
    Reads cart from marketplace_carts.
    Do NOT read from marketplace_temp because marketplace_temp is used for
    featured/results/selected_product/seller-upload states.
    """

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT cart FROM marketplace_carts WHERE phone=%s", (phone,))
    row = c.fetchone()

    release_db(conn)

    return parse_marketplace_cart(row[0]) if row and row[0] else {}


def add_product_to_cart(phone, product_id, qty=1):
    cart = get_marketplace_cart(phone)

    if product_id in cart:
        cart[product_id] += qty
    else:
        cart[product_id] = qty

    save_marketplace_cart(phone, cart)

    return cart


def remove_product_from_cart(phone, product_id):
    cart = get_marketplace_cart(phone)

    if product_id in cart:
        del cart[product_id]

    save_marketplace_cart(phone, cart)

    return cart


def clear_marketplace_cart(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM marketplace_carts WHERE phone=%s", (phone,))

    conn.commit()
    release_db(conn)


def get_products_from_cart(cart):
    """
    Returns full product details for all cart items.
    """

    products = []

    for product_id, qty in cart.items():
        product = get_marketplace_product(product_id)

        if not product:
            continue

        (
            pid, category, name, description, price, unit,
            seller_name, seller_phone, seller_location,
            image_url, image_media_id, status
        ) = product

        products.append({
            "id": pid,
            "category": category,
            "name": name,
            "description": description,
            "price": price,
            "unit": unit,
            "seller_name": seller_name,
            "seller_phone": seller_phone,
            "seller_location": seller_location,
            "qty": qty
        })

    return products


def build_cart_message(phone):
    cart = get_marketplace_cart(phone)
    products = get_products_from_cart(cart)

    if not products:
        return (
            "🛒 *YOUR CART IS EMPTY*\n\n"
            "Go back to the marketplace and add products first.\n\n"
            "Type *MARKET* to continue shopping."
        )

    text = "🛒 *YOUR MARKETPLACE CART*\n\n"

    for i, p in enumerate(products, start=1):
        text += (
            f"{i}. {p['name']}\n"
            f"   Qty: {p['qty']}\n"
            f"   Price: {p['price']} {p['unit']}\n"
            f"   Seller: {p['seller_name']}\n"
            f"   Contact: {p['seller_phone']}\n\n"
        )

    text += (
        "Reply:\n"
        "✅ *CHECKOUT* to place order\n"
        "🗑 *REMOVE 1* to remove item number 1\n"
        "❌ *CLEAR* to empty cart\n"
        "🛒 *MARKET* to continue shopping"
    )

    return text


def build_order_data_from_cart(phone, delivery="", note=""):
    cart = get_marketplace_cart(phone)
    products = get_products_from_cart(cart)

    items = []

    for p in products:
        seller_phone = p["seller_phone"] or ""

        if seller_phone:
            seller_phone = normalize_phone(seller_phone)

        items.append({
            "name": p["name"],
            "qty": str(p["qty"]),
            "price": f"{p['price']} {p['unit']}".strip(),
            "seller_name": p["seller_name"],
            "seller_phone": seller_phone
        })

    return {
        "customer": phone,
        "delivery": delivery,
        "note": note,
        "items": items
    }
    
def detect_module_from_question(question, allowed_modules):
    if not question:
        return None

    q = question.lower()

    keyword_map = {
        "dishwash": "dishwash",
        "dish wash": "dishwash",

        "bleach": "thick_bleach",
        "jik": "thick_bleach",

        "foam": "foam_bath",
        "pine": "pine_gel",
        "toilet": "toilet_cleaner",

        "engine": "engine_cleaner",
        "engine 2": "engine_cleaner2",

        "laundry": "laundry_bar",
        "bar soap": "laundry_bar",

        "fabric": "fabric_softener",
        "softener": "fabric_softener",

        "petroleum": "petroleum_jelly",
        "vaseline": "petroleum_jelly",

        "floor polish": "floor_polish",

        "car shampoo": "car_shampoo",
        "car wash": "car_shampoo",

        "degreaser": "acidic_metal_degreaser",
        "acid": "acidic_metal_degreaser",

        "tyre": "tyre_polish",

        "shoe polish": "paste_shoe_polish",
        "liquid polish": "liquid_shoe_polish",

        "tile": "tile_cleaner",

        "conditioner": "hair_conditioner",
        "hair shampoo": "hair_shampoo",

        "washing paste": "washing_paste",
        "bath soap": "bath_soap",

        "freezits": "freezits",
        "ice cream": "ice_cream",

        "baobab": "baobab_drink",
        "cascade": "juice_cascade",
        "orange drink": "orange_drink",
        "raspberry": "raspberry_drink",
        "cream soda": "cream_soda",

        "low cost orange": "low_cost_orange_drink",
        "orange drink": "orange_drink",

        "low cost raspberry": "low_cost_raspberry_drink",

        "universal cordial": "universal_cordial",
        "cordial": "universal_cordial" 
    }

    # 1️⃣ strict keyword match but only if user owns module
    for key, module in keyword_map.items():
        if key in q and module in allowed_modules:
            return module

    # if no keyword match → stay in last module
    if allowed_modules:
        return allowed_modules[-1]


    # 2️⃣ direct module name mention
    for module in allowed_modules:
        if module.replace("_", " ") in q:
            return module

    # 3️⃣ fallback = last opened module
    return allowed_modules[-1] if allowed_modules else None

def open_lesson_direct(phone, module):
    modules = load_lessons()

    if module not in modules:
        send_message(phone, "❌ Lesson PDF not found. Upload it in admin.")
        return

    pdf, label = modules[module]

    record_module_access(phone, module)
    update_metrics(phone, "module")
    log_activity(phone, "open_module", module)

    send_message(
        phone,
        f"{label}\n\n📱 This lesson is now read inside the Arachis App.\n\nType *MENU* then choose *10 - Download App*.\n\n🤖 AI support is still available here."
    )

    if not whatsapp_media_disabled_for(phone):
        send_message(phone, "🎧 Lesson audio (listen in order) 👇")

    send_audio_series(phone, module)

    send_pdf(
        phone,
        f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}",
        label
    )

    send_message(
        phone,
        "Kana pane chausinganzwisise, bvunza pano 🤖\n\n"
        "➡️ Type *NEXT* to return to lessons.\n"
        "🏠 Type *MENU* for main dashboard."
    )

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET active_module=%s WHERE phone=%s",
        (module, phone)
    )
    conn.commit()
    release_db(conn)
    
def find_direct_lesson_match(incoming):
    lesson_aliases = {
        # Detergents
        "dishwash": "dishwash",
        "dish wash": "dishwash",
        "liquid laundry soap": "liquid_laundry_soap",
        "fabric softener": "fabric_softener",
        "bleach": "thick_bleach",
        "thick bleach": "thick_bleach",
        "washing paste": "washing_paste",
        "toilet cleaner": "toilet_cleaner",
        "pine gel": "pine_gel",
        "pinegel": "pine_gel",
        "foam bath": "foam_bath",
        "car shampoo": "car_shampoo",
        "engine cleaner": "engine_cleaner",
        "perfume": "perfume",
        "tile cleaner": "tile_cleaner",
        "floor polish": "floor_polish",
        "tyre polish": "tyre_polish",
        "shoe polish": "paste_shoe_polish",
        "hair shampoo": "hair_shampoo",
        "hair conditioner": "hair_conditioner",
        "petroleum jelly": "petroleum_jelly",
        "vaseline": "petroleum_jelly",
        "bath soap": "bath_soap",
        "laundry bar": "laundry_bar",
        "washing powder": "washing_powder",
        "scouring powder": "scouring_powder",
        "roll on": "roll_on",
        "roll-on": "roll_on",

        # Beverages
        "baobab": "baobab_drink",
        "baobab drink": "baobab_drink",
        "cream soda": "cream_soda",
        "freezits": "freezits",
        "freezit": "freezits",
        "ice cream": "ice_cream",
        "cascade": "juice_cascade",
        "juice cascade": "juice_cascade",
        "orange drink": "orange_drink",
        "raspberry drink": "raspberry_drink",
        "cordial": "universal_cordial",
        "universal cordial": "universal_cordial",

        # Advanced
        "paint": "paint",
        "gummies": "gummies",
        "gummy": "gummies",
        "glue": "glue",
        "maheu": "maheu",
        "lotion": "lotion",
        "body cream": "body_cream",
        "beauty cream": "body_cream",
        "cream": "body_cream",
        "methylated spirit": "methylated_spirit",
        "battery acid": "battery_acid",
        "deo blocks": "deo_blocks",
        "toilet blocks": "deo_blocks",

        #Spices
        "chicken spice": "chicken_spice",
        "peri peri": "peri_peri_spice",
        "peri peri spice": "peri_peri_spice",
        "curry powder": "curry_powder",
        "curry beef": "curry_beef_spice",
        "curry beef spice": "curry_beef_spice",
        "curry garlic herb": "curry_garlic_herb",
        "rice spice": "rice_spice",
        "tea masala": "tea_masala",
        "ginger powder": "ginger_powder",
        "cinnamon blend": "cinnamon_blend",
        "royco": "royco_style_soup",
        "royco soup": "royco_style_soup",
        "sauce spice": "sauce_spice_base",
        "sauce spice base": "sauce_spice_base",
    }

    cleaned = incoming.lower().strip()

    if cleaned in lesson_aliases:
        return lesson_aliases[cleaned]

    for module in DETERGENT_MODULES + BEVERAGE_MODULES + ADVANCED_MODULES + SPICE_MODULES:
        if cleaned == module.replace("_", " "):
            return module

    return None

def get_registration_name(phone):

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT full_name
        FROM offline_registrations
        WHERE phone=%s
    """, (phone,))

    row = c.fetchone()

    release_db(conn)

    return row[0] if row else ""

# ==========================================
# PENDING ACTION HELPERS
# ==========================================

def set_pending_action(phone, action):

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET pending_action=%s
        WHERE phone=%s
    """, (action, phone))

    conn.commit()
    release_db(conn)

def get_pending_action(phone):

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT pending_action
        FROM users
        WHERE phone=%s
    """, (phone,))

    row = c.fetchone()

    release_db(conn)

    if row:
        return row[0]

    return None


def clear_pending_action(phone):

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET pending_action=NULL
        WHERE phone=%s
    """, (phone,))

    conn.commit()
    release_db(conn)

# ==========================================
# ARACHIS BRAIN
# ==========================================

def route_employee(message):

    text = message.lower().strip()

    # ----------------------------
    # PRACTICAL TRAINING
    # ----------------------------

    training = [
        "training",
        "offline",
        "practical",
        "workshop",
        "register",
        "registration",
        "book",
        "book seat",
        "reserve",
        "deposit",
        "venue",
        "location",
        "date",
        "when is the training",
        "next training",
        "bulawayo",
        "harare",
        "gweru"
    ]

    if any(word in text for word in training):
        return "TRAINING"


    # ----------------------------
    # PAYMENT
    # ----------------------------

    payment = [
        "pay",
        "payment",
        "ecocash",
        "upgrade",
        "deposit",
        "$5",
        "$10",
        "$20"
    ]

    if any(word in text for word in payment):
        return "PAYMENT"


    # ----------------------------
    # MARKETPLACE
    # ----------------------------

    marketplace = [
        "marketplace",
        "sell",
        "buyer",
        "supplier",
        "suppliers",
        "ingredient",
        "ingredients",
        "machine",
        "equipment",
        "bottle",
        "container",
        "label"
    ]

    if any(word in text for word in marketplace):
        return "MARKETPLACE"


    # ----------------------------
    # CALCULATOR
    # ----------------------------

    calculator = [
        "profit",
        "calculator",
        "cost",
        "pricing",
        "price",
        "calculate"
    ]

    if any(word in text for word in calculator):
        return "CALCULATOR"


    # ----------------------------
    # LESSONS
    # ----------------------------

    lessons = [
        "lesson",
        "continue",
        "pine gel",
        "dishwash",
        "bleach",
        "foam bath",
        "formula",
        "cmc",
        "sles"
    ]

    if any(word in text for word in lessons):
        return "LESSON"


    return "AI"
    
# =========================
# WEBHOOK
# =========================

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()
    
    ai_handled = False

    print("WEBHOOK RECEIVED")

    try:
        statuses = data["entry"][0]["changes"][0]["value"].get("statuses", [])

        if statuses:
            conn = get_db()
            c = conn.cursor()

            for s in statuses:
                message_id = s.get("id")
                status = s.get("status")
                error_details = ""

                if "errors" in s:
                    error_details = str(s["errors"])

                c.execute("""
                    UPDATE template_messages
                    SET status=%s,
                        error_details=%s,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE whatsapp_message_id=%s
                """, (status, error_details, message_id))

                print("📩 TEMPLATE DELIVERY STATUS:", message_id, status, error_details)

            conn.commit()
            release_db(conn)

            return "OK", 200

    except Exception as e:
        print("STATUS WEBHOOK ERROR:", e)

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = normalize_phone(message["from"])
        message_id = message["id"]

        msg_type = message["type"]

        if msg_type == "text":
            incoming = message["text"]["body"].strip().lower()

        elif msg_type == "button":
            incoming = message["button"]["text"].strip().lower()

        elif msg_type == "interactive":
            interactive = message.get("interactive", {})

            if interactive.get("type") == "button_reply":
                incoming = interactive["button_reply"]["title"].strip().lower()
            elif interactive.get("type") == "list_reply":
                incoming = interactive["list_reply"]["title"].strip().lower()
            else:
                incoming = ""

        else:
            incoming = ""

        if already_processed_message(message_id, phone, incoming):
            print("⚠️ DUPLICATE MESSAGE IGNORED:", message_id)
            return "OK", 200

        update_metrics(phone, "message")
        log_activity(phone, "incoming_message", msg_type)

    except Exception:
        return "OK", 200

    create_user(phone)
    user = get_user(phone)
    if not user:
        return "OK", 200


    # =========================
    # QUICK LESSON SHORTCUTS
    # =========================
    lesson_shortcuts = {
        "detergents": "detergents_menu",
        "detergent": "detergents_menu",
        "ma detergents": "detergents_menu",
        "beverages": "beverages_menu",
        "drinks": "beverages_menu",
        "madrinks": "beverages_menu",
        "advanced": "advanced_menu",
        "advanced manufacturing": "advanced_menu",
        "manufacturing": "advanced_menu",
        "spices": "spices_menu",
        "spice": "spices_menu",
        "seasonings": "spices_menu",
        "spices and seasonings": "spices_menu",
    }

    if incoming in lesson_shortcuts:
        fresh_user = get_user(phone)

        if not fresh_user["is_paid"]:
            send_message(phone, "🔒 Lessons are for paid students only.\nNyora *PAY* kuti utange.")
            return jsonify({"status": "ok"})

        target_state = lesson_shortcuts[incoming]
        set_state(phone, target_state)

        if target_state == "detergents_menu":
            send_message(phone, build_detergent_menu(phone))

        elif target_state == "beverages_menu":
            send_message(phone, build_beverage_menu(phone))

        elif target_state == "advanced_menu":
            send_message(phone, build_advanced_menu(phone))

        elif target_state == "spices_menu":
            send_message(phone, build_spices_menu(phone))

        return jsonify({"status": "ok"})

    # =========================
    # DOWNLOAD APP SHORTCUTS
    # Do NOT include "10" here because 10 can also be a lesson number
    # =========================
    if incoming in ["app", "apk", "download app", "download apk", "android app"]:
        send_app_download(phone)
        return jsonify({"status": "ok"})

    if incoming in ["market", "marketplace", "buy", "shop"]:
        set_state(phone, "marketplace_home")
        send_message(phone, build_marketplace_home(phone))
        return jsonify({"status": "ok"})

    if incoming in ["cart", "my cart", "basket"]:
        set_state(phone, "marketplace_cart")
        send_message(phone, build_cart_message(phone))
        return jsonify({"status": "ok"})

    # =========================
    # APP SHORTCUTS: MARKETPLACE SELL + PAYMENT CONFIRMATION
    # These commands come from the Android app buttons.
    # Put this BEFORE direct lesson opening and BEFORE AI handling.
    # =========================

    if incoming.startswith("arachis_marketplace_sell") or incoming in ["sell product", "upload product", "post product"]:
        set_state(phone, "marketplace_sell_category")

        send_message(
            phone,
            "📤 *SELL YOUR PRODUCT ON ARACHIS MARKETPLACE*\n\n"
            "Choose product category:\n\n"
            "1️⃣ Beverages\n"
            "2️⃣ Detergents\n"
            "3️⃣ Spices\n"
            "4️⃣ Advanced Products\n"
            "5️⃣ Packaging\n"
            "6️⃣ Machinery and Tools\n"
            "7️⃣ Branding and Labels\n\n"
            "Reply with category number."
        )

        return jsonify({"status": "ok"})

    if incoming.startswith("arachis_app_payment_confirmation"):

        # This message comes from the Android app's "I have paid" button.
        # It must NOT approve payment.
        # It only prepares the user for EcoCash SMS verification.

        selected_plan = "premium"

        if "plan id:" in incoming:
            try:
                selected_plan = incoming.split("plan id:", 1)[1].split("\n", 1)[0].strip().lower()
            except Exception:
                selected_plan = "premium"

        if selected_plan not in ["basic", "premium", "custom", "advanced", "spices"]:
            if "basic" in incoming:
                selected_plan = "basic"
            elif "advanced" in incoming:
                selected_plan = "advanced"
            elif "spices" in incoming:
                selected_plan = "spices"
            elif "custom" in incoming:
                selected_plan = "custom"
            else:
                selected_plan = "premium"

        conn = get_db()
        c = conn.cursor()

        if selected_plan == "advanced":
            c.execute("""
                UPDATE users
                SET pending_purchase='advanced_full',
                    package='none',
                    payment_status='awaiting',
                    is_paid=0
                WHERE phone=%s
            """, (phone,))

        elif selected_plan == "spices":
            c.execute("""
                UPDATE users
                SET pending_purchase='spices_full',
                    package='none',
                    payment_status='awaiting',
                    is_paid=0
                WHERE phone=%s
            """, (phone,))

        elif selected_plan == "basic":
            c.execute("""
                UPDATE users
                SET package='basic',
                    pending_purchase=NULL,
                    payment_status='awaiting',
                    is_paid=0
                WHERE phone=%s
            """, (phone,))

        elif selected_plan == "custom":
            c.execute("""
                UPDATE users
                SET package='custom',
                    pending_purchase=NULL,
                    payment_status='awaiting',
                    is_paid=0
                WHERE phone=%s
            """, (phone,))

        else:
            c.execute("""
                UPDATE users
                SET package='premium',
                    pending_purchase=NULL,
                    payment_status='awaiting',
                    is_paid=0
                WHERE phone=%s
            """, (phone,))

        conn.commit()
        release_db(conn)

        if selected_plan == "custom":
            try:
                formula_line = ""

                for line in incoming.split("\n"):
                    if line.lower().startswith("custom formula ids:"):
                        formula_line = line.split(":", 1)[1].strip()
                        break

                if formula_line:
                    clear_custom_modules(phone)

                    all_modules = DETERGENT_MODULES + BEVERAGE_MODULES + ADVANCED_MODULES + SPICE_MODULES

                    for module in [x.strip().lower() for x in formula_line.split(",") if x.strip()]:
                        if module in all_modules:
                            add_custom_module(phone, module)

            except Exception as e:
                print("APP CUSTOM FORMULA SAVE ERROR:", e)

        set_state(phone, "awaiting_payment")

        send_message(
            phone,
            "✅ *PAYMENT CONFIRMATION MODE*\n\n"
            f"Plan selected from app: *{selected_plan.upper()}*\n\n"
            "Now send your full EcoCash confirmation SMS here.\n\n"
            "⚠️ Do not type only 'I have paid'.\n"
            "The message must include:\n"
            "✔ Amount paid\n"
            "✔ EcoCash reference number\n"
            "✔ EcoCash confirmation wording\n\n"
            "The bot will approve automatically only after receiving a valid EcoCash confirmation SMS."
        )

        return jsonify({"status": "ok"})

    if incoming.startswith("arachis_marketplace_order"):

        raw_text = ""

        if msg_type == "text":
            raw_text = message["text"]["body"].strip()
        else:
            raw_text = incoming

        order_data = parse_app_marketplace_order(raw_text)

        if not order_data.get("items"):
            send_message(
                phone,
                "❌ No valid products were found in your order.\nPlease go back to the app and try again."
            )
            return jsonify({"status": "ok"})

        ok = send_marketplace_order_to_admin_and_sellers(order_data, phone)

        if ok:
            send_message(
                phone,
                "✅ *ORDER RECEIVED*\n\n"
                "Your marketplace order has been sent to:\n"
                "✔ Admin\n"
                "✔ Seller(s)\n\n"
                "The seller will contact you directly to confirm stock, payment and delivery."
            )
        else:
            send_message(
                phone,
                "❌ Failed to process your order.\nPlease try again."
            )

        return jsonify({"status": "ok"})

    # ==========================================
    # UNIFIED ADMIN APPROVAL COMMAND
    # ==========================================

    if phone in ADMIN_NUMBERS and incoming.strip().lower().startswith("approve "):

        parts = incoming.strip().split()

    # ------------------------------------------
    # BASIC COMMAND VALIDATION
    # ------------------------------------------

        if len(parts) < 2:
            send_message(
                phone,
                "❌ Invalid approval command.\n\n"
                "ONLINE LESSON:\n"
                "approve +2637xxxx basic\n"
                "approve +2637xxxx premium\n"
                "approve +2637xxxx advanced\n"
                "approve +2637xxxx spices\n"
                "approve +2637xxxx custom dishwash\n\n"
                "OFFLINE TRAINING:\n"
                "approve AR-XXXXX"
            )
            return jsonify({"status": "ok"})


        target = parts[1].strip()


    # ==========================================
    # OFFLINE PRACTICAL TRAINING APPROVAL
    # ==========================================
        #
        # Offline booking numbers start with AR-
        #
        # Example:
        # approve AR-123-20260817-4567
        #

        if target.upper().startswith("AR-"):

            booking = target

            conn = get_db()
            c = conn.cursor()

            c.execute("""
                SELECT
                    phone,
                    event_id,
                    full_name,
                    event_title
                FROM offline_registrations
                WHERE booking_number=%s
            """, (booking,))

            row = c.fetchone()

            if not row:
                release_db(conn)

                send_message(
                    phone,
                    f"❌ Booking number not found.\n\n"
                    f"Booking: {booking}"
                )

                return jsonify({"status": "ok"})


            student_phone = row[0]
            event_id = row[1]
            full_name = row[2]
            event_title = row[3]

            # Approve registration
            c.execute("""
                UPDATE offline_registrations
                SET registration_status='Deposit Approved'
                WHERE booking_number=%s
            """, (booking,))

            conn.commit()
            release_db(conn)


            # Notify student
            send_message(
                student_phone,
                f"🎉 *DEPOSIT APPROVED!*\n\n"
                f"Hello {full_name},\n\n"
                f"Your $5 deposit for:\n"
                f"🎓 {event_title}\n\n"
                f"has been successfully approved.\n\n"
                f"🎟 Booking Number: {booking}\n\n"
                f"✅ Your seat is now RESERVED.\n\n"
                f"💵 Balance to pay on training day: $15\n\n"
                f"We look forward to seeing you at the training."
            )


            # Notify admin
            send_message(
                phone,
                f"✅ *OFFLINE TRAINING APPROVED*\n\n"
                f"Student: {full_name}\n"
                f"Phone: {student_phone}\n"
                f"Booking: {booking}\n"
                f"Training: {event_title}"
            )

            return jsonify({"status": "ok"})


    # ==========================================
    # ONLINE LESSON APPROVAL
    # ==========================================

        # Expected:
        #
        # approve +263772926711 basic
        # approve +263772926711 premium
        # approve +263772926711 advanced
        # approve +263772926711 spices
        # approve +263772926711 custom foam_bath
        #

        if not target.startswith("+"):

            send_message(
                phone,
                "❌ Invalid approval command.\n\n"
                "For online lessons use:\n"
                "approve +2637xxxx package\n\n"
                "Example:\n"
                "approve +263772926711 custom foam_bath\n\n"
                "For practical training use:\n"
                "approve AR-XXXXX"
            )

            return jsonify({"status": "ok"})


        # Need at least:
        # approve
        # phone
        # package

        if len(parts) < 3:

            send_message(
                phone,
                "❌ Missing package.\n\n"
                "Use:\n"
                "approve +2637xxxx basic\n"
                "approve +2637xxxx premium\n"
                "approve +2637xxxx advanced\n"
                "approve +2637xxxx spices\n"
                "approve +2637xxxx custom foam_bath"
            )

            return jsonify({"status": "ok"})


        target = normalize_phone(parts[1])
        package = parts[2].lower().strip()


    # ==========================================
    # CUSTOM ONLINE LESSON
    # ==========================================

        if package == "custom":

            if len(parts) < 4:

                send_message(
                    phone,
                    "❌ Custom formula is missing.\n\n"
                    "Use:\n"
                    "approve +2637xxxx custom module_name\n\n"
                    "Example:\n"
                    "approve +263772926711 custom foam_bath"
                )

                return jsonify({"status": "ok"})


            module = parts[3].lower().strip()


            all_modules = (
                DETERGENT_MODULES
                + BEVERAGE_MODULES
                + ADVANCED_MODULES
                + SPICE_MODULES
            )


            if module not in all_modules:

                send_message(
                    phone,
                    "❌ Invalid module name.\n\n"
                    "Examples:\n"
                    "dishwash\n"
                    "foam_bath\n"
                    "pine_gel\n"
                    "freezits\n"
                    "paint"
                )

                return jsonify({"status": "ok"})


            create_user(target)


            conn = get_db()
            c = conn.cursor()


            # Approve payment
            c.execute("""
                UPDATE users
                SET
                    is_paid=1,
                    payment_status='approved',
                    package='custom'
                WHERE phone=%s
            """, (target,))


        # Unlock custom module
            c.execute("""
                INSERT INTO custom_module_access (phone, module)
                VALUES (%s, %s)
                ON CONFLICT (phone, module) DO NOTHING
            """, (target, module))


        # Also unlock normal module access
            c.execute("""
                INSERT INTO module_access (phone, module)
                VALUES (%s, %s)
                ON CONFLICT (phone, module) DO NOTHING
            """, (target, module))


            conn.commit()
            release_db(conn)


            log_activity(
                target,
                "manual_custom_approved",
                module
            )


        # Student notification
            send_message(
                target,
                f"🎉 *Payment Approved!*\n\n"
                f"Custom Formula Unlocked:\n"
                f"✔ {module.replace('_', ' ').title()}\n\n"
                f"Nyora *MENU* kuti uvhure lesson yako."
            )


        # Admin confirmation
            send_message(
                phone,
                f"✅ *ONLINE PAYMENT APPROVED*\n\n"
                f"Student: {target}\n"
                f"Package: CUSTOM\n"
                f"Formula: {module.replace('_', ' ').title()}"
            )


            return jsonify({"status": "ok"})


    # ==========================================
    # NORMAL ONLINE PACKAGES
    # ==========================================

        if package not in [
            "basic",
            "premium",
            "advanced",
            "spices"
        ]:

            send_message(
                phone,
                "❌ Invalid package.\n\n"
                "Available packages:\n"
                "basic\n"
                "premium\n"
                "advanced\n"
                "spices\n"
                "custom"
            )

            return jsonify({"status": "ok"})


        create_user(target)


        conn = get_db()
        c = conn.cursor()


        has_spices = 1 if package in [
            "spices",
            "advanced"
        ] else 0

        has_advanced = 1 if package == "advanced" else 0


        c.execute("""
            UPDATE users
            SET
                is_paid=1,
                payment_status='approved',
                package=%s,
                has_spices=%s,
                has_advanced=%s,
                pending_purchase=NULL
            WHERE phone=%s
        """, (
            package,
            has_spices,
            has_advanced,
            target
        ))


        conn.commit()
        release_db(conn)


    # Student notification
        send_message(
            target,
            f"🎉 *Payment Approved!*\n\n"
            f"Package: {package.upper()}\n\n"
            f"Nyora *MENU* kuti utange kudzidza."
        )


    # Admin confirmation
        send_message(
            phone,
            f"✅ *ONLINE PAYMENT APPROVED*\n\n"
            f"Student: {target}\n"
            f"Package: {package.upper()}"
        )


        return jsonify({"status": "ok"})

    user = get_user(phone)
    state = user.get("state", STATE_MAIN)

    # ==========================================
    # GLOBAL COMMANDS
    # ==========================================

    incoming_upper = incoming.strip().upper()

    # Main dashboard
    if incoming_upper in ["MENU", "HOME", "START"]:

        set_state(phone, STATE_MAIN)

        send_message(
            phone,
            main_menu(user, phone)
        )

        return jsonify({"status": "ok"})


    # Help
    if incoming_upper == "HELP":

        send_message(
            phone,
            "🤖 *ARACHIS HELP*\n\n"
            "You can:\n\n"
            "• Type *MENU* to return to the dashboard.\n"
            "• Ask any manufacturing question.\n"
            "• Ask about training.\n"
            "• Ask about suppliers.\n"
            "• Ask about your business.\n\n"
            "Example:\n"
            "\"How do I make Dishwash?\""
        )

        return jsonify({"status": "ok"})


    # Cancel current operation
    if incoming_upper == "CANCEL":

        set_state(phone, STATE_MAIN)

        send_message(
            phone,
            "✅ Current operation cancelled.\n\n"
            + main_menu(user, phone)
        )

        return jsonify({"status": "ok"})


    # Back
    if incoming_upper == "BACK":

        set_state(phone, STATE_MAIN)

        send_message(
            phone,
            main_menu(user, phone)
        )

        return jsonify({"status": "ok"})

    # ==========================================
    # PENDING ACTION HANDLER
    # ==========================================

    pending_action = get_pending_action(phone)

    if pending_action == "training_registration":

        text = incoming.lower().strip()

        registration_confirmations = [
            "yes",
            "yes please",
            "yes i want to book",
            "yes i want to register",
            "i want to book",
            "i want to register",
            "book",
            "book me",
            "register",
            "register me",
            "booking",
            "proceed",
            "yes proceed",
            "continue",
            "ok",
            "okay",
            "sure",
            "interested",
            "join",
            "reserve",
            "reserve my seat"
        ]

        if any(
            phrase in text
            for phrase in registration_confirmations
        ):

            clear_pending_action(phone)

            set_state(phone, "offline_name")

            send_message(
                phone,
                "🎓 *PRACTICAL TRAINING REGISTRATION*\n\n"

                "Great! Let's reserve your seat.\n\n"

                "💵 Training Fee: $20\n"
                "💳 Deposit Required: $5\n"
                "💰 Balance: $15\n\n"

                "Your seat will be reserved once the $5 deposit "
                "has been confirmed.\n\n"

                "✍🏽 Please enter your *FULL NAME*."
            )

            return jsonify({"status": "ok"})

    # ==========================================
    # LEARN MENU
    # ==========================================

    if state == STATE_LEARN:

        if incoming == "1":

            set_state(phone, STATE_STUDENT_DASHBOARD)

            send_message(
                phone,
                build_student_dashboard(phone)
            )

            return jsonify({"status":"ok"})

        elif incoming == "2":

            set_state(phone, "browse_courses")

            send_message(
                phone,
                build_courses_menu()
            )

            return jsonify({"status":"ok"})

        elif incoming == "3":

            upcoming = get_next_training()

            if not upcoming:

                send_message(
                    phone,
                    "There are currently no practical training events."
                )

                return jsonify({"status":"ok"})

            (
                event_id,
                title,
                city,
                venue,
                event_date,
                start_time,
                fee,
                deposit,
                products,
                status,
                booked,
                seats
            ) = upcoming

            set_state(phone, "offline_name")

            send_message(
                phone,
                f"🎓 *{title}*\n\n"
                f"📍 {venue}\n"
                f"🏙 {city}\n"
                f"📅 {event_date}\n"
                f"🕘 {start_time}\n\n"
                f"💵 Training Fee: ${fee}\n"
                f"💳 Deposit Required: ${deposit}\n\n"

                "📝 Let's reserve your seat.\n\n"

                "Please enter your *FULL NAME*."
            )

            return jsonify({"status":"ok"})


        elif incoming == "4":

            send_app_download(phone)

            return jsonify({"status":"ok"})


        elif incoming == "5":

            incoming = "upgrade"

        elif incoming == "6":

            send_message(
                phone,
                "🏆 *MY CERTIFICATES*\n\n"
                "Certificates will be available after completing eligible courses.\n\n"
                "In a future update, you'll be able to download them directly from the Arachis Business App."
            )

            return jsonify({"status":"ok"})


        elif incoming.upper() in ["MENU","HOME","BACK"]:

            set_state(phone, STATE_MAIN)

            send_message(phone, main_menu(get_user(phone)))

            return jsonify({"status":"ok"})



    # ==========================================
    # MANUFACTURE MENU
    # ==========================================

    elif state == STATE_MANUFACTURE:

        if incoming == "1":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🧪 *PRODUCT FORMULAS*\n\n"
                "Tell me which product you want to make.\n\n"
                "Examples:\n"
                "• Dishwash\n"
                "• Pine Gel\n"
                "• Foam Bath\n"
                "• Fabric Softener\n"
                "• Car Shampoo\n\n"
                "I'll guide you using your Arachis lessons."
            )

            return jsonify({"status":"ok"})

        elif incoming == "2":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "📊 *BATCH CALCULATOR*\n\n"
                "Tell me:\n\n"
                "• Product name\n"
                "• Required batch size\n\n"
                "Example:\n"
                "Calculate 250L Dishwash."
            )

            return jsonify({"status":"ok"})

        elif incoming == "3":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🛠 *PRODUCT TROUBLESHOOTING*\n\n"
                "Describe your problem.\n\n"
                "Examples:\n"
                "• My bleach separated.\n"
                "• My pine gel is too thin.\n"
                "• My dishwash has no foam."
            )

            return jsonify({"status":"ok"})

        elif incoming == "4":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "✅ *QUALITY CONTROL*\n\n"
                "Tell me which product you want to check.\n\n"
                "Example:\n"
                "Check my fabric softener quality."
            )

            return jsonify({"status":"ok"})

        elif incoming == "5":

            set_state(phone, "awaiting_product_photo")

            send_message(
                phone,
                "📷 *PRODUCT ANALYSIS*\n\n"
                "Please send a clear photo of your product.\n\n"
                "You can also describe the problem."
            )

            return jsonify({"status":"ok"})

        elif incoming == "6":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🧪 *INGREDIENT GUIDE*\n\n"
                "Ask about any ingredient.\n\n"
                "Examples:\n"
                "• What is SLES?\n"
                "• What does CMC do?\n"
                "• Can I replace NP9?"
            )

            return jsonify({"status":"ok"})
        elif incoming in ["back","menu","home"]:

            set_state(phone, STATE_MAIN)
            send_message(phone, main_menu(get_user(phone), phone))
            return jsonify({"status":"ok"})


    # ==========================================
    # BUSINESS MENU
    # ==========================================

    elif state == STATE_BUSINESS:

        if incoming == "1":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🚀 *START A MANUFACTURING BUSINESS*\n\n"
                "Tell me about your situation.\n\n"
                "Examples:\n"
                "• I have $100.\n"
                "• I want to start from home.\n"
                "• Which product is most profitable?\n\n"
                "I'll help you build a business plan."
            )

            return jsonify({"status":"ok"})

        elif incoming == "2":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "💰 *PRICING & PROFIT*\n\n"
                "Tell me:\n\n"
                "• Product name\n"
                "• Batch size\n"
                "• Production cost (if known)\n\n"
                "Example:\n"
                "Price my 20L Dishwash."
            )

            return jsonify({"status":"ok"})

        elif incoming == "3":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "📢 *MARKETING ASSISTANT*\n\n"
                "I can help you create:\n\n"
                "• WhatsApp adverts\n"
                "• Facebook posts\n"
                "• Posters\n"
                "• Promotional messages\n\n"
                "Tell me what you want to advertise."
            )

            return jsonify({"status":"ok"})

        elif incoming == "4":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🎨 *BRANDING ASSISTANT*\n\n"
                "I can help with:\n\n"
                "• Product names\n"
                "• Labels\n"
                "• Logos\n"
                "• Packaging ideas\n\n"
                "Tell me about your product."
            )

            return jsonify({"status":"ok"})

        elif incoming == "5":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "💼 *BUSINESS ADVISOR*\n\n"
                "Ask me anything about growing your business.\n\n"
                "Examples:\n"
                "• How do I increase sales?\n"
                "• Which product should I add?\n"
                "• Help me grow my business."
            )

            return jsonify({"status":"ok"})

        elif incoming == "6":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "📈 *FUNDING & GROWTH*\n\n"
                "I can help you:\n\n"
                "• Raise capital\n"
                "• Reinvest profits\n"
                "• Expand your manufacturing business\n\n"
                "Tell me your current situation."
            )

            return jsonify({"status":"ok"})

        elif incoming in ["back","menu","home"]:

            set_state(phone, STATE_MAIN)
            send_message(phone, main_menu(get_user(phone), phone))
            return jsonify({"status":"ok"})


    # ==========================================
    # MARKETPLACE
    # ==========================================

    elif state == STATE_MARKETPLACE:

        if incoming == "1":

            set_state(phone, "marketplace_home")

            send_message(
                phone,
                build_marketplace_home(phone)
            )

            return jsonify({"status":"ok"})

        elif incoming == "2":

            set_state(phone, "supplier_directory")

            send_message(
                phone,
                "🏭 *SUPPLIER DIRECTORY*\n\n"

                "1️⃣ Detergent Ingredients\n"
                "2️⃣ Beverage Ingredients\n"
                "3️⃣ Containers & Bottles\n"
                "4️⃣ Laboratory Equipment\n"
                "5️⃣ Search Any Ingredient\n\n"

                "Reply with a number."
            )

            return jsonify({"status":"ok"})

        elif incoming == "3":

            set_state(phone, "marketplace_sell_category")

            send_message(
                phone,
                "📤 *SELL YOUR PRODUCT ON ARACHIS MARKETPLACE*\n\n"
                "Choose product category:\n\n"
                "1️⃣ Beverages\n"
                "2️⃣ Detergents\n"
                "3️⃣ Spices\n"
                "4️⃣ Advanced Products\n"
                "5️⃣ Packaging\n"
                "6️⃣ Machinery & Tools\n"
                "7️⃣ Branding & Labels\n\n"
                "Reply with category number."
            )

            return jsonify({"status":"ok"})

        elif incoming == "4":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "📦 *PACKAGING SUPPLIERS*\n\n"
                "Tell me what packaging you need.\n\n"
                "Examples:\n"
                "• 500ml bottles\n"
                "• Trigger sprayers\n"
                "• Labels\n"
                "• Buckets"
            )

            return jsonify({"status":"ok"})

        elif incoming == "5":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "⚙ *MACHINERY & EQUIPMENT*\n\n"
                "Tell me what equipment you need.\n\n"
                "Examples:\n"
                "• Mixing tank\n"
                "• Heat sealer\n"
                "• Filling machine\n"
                "• Earth auger"
            )

            return jsonify({"status":"ok"})

        elif incoming == "6":

            set_state(phone, "marketplace_cart")

            send_message(
                phone,
                build_cart_message(phone)
            )

            return jsonify({"status":"ok"})

        elif incoming in ["back","menu","home"]:

            set_state(phone, STATE_MAIN)
            send_message(phone, main_menu(get_user(phone), phone))
            return jsonify({"status":"ok"})


    # ==========================================
    # TOOLS
    # ==========================================

    elif state == STATE_TOOLS:

        if incoming == "1":

            set_state(phone, "calc_menu")

            send_message(
                phone,
                "💰 *PROFIT CALCULATOR*\n\n"
                "Choose calculator:\n\n"
                "1️⃣ Detailed Calculator\n"
                "2️⃣ Quick Calculator\n\n"
                "Reply with 1 or 2."
            )

            return jsonify({"status":"ok"})

        elif incoming == "2":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "📊 *BATCH CALCULATOR*\n\n"
                "Example:\n"
                "Calculate a 500L Pine Gel batch."
            )

            return jsonify({"status":"ok"})

        elif incoming == "3":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "📏 *UNIT CONVERTER*\n\n"
                "Examples:\n"
                "• Convert 5kg to grams.\n"
                "• Convert 250ml to litres.\n"
                "• Convert pounds to kilograms."
            )

            return jsonify({"status":"ok"})

        elif incoming == "4":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🧮 *PRODUCT COSTING*\n\n"
                "Tell me:\n\n"
                "• Product name\n"
                "• Ingredient costs\n\n"
                "I'll calculate the production cost."
            )

            return jsonify({"status":"ok"})

        elif incoming == "5":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🤖 *ARACHIS VIRTUAL EMPLOYEE*\n\n"
                "Ask me anything about manufacturing, business, suppliers, training or your account."
            )

            return jsonify({"status":"ok"})

        elif incoming == "6":

            send_app_download(phone)

            return jsonify({"status":"ok"})

        elif incoming in ["back","menu","home"]:

            set_state(phone, STATE_MAIN)
            send_message(phone, main_menu(get_user(phone), phone))
            return jsonify({"status":"ok"})


    # ==========================================
    # ACCOUNT
    # ==========================================
    elif state == STATE_ACCOUNT:
    
        if incoming == "1":

            send_message(
                phone,
                f"🎓 Your current package is *{get_user(phone)['package'].title()}*."
            )

            return jsonify({"status":"ok"})

        elif incoming == "2":

            set_state(phone, "upgrade_offer")

            send_message(
                phone,
                "⬆ *UPGRADE YOUR ACCOUNT*\n\n"
                "Upgrade from your current package to unlock more lessons.\n\n"
                "1️⃣ Upgrade Now\n"
                "2️⃣ Cancel\n\n"
                "Reply with 1 or 2."
            )

            return jsonify({"status":"ok"})

        

        elif incoming == "3":

            send_message(
                phone,
                "📜 Payment history will appear here in a future update."
            )

            return jsonify({"status":"ok"})

        elif incoming == "4":

            send_message(
                phone,
                "🏆 Certificates will be downloadable from the Arachis Business App."
            )

            return jsonify({"status":"ok"})

        elif incoming == "5":

            send_app_download(phone)

            return jsonify({"status":"ok"})

        elif incoming == "6":

            send_message(
                phone,
                "⚙ Settings are coming soon.\n\n"
                "You'll be able to manage notifications, language and preferences."
            )

            return jsonify({"status":"ok"})

        elif incoming in ["back","menu","home"]:

            set_state(phone, STATE_MAIN)
            send_message(phone, main_menu(get_user(phone), phone))
            return jsonify({"status":"ok"})

    elif state == STATE_STUDENT_DASHBOARD:

        if incoming == "1":

            set_state(phone, STATE_OPEN_LESSONS)

            send_message(
                phone,
                build_open_lessons_menu(phone)
            )

            return jsonify({"status":"ok"})

        elif incoming == "2":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🤖 Ask me anything about your lessons."
            )

            return jsonify({"status":"ok"})


        elif incoming == "3":

            upcoming = get_next_training()

            if upcoming:

                (
                    event_id,
                    title,
                    city,
                    venue,
                    event_date,
                    start_time,
                    fee,
                    deposit,
                    products,
                    status,
                    booked,
                    seats
                ) = upcoming

                send_message(
                    phone,
                    f"🎓 {title}\n\n"
                    f"📍 {city}\n"
                    f"📅 {event_date}\n"
                    f"💵 ${fee}"
                )

            else:

                send_message(
                    phone,
                    "There are currently no practical training events."
                )

            return jsonify({"status":"ok"})


        elif incoming == "4":

            send_app_download(phone)

            return jsonify({"status":"ok"})


        elif incoming == "5":

            send_message(
                phone,
                "💳 Reply *UPGRADE* to view available packages."
            )

            return jsonify({"status":"ok"})


        elif incoming.upper() in ["MENU","BACK","HOME"]:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone), phone)
            )

            return jsonify({"status":"ok"})
    # ==========================================
    # OPEN LESSONS
    # ==========================================

    elif state == STATE_OPEN_LESSONS:

        if incoming == "1":

            send_message(
                phone,
                "📱 Please open the *Arachis Business App*.\n\n"
                "Tap *My Lessons* to continue learning."
            )

            return jsonify({"status":"ok"})


        elif incoming == "2":

            send_app_download(phone)

            return jsonify({"status":"ok"})


        elif incoming == "3":

            send_message(
                phone,
                "🛠 Let's solve your problem.\n\n"
                "Tell me what is happening.\n\n"
                "Examples:\n"
                "• My lessons are locked.\n"
                "• I cannot login.\n"
                "• The app is not opening."
            )

            set_state(phone, "app_support")

            return jsonify({"status":"ok"})


        elif incoming == "4":

            set_state(phone, "ai_virtual_employee" )

            send_message(
                phone,
                "🤖 Ask me anything about your lessons."
            )

            return jsonify({"status":"ok"})


        elif incoming.upper() in ["MENU","BACK","HOME"]:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone), phone)
            )

            return jsonify({"status":"ok"})

    # ==========================================
    # VIRTUAL EMPLOYEE
    # ARACHIS BRAIN
    # ==========================================

    elif state == STATE_VIRTUAL_EMPLOYEE:

        text = incoming.lower().strip()

        # ==========================================
        # MENU
        # ==========================================

        if text in ["menu", "back", "home"]:

            clear_pending_action(phone)

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone))
            )

            return jsonify({"status": "ok"})


    # ==========================================
    # PRACTICAL TRAINING
    # ==========================================

        training_words = [
            "training",
            "offline training",
            "practical training",
            "practical",
            "workshop",
            "bulawayo",
            "harare",
            "gweru",
            "next training",
            "when is the next training",
            "when is training",
            "training date",
            "training dates",
            "training venue",
            "training location",
            "where is the training",
            "where is training",
            "how much is training",
            "training fee",
            "training cost",
            "training deposit",
            "deposit for training"
        ]


        if any(word in text for word in training_words):

            upcoming = get_next_training()

            if not upcoming:

                clear_pending_action(phone)

                send_message(
                    phone,
                    "There are currently no upcoming "
                    "practical training events."
                )

                return jsonify({"status": "ok"})


            (
                event_id,
                title,
                city,
                venue,
                event_date,
                start_time,
                fee,
                deposit,
                products,
                status,
                booked,
                seats
            ) = upcoming


        # ------------------------------------------
        # CHECK AVAILABLE SEATS
        # ------------------------------------------

            try:
                remaining_seats = max(
                    0,
                    int(seats or 0) - int(booked or 0)
                )
            except Exception:
                remaining_seats = 0


        # ------------------------------------------
        # IF USER IS ALREADY ASKING TO REGISTER
        # ------------------------------------------

            registration_words = [
                "register",
                "registration",
                "register me",
                "i want to register",
                "i want to book",
                "book",
                "book me",
                "booking",
                "reserve",
                "reserve my seat",
                "book my seat",
                "sign me up",
                "join training",
                "attend training"
            ]


            if any(word in text for word in registration_words):

                if remaining_seats <= 0:

                    clear_pending_action(phone)

                    send_message(
                        phone,
                        "❌ Unfortunately, this training is now full."
                    )

                    return jsonify({"status": "ok"})


                clear_pending_action(phone)

                set_state(phone, "offline_name")

                send_message(
                    phone,

                    f"🎓 *{title}*\n\n"

                    f"📍 {venue}\n"
                    f"🏙 {city}\n"
                    f"📅 {event_date}\n"
                    f"🕘 {start_time}\n\n"

                    f"💵 Training Fee: ${fee}\n"
                    f"💳 Deposit Required: ${deposit}\n"
                    f"🪑 Seats Remaining: {remaining_seats}\n\n"

                    "📝 *Let's reserve your seat.*\n\n"

                    "✍🏽 Please enter your *FULL NAME*."
                )

                return jsonify({"status": "ok"})


        # ------------------------------------------
        # GENERAL TRAINING INFORMATION
        # ------------------------------------------

            # Remember that the next response may be
            # an acceptance such as YES / PROCEED / BOOK.
            set_pending_action(phone, "training_registration")


            send_message(
                phone,

                f"🎓 *NEXT PRACTICAL TRAINING*\n\n"

                f"📍 {venue}\n"
                f"🏙 {city}\n"
                f"📅 {event_date}\n"
                f"🕘 {start_time}\n\n"

                f"💵 Training Fee: ${fee}\n"
                f"💳 Deposit Required: ${deposit}\n"
                f"🪑 Seats Remaining: {remaining_seats}\n\n"

                "You can reserve your seat with a *$5 deposit*.\n"
                "The remaining balance is paid on or before "
                "the training day.\n\n"

                "Would you like to register for this training?\n\n"

                "Reply *YES* to continue."
            )

            return jsonify({"status": "ok"})


    # ==========================================
    # PAYMENT
    # ==========================================

        payment_words = [
            "pay",
            "payment",
            "payment details",
            "ecocash",
            "upgrade",
            "upgrade my training",
            "upgrade my plan"
        ]


        if any(word in text for word in payment_words):

            clear_pending_action(phone)

            set_state(phone, "pay_menu")

            send_message(
                phone,
                build_payment_menu()
            )

            return jsonify({"status": "ok"})


    # ==========================================
    # SUPPLIERS
    # ==========================================

        supplier_words = [
            "supplier",
            "suppliers",
            "ingredient supplier",
            "ingredient suppliers",
            "where can i buy",
            "where do i buy",
            "chemical supplier",
            "chemical suppliers",
            "container supplier",
            "bottle supplier",
            "packaging supplier"
        ]


        if any(word in text for word in supplier_words):

            clear_pending_action(phone)

            set_state(phone, "supplier_directory")

            send_message(
                phone,
                "🧪 *SUPPLIER DIRECTORY*\n\n"

                "Choose a category:\n\n"

                "1️⃣ Detergent Ingredients\n"
                "2️⃣ Drink Ingredients\n"
                "3️⃣ Containers & Bottles\n"
                "4️⃣ Laboratory Equipment\n"
                "5️⃣ Search for a Supplier\n\n"

                "Reply with 1, 2, 3, 4 or 5."
            )

            return jsonify({"status": "ok"})


    # ==========================================
    # CALCULATOR
    # ==========================================

        calculator_words = [
            "calculator",
            "calculate",
            "calculate profit",
            "profit calculator",
            "profit",
            "cost calculator",
            "costing",
            "cost",
            "pricing",
            "selling price"
        ]


        if any(word in text for word in calculator_words):

            clear_pending_action(phone)

            set_state(phone, STATE_CALCULATOR)

            send_message(
                phone,
                build_calculator_menu()
            )

            return jsonify({"status": "ok"})


    # ==========================================
    # DEFAULT → MANUFACTURING AI
    # ==========================================

        clear_pending_action(phone)

        ai_answer = ai_virtual_employee(
            phone,
            incoming
        )

        send_message(
            phone,
            ai_answer
        )

        log_activity(
            phone,
            "ai_question",
            incoming
        )

        update_metrics(
            phone,
            "ai"
        )

        log_activity(
            phone,
            "ai_answer",
            ai_answer[:500]
        )

        return jsonify({"status": "ok"})

    # ==========================================
    # BROWSE COURSES
    # ==========================================

    elif state == "browse_courses":

        if incoming in ["1","2","3","4","5"]:

            send_message(
                phone,
                build_course_list(incoming)
            )

            return jsonify({"status":"ok"})

        elif incoming.upper() in ["BACK", "MENU", "HOME"]:

            set_state(phone, STATE_LEARN)

            send_message(
                phone,
                build_learn_menu()
            )

            return jsonify({"status":"ok"})

    # ==========================================
    # SUPPLIER DIRECTORY
    # ==========================================

    elif state == "supplier_directory":

        if incoming == "1":

            send_message(
                phone,
                "🧪 *DETERGENT INGREDIENT SUPPLIERS*\n\n"

                "1. Grace Rita Plastics\n"
                "📍 Harare\n"
                "📞 +263775641533\n\n"

                "2. Tamayi Chemicals\n"
                "📍 South Africa\n"
                "📞 +27655521810\n\n"

                "3. Nastovert Chemicals\n"
                "📍 Harare\n"
                "📞 +263774692352\n\n"

                "4. MazChem\n"
                "📍 Harare\n"
                "📞 +263772597141\n\n"

                "5. ArrowChem\n"
                "📍 Bulawayo / Gweru\n"
                "📞 +263780381618"
            )

            return jsonify({"status":"ok"})


        elif incoming == "2":

            send_message(
                phone,
                "🥤 *DRINK INGREDIENT SUPPLIERS*\n\n"

                "1. Codchem Chemicals\n"
                "📍 Harare\n"
                "📞 +263772866766\n\n"

                "2. Acol Chemicals\n"
                "📍 Bulawayo / Harare\n"
                "📞 +263778730915"
            )

            return jsonify({"status":"ok"})


        elif incoming == "3":

            send_message(
                phone,
                "🧴 *CONTAINER & BOTTLE SUPPLIERS*\n\n"

                "1. Grace Rita Plastics\n"
                "📞 +263775641533\n\n"

                "2. BriPak Packaging\n"
                "📞 +263783213322\n\n"

                "3. TekPak Plastics\n"
                "📞 +263775142283"
            )

            return jsonify({"status":"ok"})


        elif incoming == "4":

            send_message(
                phone,
                "🧪 *LABORATORY EQUIPMENT*\n\n"

                "1. Reditek Chemicals\n"
                "📞 +263773903806\n\n"

                "2. Graniteside Chemicals\n"
                "📞 +263774547609\n\n"

                "3. Mega Mark Scientific\n"
                "📞 +263771263978"
            )

            return jsonify({"status":"ok"})


        elif incoming == "5":

            set_state(phone, STATE_VIRTUAL_EMPLOYEE)

            send_message(
                phone,
                "🔎 Tell me which ingredient or equipment you are looking for.\n\n"

                "Examples:\n"
                "• SLES\n"
                "• NP9\n"
                "• Citric Acid\n"
                "• Bottles\n"
                "• Labels"
            )

            return jsonify({"status":"ok"})


        elif incoming.upper() in ["BACK","MENU","HOME"]:

            set_state(phone, STATE_MARKETPLACE)

            send_message(
                phone,
                build_marketplace_menu()
            )

            return jsonify({"status":"ok"})
    

    # 🔥 HANDLE TEMPLATE REPLIES (FIXED)
    if user["state"] == "promo_offer" and incoming in ["yes", "ok", "interested", "view"]:

        set_state(phone, "pay_menu")

        send_message(
            phone,
            "💳 *SELECT YOUR TRAINING PACKAGE*\n\n"
            "1️⃣ Basic – $5\n"
            "2️⃣ Premium – $10\n"
            "3️⃣ Custom – $2 per formula\n"
            "4️⃣ Advanced Manufacturing – $20\n"
            "5️⃣ Spices & Seasonings – $10\n\n"
            "Reply with 1, 2, 3, 4 or 5."
        )

        return jsonify({"status": "ok"})

    if msg_type == "image" and user["state"] == "marketplace_sell_photo":

        media_id = message["image"]["id"]

        finalize_marketplace_product_upload(
            phone=phone,
            image_media_id=media_id
        )

        return jsonify({"status": "ok"})

    if user["state"] == "marketplace_sell_photo" and incoming in ["skip", "no photo", "none", "0"]:

        finalize_marketplace_product_upload(
            phone=phone,
            image_media_id=None
        )

        return jsonify({"status": "ok"})

    if msg_type == "image":

        if not user["is_paid"]:
            send_message(
                phone,
                "📷 Photo analysis is available to paid students only.\nNyora *PAY* kuti utange."
            )
            return jsonify({"status": "ok"})

        media_id = message["image"]["id"]

        image_path = download_whatsapp_image(media_id)

        # store image path temporarily
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO temp_orders (phone, item)
            VALUES (%s,%s)
            ON CONFLICT (phone)
            DO UPDATE SET item = EXCLUDED.item
        """, (phone, image_path))
        conn.commit()
        release_db(conn)

        set_state(phone, "photo_details")

        send_message(
            phone,
            "📷 *PHOTO RECEIVED*\n\n"
            "Ndibatsirei ne details idzi kuti ndi diagnose problem:\n\n"
            "Nyora seizvi:\n\n"
            "Product: Thick Bleach\n"
            "Ingredients: SLES + Hypo + Caustic\n"
            "Batch size: 20 litres\n"
            "Problem: very watery\n\n"
            "Tumira message yako seizvi."
        )

        return jsonify({"status": "ok"})


    # START OF YOUR OLD LOGIC

    if incoming == "admin" and phone in ADMIN_NUMBERS:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_paid=1")
        paid = c.fetchone()[0]
        release_db(conn)
        send_message(phone, f"📊 *ADMIN DASHBOARD*\n\n👥 Users: {total}\n💰 Paid: {paid}")
        return jsonify({"status": "ok"})

    if incoming.lower() == "admin events":

        if phone not in ADMIN_NUMBERS:
            send_message(phone, "Unauthorized.")
            return jsonify({"status": "ok"})

        send_message(phone, admin_training_events())
        return jsonify({"status": "ok"})

    if incoming.startswith("reset device ") and phone in ADMIN_NUMBERS:
        target = incoming.replace("reset device ", "").strip()

        if not target:
            send_message(phone, "Use: reset device +2637xxxxxxxx")
            return jsonify({"status": "ok"})

        target = normalize_phone(target)

        reset_device_lock(target, reset_by=phone)

        send_message(
            target,
            "✅ Your Arachis app device has been reset.\n\n"
            "You can now login on your new phone using your approved WhatsApp number."
        )

        send_message(
            phone,
            f"✅ Device lock reset for {target}"
        )

        return jsonify({"status": "ok"})

    if incoming.startswith("approve product ") and phone in ADMIN_NUMBERS:

        parts = incoming.split()

        if len(parts) < 3 or not parts[2].isdigit():
            send_message(phone, "Use: approve product 12")
            return jsonify({"status": "ok"})

        product_id = int(parts[2])
        result = approve_marketplace_product(product_id)

        if not result:
            send_message(phone, "❌ Product not found.")
            return jsonify({"status": "ok"})

        product_name, seller_phone = result

        send_message(phone, f"✅ Product approved: {product_name}")

        if seller_phone:
            send_message(
                seller_phone,
                f"🎉 Your marketplace product has been approved:\n\n"
                f"✔ {product_name}\n\n"
                "It can now appear in Arachis Marketplace."
            )

        return jsonify({"status": "ok"})

    if incoming.startswith("reject product ") and phone in ADMIN_NUMBERS:

        parts = incoming.split()

        if len(parts) < 3 or not parts[2].isdigit():
            send_message(phone, "Use: reject product 12")
            return jsonify({"status": "ok"})

        product_id = int(parts[2])
        result = reject_marketplace_product(product_id)

        if not result:
            send_message(phone, "❌ Product not found.")
            return jsonify({"status": "ok"})

        product_name, seller_phone = result

        send_message(phone, f"❌ Product rejected: {product_name}")

        if seller_phone:
            send_message(
                seller_phone,
                f"Your marketplace product was not approved:\n\n"
                f"{product_name}\n\n"
                "Please contact Admin if you need help correcting the listing."
            )

        return jsonify({"status": "ok"})

    if incoming.startswith("approve ") and phone in ADMIN_NUMBERS:

        parts = incoming.split()

        if len(parts) < 3:
            send_message(
                phone,
                "Use:\n"
                "approve +2637xxxx basic\n"
                "approve +2637xxxx premium\n"
                "approve +2637xxxx advanced\n"
                "approve +2637xxxx spices\n"
                "approve +2637xxxx custom module_name\n\n"
                "Example:\n"
                "approve +263773208904 custom dishwash"
            )
            return jsonify({"status": "ok"})

        target = normalize_phone(parts[1])
        package = parts[2].lower()

        if package == "custom":

            if len(parts) < 4:
                send_message(
                    phone,
                    "For custom use:\n"
                    "approve +2637xxxx custom module_name\n\n"
                    "Example:\n"
                    "approve +263773208904 custom dishwash"
                )
                return jsonify({"status": "ok"})

            module = parts[3].lower().strip()

            all_modules = DETERGENT_MODULES + BEVERAGE_MODULES + ADVANCED_MODULES + SPICE_MODULES

            if module not in all_modules:
                send_message(
                    phone,
                    "Invalid module name.\n\n"
                    "Use module key like:\n"
                    "dishwash\n"
                    "pine_gel\n"
                    "freezits\n"
                    "paint"
                )
                return jsonify({"status": "ok"})

            create_user(target)

            conn = get_db()
            c = conn.cursor()

            c.execute("""
                UPDATE users
                SET is_paid=1,
                    payment_status='approved',
                    package='custom'
                WHERE phone=%s
            """, (target,))

            c.execute("""
                INSERT INTO custom_module_access (phone, module)
                VALUES (%s, %s)
                ON CONFLICT (phone, module) DO NOTHING
            """, (target, module))

            c.execute("""
                INSERT INTO module_access (phone, module)
                VALUES (%s, %s)
                ON CONFLICT (phone, module) DO NOTHING
            """, (target, module))

            conn.commit()
            release_db(conn)

            log_activity(target, "manual_custom_approved", module)

            send_message(
                target,
                f"🎉 Payment Approved!\n\n"
                f"Custom Formula Unlocked:\n"
                f"✔ {module.replace('_',' ').title()}\n\n"
                "Nyora MENU kuti uvhure lesson yako."
            )

            send_message(
                phone,
                f"✅ Custom approved:\n"
                f"{target}\n"
                f"Formula: {module}"
            )

            return jsonify({"status": "ok"})

        if package not in ["basic", "premium", "advanced", "spices"]:
            send_message(phone, "Package must be basic, premium, spices, advanced or custom")
            return jsonify({"status": "ok"})

        create_user(target)

        conn = get_db()
        c = conn.cursor()

        has_spices = 1 if package in ["spices", "advanced"] else 0
        has_advanced = 1 if package == "advanced" else 0

        c.execute("""
            UPDATE users
            SET is_paid=1,
                payment_status='approved',
                package=%s,
                has_spices=%s,
                has_advanced=%s,
                pending_purchase=NULL
            WHERE phone=%s
        """, (package, has_spices, has_advanced, target))

        conn.commit()
        release_db(conn)

        send_message(target, f"🎉 Payment Approved!\nPackage: {package.upper()}")
        send_message(phone, f"✅ Approved: {target} ({package})")

        return jsonify({"status": "ok"})

    if incoming.lower() in ["menu", "start", "makadini", "hie"]:

        user = get_user(phone)

        # Brand new user
        if not user:

            create_user(phone)   # if your project already has this

            set_state(phone, "qualify")

            send_message(
                phone,
                "👋 *Welcome to Arachis Training!*\n\n"
                "Why do you want to learn?\n\n"
                "1️⃣ Start a business\n"
                "2️⃣ Make products for personal use\n\n"
                "Reply with 1 or 2."
            )

            return jsonify({"status": "ok"})

        # Existing user
        set_state(phone, STATE_MAIN)

        send_message(
            phone,
            main_menu(user)
        )

        return jsonify({"status": "ok"})

    if incoming.lower() == "pay":

        set_state(phone, "pay_menu")

        send_message(
            phone,
            build_payment_menu()
        )

        return jsonify({"status": "ok"})
        
    # =========================
    # HELP MENU
    # =========================
    if user["state"] == "help_menu":

        if incoming == "1":
            send_message(
                phone,
                "💳 *HOW TO PAY*\n\n"
                "*153*1*1*0773208904*amount#\n\n"
                "Send EcoCash confirmation SMS here."
            )

        elif incoming == "2":
            send_message(
                phone,
                "📚 *HOW TO USE COURSE*\n\n"
                "1. Open Course Lessons\n"
                "2. Choose category\n"
                "3. Open lesson\n"
                "4. Listen audio\n"
                "5. Read PDF\n\n"
                "You can ask questions anytime 🤖"
            )

        elif incoming == "3":
            send_message(
                phone,
                "👤 *ADMIN SUPPORT*\n\n"
                "WhatsApp: +263773208904"
            )

        else:
            send_message(phone, "Sarudza 1, 2 or 3")
            return jsonify({"status": "ok"})

        send_message(phone, "\n↩ Nyora MENU kudzokera")
        return jsonify({"status": "ok"})

    # ==========================================
    # MAIN MENU
    # ==========================================

    if user["state"] == STATE_MAIN:

        if incoming == "1":
            set_state(phone, STATE_LEARN)
            send_message(phone, build_learn_menu())
            return jsonify({"status":"ok"})

        elif incoming == "2":
            set_state(phone, STATE_MANUFACTURE)
            send_message(phone, build_manufacture_menu())
            return jsonify({"status":"ok"})

        elif incoming == "3":
            set_state(phone, STATE_BUSINESS)
            send_message(phone, build_business_menu())
            return jsonify({"status":"ok"})

        elif incoming == "4":
            set_state(phone, STATE_MARKETPLACE)
            send_message(phone, build_marketplace_menu())
            return jsonify({"status":"ok"})

        elif incoming == "5":
            set_state(phone, STATE_TOOLS)
            send_message(phone, build_tools_menu())
            return jsonify({"status":"ok"})

        elif incoming == "6":

            set_state(phone, STATE_ACCOUNT)

            send_message(
                phone,
                build_account_dashboard(phone)
            )

            return jsonify({"status":"ok"})
    # =========================
    # QUALIFICATION STAGE
    # =========================

    if user["state"] == "qualify":

        if incoming == "1":

            set_state(phone, "pitch")

            send_message(
                phone,
                "🚀 *Excellent Choice!*\n\n"
                "Arachis has helped many Zimbabweans start businesses making:\n\n"
                "🧴 Detergents\n"
                "🥤 Beverages\n"
                "🌶️ Spices & Seasonings\n"
                "🧴 Cosmetics\n"
                "🏭 Advanced Manufacturing Products\n\n"
                "Many of our students are already earning income from these skills.\n\n"
                "Reply *YES* to see the available training packages."
            )

            return jsonify({"status": "ok"})


        elif incoming == "2":

            set_state(phone, "pitch")

            send_message(
                phone,
                "👏 *Great!*\n\n"
                "You'll learn how to make high-quality products for your home while gaining practical manufacturing skills.\n\n"
                "Many students also discover they can turn these skills into a business later.\n\n"
                "Reply *YES* to see the available training packages."
            )

            return jsonify({"status": "ok"})


        else:

            send_message(
                phone,
                "Please choose:\n\n"
                "1️⃣ Start a business\n"
                "2️⃣ Make products for personal use"
            )

            return jsonify({"status": "ok"})


    # =========================
    # PITCH STAGE
    # =========================

    if user["state"] == "pitch":

        if incoming.lower() in ["yes", "ok", "start", "continue"]:

            set_state(phone, "pay_menu")

            send_message(
                phone,
                "🎓 *CHOOSE YOUR TRAINING PACKAGE*\n\n"
                "Select the package that best suits your goals:\n\n"
                "1️⃣ Basic Training – $5\n"
                "2️⃣ Premium Training – $10\n"
                "3️⃣ Custom Package – $2 per formula\n"
                "4️⃣ Advanced Manufacturing – $20\n"
                "5️⃣ Spices & Seasonings – $10\n\n"
                "Reply with *1, 2, 3, 4 or 5*."
            )

            return jsonify({"status": "ok"})

        elif incoming.upper() in ["BACK", "MENU", "HOME"]:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone), phone))

            return jsonify({"status": "ok"})

        else:

            send_message(
                phone,
                "Reply *YES* to continue or type *MENU* to return to the main menu."
            )

            return jsonify({"status": "ok"})
            
    elif user["state"] == "course_lessons":

        if incoming == "1":

            set_state(phone, "detergents_menu")

            menu = "🧪 *DETERGENT LESSONS*\n\n"
            
            fresh_user = get_user(phone)

            detergent_list = DETERGENT_MODULES

            if fresh_user.get("package") == "basic":
                allowed = PACKAGES["basic"]["modules"]
                detergent_list = [m for m in DETERGENT_MODULES if m in allowed]

            elif fresh_user.get("package") == "custom":
                allowed = get_custom_modules(phone)
                detergent_list = [m for m in DETERGENT_MODULES if m in allowed]

            for i, module in enumerate(detergent_list, start=1):
                name = module.replace("_", " ").title()
                menu += f"{i}️⃣ {name}\n"

            if not detergent_list:
                send_message(phone, "Hauna detergent lessons pa custom package yako.")
                return jsonify({"status": "ok"})

            menu += "\nReply with number"

            send_message(phone, menu)
            return jsonify({"status": "ok"})

        elif incoming == "2":

            set_state(phone, "beverages_menu")

            beverages = [
                "baobab_drink",
                "cream_soda",
                "freezits",
                "ice_cream",
                "juice_cascade",
                "low_cost_orange_drink",
                "low_cost_raspberry_drink",
                "orange_drink",
                "raspberry_drink",
                "universal_cordial"
            ]

            beverages.sort()
            
            fresh_user = get_user(phone)

            if fresh_user.get("package") == "basic":
                allowed = PACKAGES["basic"]["modules"]
                beverages = [m for m in beverages if m in allowed]

            elif fresh_user.get("package") == "custom":
                allowed = get_custom_modules(phone)
                beverages = [m for m in beverages if m in allowed]

            if not beverages:
                send_message(phone, "Hauna beverage lessons pa custom package yako.")
                return jsonify({"status": "ok"})

            menu = "🥤 *BEVERAGE LESSONS*\n\n"

            for i, module in enumerate(beverages, start=1):
                name = module.replace("_", " ").title()
                menu += f"{i}️⃣ {name}\n"

            menu += "\nReply with number"

            send_message(phone, menu)
            return jsonify({"status": "ok"})

        elif incoming == "3":
            set_state(phone, "advanced_menu")

            advanced = ADVANCED_MODULES

            fresh_user = get_user(phone)

            if fresh_user.get("package") == "advanced":
                allowed = ADVANCED_MODULES

            elif fresh_user.get("package") == "custom":
                allowed = get_custom_modules(phone)
                advanced = [m for m in ADVANCED_MODULES if m in allowed]

            else:
                send_message(
                    phone,
                    "🔒 Advanced Manufacturing is a separate package.\n\n"
                    "💵 Price: $20\n"
                    "Nyora PAY kuti ubhadhare."
                )
                return jsonify({"status":"ok"})

            menu = "🏭 *ADVANCED MANUFACTURING*\n\n"

            for i, module in enumerate(advanced, start=1):
                name = module.replace("_"," ").title()
                menu += f"{i}️⃣ {name}\n"

            menu += "\nReply with number"

            send_message(phone, menu)
            return jsonify({"status":"ok"})
            
        elif incoming == "4":
            set_state(phone, "spices_menu")
            send_message(phone, build_spices_menu(phone))
            return jsonify({"status": "ok"})

    elif user["state"] == "detergents_menu":

        if not incoming.isdigit():

            # 👉 allow AI questions inside lessons
            allowed_modules = get_user_modules(phone, incoming)

            ai_answer = ai_virtual_employee (phone, incoming)

            send_message(phone, ai_answer)

            ai_handled = True

            log_activity(phone, "ai_question", incoming)
            update_metrics(phone, "ai")

            return jsonify({"status": "ok"})

        index = int(incoming) - 1

        if index < 0 or index >= len(DETERGENT_MODULES):
            send_message(phone, "Invalid choice")
            return jsonify({"status": "ok"})

        fresh_user = get_user(phone)

        detergent_list = DETERGENT_MODULES

        if fresh_user.get("package") == "basic":
            allowed = PACKAGES["basic"]["modules"]
            detergent_list = [m for m in DETERGENT_MODULES if m in allowed]

        elif fresh_user.get("package") == "custom":
            allowed = get_custom_modules(phone)
            detergent_list = [m for m in DETERGENT_MODULES if m in allowed]

        index = int(incoming) - 1

        if index < 0 or index >= len(detergent_list):
            send_message(phone, "Invalid choice")
            return jsonify({"status": "ok"})

        module = detergent_list[index]

        modules = load_lessons()

        if module not in modules:
            send_message(phone, "Lesson not uploaded yet")
            return jsonify({"status": "ok"})

        pdf, label = modules[module]

        # 📘 Send lesson title
        send_message(
            phone,
             f"{label}\n\n📱 This lesson is now read inside the Arachis App.\n\nType *MENU* then choose *10 - Download App*.\n\n🤖 AI support is still available here."
        )

        # 🔊 FORCE AUDIO FIRST
        if not whatsapp_media_disabled_for(phone):
            send_message(phone, "🎧 Lesson audio (listen in order) 👇")

        send_audio_series(phone, module)

        # 📄 THEN SEND PDF
        send_pdf(
            phone,
            f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}",
            label
        )

        # 🤖 AI prompt
        send_message(
            phone,
            "Kana pane chausinganzwisise, bvunza pano 🤖\n\n"
            "➡️ Type *NEXT* to return to this lesson menu.\n"
            "🏠 Type *MENU* for main dashboard."
        )
        conn = get_db()
        c = conn.cursor()

        c.execute(
            "UPDATE users SET active_module=%s WHERE phone=%s",
            (module, phone)
        )

        conn.commit()
        release_db(conn)

        return jsonify({"status": "ok"})

    elif user["state"] == "beverages_menu":

        beverages = [
            "baobab_drink",
            "cream_soda",
            "freezits",
            "ice_cream",
            "juice_cascade",
            "low_cost_orange_drink",
            "low_cost_raspberry_drink",
            "orange_drink",
            "raspberry_drink",
            "universal_cordial"
        ]

        beverages.sort()
        
        fresh_user = get_user(phone)

        if fresh_user.get("package") == "basic":
            allowed = PACKAGES["basic"]["modules"]
            beverages = [m for m in beverages if m in allowed]

        elif fresh_user.get("package") == "custom":
            allowed = get_custom_modules(phone)
            beverages = [m for m in beverages if m in allowed]

        if not incoming.isdigit():

            # 👉 allow AI questions inside lessons
            allowed_modules = get_user_modules(phone, incoming)

            ai_answer = ai_virtual_employee(phone, incoming)

            send_message(phone, ai_answer)

            ai_handled = True

            log_activity(phone, "ai_question", incoming)
            update_metrics(phone, "ai")

            return jsonify({"status": "ok"})

        index = int(incoming) - 1

        if index < 0 or index >= len(beverages):
            send_message(phone, "Invalid choice")
            return jsonify({"status": "ok"})

        module = beverages[index]

        modules = load_lessons()

        if module not in modules:
            send_message(phone, "❌ Lesson PDF not found. Upload it in admin.")
            return jsonify({"status": "ok"})

        pdf, label = modules[module]

        # 📘 Send lesson title
        send_message(
            phone,
             f"{label}\n\n📱 This lesson is now read inside the Arachis App.\n\nType *MENU* then choose *10 - Download App*.\n\n🤖 AI support is still available here."
        )

        # 🔊 FORCE AUDIO FIRST
        if not whatsapp_media_disabled_for(phone):
            send_message(phone, "🎧 Lesson audio (listen in order) 👇")

        send_audio_series(phone, module)

        # 📄 THEN SEND PDF
        send_pdf(
            phone,
            f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}",
            label
        )

        # 🤖 AI prompt
        send_message(
            phone,
            "Kana pane chausinganzwisise, bvunza pano 🤖\n\n"
            "➡️ Type *NEXT* to return to this lesson menu.\n"
            "🏠 Type *MENU* for main dashboard."
        )

        conn = get_db()
        c = conn.cursor()

        c.execute(
            "UPDATE users SET active_module=%s WHERE phone=%s",
            (module, phone)
        )

        conn.commit()
        release_db(conn)
        
        return jsonify({"status": "ok"})

    elif user["state"] == "advanced_menu":

        allowed_modules = get_allowed_modules_for_user(phone)
        advanced = [m for m in ADVANCED_MODULES if m in allowed_modules]

        if not advanced:
            send_message(
                phone,
                "🔒 Advanced Manufacturing is locked.\n\n"
                "Nyora *UPGRADE* kuti uvhure."
            )
            return jsonify({"status": "ok"})

        if not incoming.isdigit():
            allowed_modules = get_user_modules(phone, incoming)
            ai_answer = ai_virtual_employee(phone, incoming)
            send_message(phone, ai_answer)
            log_activity(phone, "ai_question", incoming)
            update_metrics(phone, "ai")
            return jsonify({"status": "ok"})

        index = int(incoming) - 1

        if index < 0 or index >= len(advanced):
            send_message(phone, "Invalid choice")
            return jsonify({"status": "ok"})

        module = advanced[index]

        modules = load_lessons()

        if module not in modules:
            send_message(phone, "❌ Lesson PDF not found. Upload it in admin.")
            return jsonify({"status": "ok"})

        pdf, label = modules[module]

        record_module_access(phone, module)
        update_metrics(phone, "module")
        log_activity(phone, "open_module", module)

        send_message(
            phone,
            f"{label}\n\n📱 This lesson is now read inside the Arachis App.\n\nType *MENU* then choose *10 - Download App*.\n\n🤖 AI support is still available here."
        )
        
        if not whatsapp_media_disabled_for(phone):
            send_message(phone, "🎧 Lesson audio (listen in order) 👇")
        send_audio_series(phone, module)

        send_pdf(
            phone,
            f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}",
            label
        )

        send_message(
            phone,
            "Kana pane chausinganzwisise, bvunza pano 🤖\n\n"
            "➡️ Type *NEXT* to return to this lesson menu.\n"
            "🏠 Type *MENU* for main dashboard."
        )

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET active_module=%s WHERE phone=%s",
            (module, phone)
        )
        conn.commit()
        release_db(conn)

        return jsonify({"status": "ok"})

    elif user["state"] == "spices_menu":

        allowed_modules = get_allowed_modules_for_user(phone)
        spices = [m for m in SPICE_MODULES if m in allowed_modules]

        if not spices:
            send_message(
                phone,
                "🔒 Spices & Seasonings is locked.\n\n"
                "Nyora *UPGRADE* kuti uvhure."
            )
            return jsonify({"status": "ok"})

        if not incoming.isdigit():
            allowed_modules = get_user_modules(phone, incoming)
            ai_answer = ai_virtual_employee(phone, incoming)
            send_message(phone, ai_answer)
            log_activity(phone, "ai_question", incoming)
            update_metrics(phone, "ai")
            return jsonify({"status": "ok"})

        index = int(incoming) - 1

        if index < 0 or index >= len(spices):
            send_message(phone, "Invalid choice")
            return jsonify({"status": "ok"})

        module = spices[index]
        open_lesson_direct(phone, module)

        return jsonify({"status": "ok"})

    # =====================================================
    # PAYMENT HELPER
    # =====================================================

    def send_payment_instructions(phone, title, amount):

        send_message(
            phone,
            f"📲 *{title}*\n\n"

            "Pay using EcoCash:\n\n"

            f"*153*1*1*0773208904*{amount}#\n\n"

            "👤 Recipient: Beloved Nkomo\n"
            f"💵 Amount: ${amount} + EcoCash charges\n\n"

            "📩 After payment, simply forward the EcoCash confirmation SMS here.\n\n"

            "Type MENU anytime to cancel."
        )


    # =====================================================
    # UPGRADE COMMAND
    # =====================================================

    if incoming.lower() == "upgrade":

        user = get_user(phone)

        package = (user.get("package") or "").lower()

        if package == "basic":

            set_state(phone, "upgrade_select")

            send_message(
                phone,
                "🚀 *UPGRADE YOUR TRAINING*\n\n"

                "Current Package:\n"
                "🎓 Basic\n\n"

                "Available Upgrades:\n\n"

                "1️⃣ Premium Package (+$5)\n"
                "   ✔ More lessons\n"
                "   ✔ AI Support\n\n"

                "2️⃣ Add Spices Course (+$5)\n"
                "   ✔ Complete Spices Training\n\n"

                "3️⃣ Upgrade to Advanced (+$10)\n"
                "   ✔ Industrial Manufacturing\n\n"

                "Reply with 1, 2 or 3."
            )

            return jsonify({"status":"ok"})


        elif package == "premium":

            set_state(phone, "upgrade_select")

            send_message(
                phone,
                "🚀 *UPGRADE YOUR TRAINING*\n\n"

                "Current Package:\n"
                "🏆 Premium\n\n"

                "Available Upgrades:\n\n"

                "1️⃣ Add Spices Course (+$5)\n\n"

                "2️⃣ Upgrade to Advanced (+$7)\n\n"

                "Reply with 1 or 2."
            )

            return jsonify({"status":"ok"})


        else:

            send_message(
                phone,
                "✅ Your current package does not have any available upgrades."
            )

            return jsonify({"status":"ok"})


    # =====================================================
    # UPGRADE SELECTION
    # =====================================================

    elif user["state"] == "upgrade_select":

        if incoming.upper() in ["MENU", "BACK", "HOME"]:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone), phone))
            )

            return jsonify({"status":"ok"})


        package = (user.get("package") or "").lower()

        pending = None
        amount = 0
        title = ""


        # ------------------------------------------
        # BASIC
        # ------------------------------------------

        if package == "basic":

            if incoming == "1":

                pending = "upgrade_basic_to_premium"
                amount = 5
                title = "BASIC ➜ PREMIUM"

            elif incoming == "2":

                pending = "upgrade_basic_to_spices"
                amount = 5
                title = "ADD SPICES COURSE"

            elif incoming == "3":

                pending = "upgrade_basic_to_advanced"
                amount = 10
                title = "BASIC ➜ ADVANCED"

            else:

                send_message(
                    phone,
                    "Please choose 1, 2 or 3."
                )

                return jsonify({"status":"ok"})


        # ------------------------------------------
        # PREMIUM
        # ------------------------------------------

        elif package == "premium":

            if incoming == "1":

                pending = "upgrade_premium_to_spices"
                amount = 5
                title = "ADD SPICES COURSE"

            elif incoming == "2":

                pending = "upgrade_premium_to_advanced"
                amount = 7
                title = "PREMIUM ➜ ADVANCED"

            else:

                send_message(
                    phone,
                    "Please choose 1 or 2."
                )

                return jsonify({"status":"ok"})


        else:

            send_message(
                phone,
                "Upgrade not available."
            )

            return jsonify({"status":"ok"})


        # ------------------------------------------
        # Save Pending Purchase
        # ------------------------------------------

        conn = get_db()

        c = conn.cursor()

        c.execute(
            """
            UPDATE users
            SET pending_purchase=%s
            WHERE phone=%s
            """,
            (pending, phone)
        )

        conn.commit()

        release_db(conn)


        set_state(phone, "awaiting_payment")


        send_payment_instructions(

            phone,

            title,

            amount

        )

        return jsonify({"status":"ok"})
    # =====================================================
    # PAYMENT MENU
    # =====================================================

    elif user["state"] == "pay_menu":

        if incoming.upper() in ["MENU", "BACK", "HOME"]:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone), phone))
            )

            return jsonify({"status":"ok"})


        # ==========================================
        # BASIC PACKAGE
        # ==========================================

        if incoming == "1":

            conn = get_db()
            c = conn.cursor()

            c.execute("""
                UPDATE users
                SET pending_purchase='basic'
                WHERE phone=%s
            """, (phone,))

            conn.commit()
            release_db(conn)

            set_state(phone, "awaiting_payment")

            send_payment_instructions(
                phone,
                "BASIC TRAINING PACKAGE",
                BASIC_PRICE
            )

            return jsonify({"status":"ok"})


        # ==========================================
        # PREMIUM PACKAGE
        # ==========================================

        elif incoming == "2":

            conn = get_db()
            c = conn.cursor()

            c.execute("""
                UPDATE users
                SET pending_purchase='premium'
                WHERE phone=%s
            """, (phone,))

            conn.commit()
            release_db(conn)

            set_state(phone, "awaiting_payment")

            send_payment_instructions(
                phone,
                "PREMIUM TRAINING PACKAGE",
                PREMIUM_PRICE
            )

            return jsonify({"status":"ok"})


        # ==========================================
        # CUSTOM PACKAGE
        # ==========================================

        elif incoming == "3":

            clear_custom_modules(phone)

            set_state(phone, "custom_selecting")

            all_modules = (
                DETERGENT_MODULES +
                BEVERAGE_MODULES +
                SPICES_MODULES
            )

            menu = (
                "🧩 *CUSTOM TRAINING PACKAGE*\n\n"
                f"Price: ${CUSTOM_PRICE_PER_MODULE} per formula.\n\n"
                "Choose the formulas you want.\n\n"
            )

            for i, module in enumerate(all_modules, start=1):

                menu += f"{i}. {module.replace('_',' ').title()}\n"

            menu += (
                "\nReply with numbers separated by commas.\n"
                "Example:\n"
                "1,4,9\n\n"
                "Type *DONE* when finished."
            )

            send_message(phone, menu)

            return jsonify({"status":"ok"})


        # ==========================================
        # ADVANCED PACKAGE
        # ==========================================

        elif incoming == "4":

            conn = get_db()
            c = conn.cursor()

            c.execute("""
                UPDATE users
                SET pending_purchase='advanced_full'
                WHERE phone=%s
            """, (phone,))

            conn.commit()
            release_db(conn)

            set_state(phone, "awaiting_payment")

            send_payment_instructions(
                phone,
                "ADVANCED MANUFACTURING PACKAGE",
                ADVANCED_PRICE
            )

            return jsonify({"status":"ok"})


        # ==========================================
        # SPICES PACKAGE
        # ==========================================

        elif incoming == "5":

            conn = get_db()
            c = conn.cursor()

            c.execute("""
                UPDATE users
                SET pending_purchase='spices_full'
                WHERE phone=%s
            """, (phone,))

            conn.commit()
            release_db(conn)

            set_state(phone, "awaiting_payment")

            send_payment_instructions(
                phone,
                "SPICES & SEASONINGS PACKAGE",
                SPICES_PRICE
            )

            return jsonify({"status":"ok"})


        # ==========================================
        # INVALID OPTION
        # ==========================================

        else:

            send_message(
                phone,
                "Please choose:\n\n"
                "1️⃣ Basic\n"
                "2️⃣ Premium\n"
                "3️⃣ Custom\n"
                "4️⃣ Advanced\n"
                "5️⃣ Spices"
            )

            return jsonify({"status":"ok"})

    # =====================================================
    # CUSTOM PACKAGE SELECTION
    # =====================================================

    elif user["state"] == "custom_selecting":

        if incoming.upper() in ["MENU", "BACK", "HOME"]:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone), phone))
            )

            return jsonify({"status":"ok"})


        all_modules = (
            DETERGENT_MODULES +
            BEVERAGE_MODULES +
            SPICES_MODULES
        )


        # ==========================================
        # FINISH SELECTION
        # ==========================================

        if incoming.lower() == "done":

            selected = get_custom_modules(phone)

            if not selected:

                send_message(
                    phone,
                    "❌ You haven't selected any formulas yet.\n\n"
                    "Reply with numbers like:\n"
                    "1,3,7"
                )

                return jsonify({"status":"ok"})


            total = len(selected) * CUSTOM_PRICE_PER_MODULE


            conn = get_db()

            c = conn.cursor()

            c.execute("""
                UPDATE users
                SET pending_purchase='custom'
                WHERE phone=%s
            """, (phone,))

            conn.commit()

            release_db(conn)


            set_state(phone, "awaiting_payment")


            selected_names = "\n".join(

                f"✔ {m.replace('_',' ').title()}"

                for m in selected

            )


        send_message(

            phone,

            f"""🧩 *CUSTOM PACKAGE SUMMARY*

    {selected_names}

    ━━━━━━━━━━━━━━━━━━

    📚 Total Formulae: {len(selected)}

    💵 Total: ${total:.2f}

    ━━━━━━━━━━━━━━━━━━

    Now complete payment.

    After paying,
    forward the EcoCash confirmation SMS here."""
            )


        send_payment_instructions(

            phone,

            "CUSTOM TRAINING PACKAGE",

                total

        )

        return jsonify({"status":"ok"})


        # ==========================================
        # ADD MORE MODULES
        # ==========================================

        try:

            numbers = incoming.replace(" ", "").split(",")

            added = []

            already = []

            for n in numbers:

                if not n.isdigit():
                    continue

                index = int(n) - 1

                if index < 0 or index >= len(all_modules):
                    continue

                module = all_modules[index]

                current = get_custom_modules(phone)

                if module in current:

                    already.append(module)

                    continue

                add_custom_module(phone, module)

                added.append(module)


            if not added and not already:

                send_message(
                    phone,
                    "❌ Invalid selection.\n\n"
                    "Example:\n"
                    "1,3,7"
                )

                return jsonify({"status":"ok"})


            selected = get_custom_modules(phone)

            total = len(selected) * CUSTOM_PRICE_PER_MODULE


            reply = "✅ *CUSTOM PACKAGE UPDATED*\n\n"


            if added:

                reply += "Added:\n"

                for module in added:

                    reply += f"✔ {module.replace('_',' ').title()}\n"


            if already:

                reply += "\nAlready Selected:\n"

                for module in already:

                    reply += f"• {module.replace('_',' ').title()}\n"


            reply += (

                f"\n━━━━━━━━━━━━━━━━━━"

                f"\n📚 Total Formulae: {len(selected)}"

                f"\n💵 Current Total: ${total:.2f}"

                "\n\nReply with more numbers"

                "\nor type *DONE*."

            )


            send_message(phone, reply)

            return jsonify({"status":"ok"})


        except Exception as e:

            print("CUSTOM PACKAGE ERROR:", e)

            send_message(
                phone,
                "❌ Invalid format.\n\n"
                "Example:\n"
                "1,3,7"
            )

            return jsonify({"status":"ok"})

    # =====================================================
    # AWAITING PAYMENT
    # =====================================================

    elif user["state"] == "awaiting_payment":

        if incoming.upper() in ["MENU", "BACK", "HOME"]:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone), phone))
            )

            return jsonify({"status":"ok"})


        # ------------------------------------------
        # Wait for EcoCash confirmation
        # ------------------------------------------

        if "ecocash" not in incoming.lower() and "confirmed" not in incoming.lower():

            send_message(
                phone,
                "📩 Please forward your EcoCash confirmation SMS here.\n\n"
                "Our system (or an administrator) will verify your payment and activate your package."
            )

            return jsonify({"status":"ok"})


        conn = get_db()
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET payment_status='pending'
            WHERE phone=%s
        """, (phone,))

        conn.commit()

        release_db(conn)


        set_state(phone, "payment_pending")


        send_message(
            phone,
            "✅ *PAYMENT RECEIVED*\n\n"
            "Thank you.\n\n"
            "Your payment has been submitted for verification.\n\n"
            "Once approved:\n"
            "✔ Your package will be activated.\n"
            "✔ Your lessons will unlock automatically.\n"
            "✔ You'll receive a confirmation message."
        )

        notify_admin_payment(phone, incoming)

        return jsonify({"status":"ok"})

    elif user["state"] == "marketplace_home":

        if incoming in ["cart", "my cart", "basket"]:
            set_state(phone, "marketplace_cart")
            send_message(phone, build_cart_message(phone))
            return jsonify({"status": "ok"})

        if incoming in MARKETPLACE_CATEGORIES:
            category = MARKETPLACE_CATEGORIES[incoming]
            products = get_products_by_category(category)

            set_state(phone, "marketplace_results")
            send_message(phone, build_product_list_message(phone, products, category))
            return jsonify({"status": "ok"})

        elif incoming in ["search", "find"]:
            set_state(phone, "marketplace_search")
            send_message(
                phone,
                "🔎 *MARKETPLACE SEARCH*\n\n"
                "Type the product you are looking for.\n\n"
                "Example:\n"
                "SLES\n"
                "bottles\n"
                "labels\n"
                "spice\n"
                "mixing bucket"
            )
            return jsonify({"status": "ok"})

        elif incoming in ["sell", "upload", "post product", "sell product"]:
            set_state(phone, "marketplace_sell_category")

            send_message(
                phone,
                "📤 *SELL YOUR PRODUCT ON ARACHIS MARKETPLACE*\n\n"
                "Choose product category:\n\n"
                "1️⃣ Beverages\n"
                "2️⃣ Detergents\n"
                "3️⃣ Spices\n"
                "4️⃣ Advanced Products\n"
                "5️⃣ Packaging\n"
                "6️⃣ Machinery and Tools\n"
                "7️⃣ Branding and Labels\n\n"
                "Reply with category number."
            )
            return jsonify({"status": "ok"})

        elif incoming.startswith("p") and incoming[1:].isdigit():

            temp = get_marketplace_temp(phone)

            if not temp.startswith("featured:"):
                send_message(phone, "Product list expired. Type *MARKET* to refresh.")
                return jsonify({"status": "ok"})

            ids = temp.replace("featured:", "").split(",")
            index = int(incoming[1:]) - 1

            if index < 0 or index >= len(ids):
                send_message(phone, "Invalid featured product.")
                return jsonify({"status": "ok"})

            set_state(phone, "marketplace_product")
            send_marketplace_product_details(phone, int(ids[index]))
            return jsonify({"status": "ok"})

        else:
            send_message(phone, build_marketplace_home(phone))
            return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_search":

        products = search_marketplace_products(incoming)

        set_state(phone, "marketplace_results")

        send_message(
            phone,
            build_product_list_message(phone, products, f"Search Results for: {incoming}")
        )

        return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_results":

        if incoming in ["cart", "my cart", "basket"]:
            set_state(phone, "marketplace_cart")
            send_message(phone, build_cart_message(phone))
            return jsonify({"status": "ok"})

        if incoming in ["search", "find"]:
            set_state(phone, "marketplace_search")
            send_message(phone, "🔎 Type the product you are looking for.")
            return jsonify({"status": "ok"})

        if incoming in ["market", "marketplace", "back"]:
            set_state(phone, "marketplace_home")
            send_message(phone, build_marketplace_home(phone))
            return jsonify({"status": "ok"})

        if not incoming.isdigit():
            send_message(phone, "Reply with product number, or type *MARKET* to go back.")
            return jsonify({"status": "ok"})

        temp = get_marketplace_temp(phone)

        if not temp.startswith("results:"):
            send_message(phone, "Product list expired. Type *MARKET* to refresh.")
            return jsonify({"status": "ok"})

        ids = temp.replace("results:", "").split(",")
        index = int(incoming) - 1

        if index < 0 or index >= len(ids):
            send_message(phone, "Invalid product number.")
            return jsonify({"status": "ok"})

        product_id = int(ids[index])

        set_state(phone, "marketplace_product")
        send_marketplace_product_details(phone, product_id)

        return jsonify({"status": "ok"})

    elif user["state"] == "marketplace_product":

        temp = get_marketplace_temp(phone)

        if incoming in ["market", "marketplace", "back"]:
            set_state(phone, "marketplace_home")
            send_message(phone, build_marketplace_home(phone))
            return jsonify({"status": "ok"})

        if incoming in ["cart", "my cart", "basket"]:
            set_state(phone, "marketplace_cart")
            send_message(phone, build_cart_message(phone))
            return jsonify({"status": "ok"})

        if incoming in ["add", "add to cart"]:

            if not temp.startswith("selected_product:"):
                send_message(phone, "Product not selected. Type *MARKET*.")
                return jsonify({"status": "ok"})

            product_id = int(temp.replace("selected_product:", ""))
            product = get_marketplace_product(product_id)

            if not product:
                send_message(phone, "❌ Product not found.")
                return jsonify({"status": "ok"})

            (
                pid, category, name, description, price, unit,
                seller_name, seller_phone, seller_location,
                image_url, image_media_id, status
            ) = product

            save_marketplace_temp(phone, f"add_quantity:{pid}")

            set_state(phone, "marketplace_quantity")

            send_message(
                phone,
                f"🔢 *QUANTITY REQUIRED*\n\n"
                f"Product: *{name}*\n"
                f"Price: {price} {unit}\n\n"
                "How many do you want to add to cart?\n\n"
                "Example:\n"
                "1\n"
                "5\n"
                "10\n"
                "25\n\n"
                "Reply with quantity number."
            )

            return jsonify({"status": "ok"})

        send_message(
            phone,
            "Reply *ADD* to choose quantity and add this product to cart, *CART* to view cart, or *MARKET* to continue shopping."
        )
        return jsonify({"status": "ok"})

    elif user["state"] == "marketplace_quantity":

        temp = get_marketplace_temp(phone)

        if incoming in ["market", "marketplace", "back"]:
            set_state(phone, "marketplace_home")
            send_message(phone, build_marketplace_home(phone))
            return jsonify({"status": "ok"})

        if incoming in ["cart", "my cart", "basket"]:
            set_state(phone, "marketplace_cart")
            send_message(phone, build_cart_message(phone))
            return jsonify({"status": "ok"})

        if not temp.startswith("add_quantity:"):
            set_state(phone, "marketplace_home")
            send_message(phone, "Product selection expired. Type *MARKET* to start again.")
            return jsonify({"status": "ok"})

        if not incoming.isdigit():
            send_message(
                phone,
                "Please enter quantity as a number.\n\n"
                "Example:\n"
                "10"
            )
            return jsonify({"status": "ok"})

        qty = int(incoming)

        if qty <= 0:
            send_message(phone, "Quantity must be 1 or more.")
            return jsonify({"status": "ok"})

        if qty > 1000:
            send_message(phone, "Quantity is too high. Please enter a smaller quantity.")
            return jsonify({"status": "ok"})

        product_id = int(temp.replace("add_quantity:", ""))
        product = get_marketplace_product(product_id)

        if not product:
            set_state(phone, "marketplace_home")
            send_message(phone, "❌ Product not found. Type *MARKET* to continue.")
            return jsonify({"status": "ok"})

        (
            pid, category, name, description, price, unit,
            seller_name, seller_phone, seller_location,
            image_url, image_media_id, status
        ) = product

        add_product_to_cart(phone, pid, qty)

        set_state(phone, "marketplace_cart")

        send_message(
            phone,
            f"✅ *ADDED TO CART*\n\n"
            f"Product: {name}\n"
            f"Quantity: {qty}\n"
            f"Price: {price} {unit}\n\n"
            + build_cart_message(phone)
        )

        return jsonify({"status": "ok"})

    elif user["state"] == "marketplace_cart":

        if incoming in ["market", "marketplace", "shop", "back"]:
            set_state(phone, "marketplace_home")
            send_message(phone, build_marketplace_home(phone))
            return jsonify({"status": "ok"})

        if incoming in ["cart", "my cart", "basket"]:
            send_message(phone, build_cart_message(phone))
            return jsonify({"status": "ok"})

        if incoming == "clear":
            clear_marketplace_cart(phone)
            send_message(
                phone,
                "🗑 Cart cleared.\n\nType *MARKET* to continue shopping."
            )
            return jsonify({"status": "ok"})

        if incoming.startswith("remove "):
            parts = incoming.split()

            if len(parts) < 2 or not parts[1].isdigit():
                send_message(phone, "Use: *REMOVE 1*")
                return jsonify({"status": "ok"})

            remove_index = int(parts[1]) - 1

            cart = get_marketplace_cart(phone)
            product_ids = list(cart.keys())

            if remove_index < 0 or remove_index >= len(product_ids):
                send_message(phone, "Invalid cart item number.")
                return jsonify({"status": "ok"})

            product_id = product_ids[remove_index]
            remove_product_from_cart(phone, product_id)

            send_message(
                phone,
                "✅ Item removed.\n\n" + build_cart_message(phone)
            )

            return jsonify({"status": "ok"})

        if incoming in ["checkout", "place order", "order"]:

            cart = get_marketplace_cart(phone)

            if not cart:
                send_message(phone, build_cart_message(phone))
                return jsonify({"status": "ok"})

            set_state(phone, "marketplace_checkout_location")

            send_message(
                phone,
                "📍 *DELIVERY / PICKUP LOCATION*\n\n"
                "Please enter your town or pickup location.\n\n"
                "Example:\n"
                "Harare CBD\n"
                "Gweru\n"
                "Bulawayo\n"
                "Mataga\n\n"
                "If you will collect from seller, type *COLLECT*."
            )

            return jsonify({"status": "ok"})

        send_message(
            phone,
            "Reply *CHECKOUT* to place order, *REMOVE 1* to remove item, *CLEAR* to empty cart, or *MARKET* to continue shopping."
        )
        return jsonify({"status": "ok"})

    elif user["state"] == "marketplace_checkout_location":

        delivery_location = incoming.title()

        order_data = build_order_data_from_cart(
            phone=phone,
            delivery=delivery_location,
            note="Order created inside WhatsApp marketplace cart."
        )

        if not order_data.get("items"):
            set_state(phone, "marketplace_home")
            send_message(
                phone,
                "❌ Your cart is empty.\n\nType *MARKET* to continue shopping."
            )
            return jsonify({"status": "ok"})

        ok = send_marketplace_order_to_admin_and_sellers(order_data, phone)

        if ok:
            clear_marketplace_cart(phone)
            set_state(phone, "main")

            send_message(
                phone,
                "✅ *ORDER RECEIVED*\n\n"
                "Your marketplace order has been sent to:\n"
                "✔ Admin\n"
                "✔ Seller(s)\n\n"
                f"📍 Location: {delivery_location}\n\n"
                "The seller will contact you directly to confirm stock, payment and delivery.\n\n"
                "⚠️ Do not pay before confirming stock and seller details."
            )

            send_message(phone, main_menu())
            return jsonify({"status": "ok"})

        send_message(
            phone,
            "❌ Failed to process your order. Please try again."
        )
        return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_sell_category":

        if incoming not in MARKETPLACE_CATEGORIES:
            send_message(phone, "Choose category number from 1 to 7.")
            return jsonify({"status": "ok"})

        category = MARKETPLACE_CATEGORIES[incoming]
        save_marketplace_temp(phone, f"sell|category={category}")

        set_state(phone, "marketplace_sell_name")

        send_message(
            phone,
            f"📂 Category selected: *{category}*\n\n"
            "Enter product name.\n\n"
            "Example:\n"
            "SLES\n"
            "Empty 750ml Bottles\n"
            "Chicken Spice Ingredients\n"
            "Label Printing Service"
        )

        return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_sell_name":

        temp = get_marketplace_temp(phone)
        temp += f"|name={incoming.title()}"
        save_marketplace_temp(phone, temp)

        set_state(phone, "marketplace_sell_description")

        send_message(
            phone,
            "📝 Enter short product description.\n\n"
            "Example:\n"
            "Good quality SLES for dishwash, foam bath and shampoo."
        )

        return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_sell_description":

        temp = get_marketplace_temp(phone)
        temp += f"|description={incoming}"
        save_marketplace_temp(phone, temp)

        set_state(phone, "marketplace_sell_price")

        send_message(
            phone,
            "💵 Enter price.\n\n"
            "Example:\n"
            "$3.50\n"
            "$1 per 30ml\n"
            "Contact seller"
        )

        return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_sell_price":

        temp = get_marketplace_temp(phone)
        temp += f"|price={incoming}"
        save_marketplace_temp(phone, temp)

        set_state(phone, "marketplace_sell_unit")

        send_message(
            phone,
            "📏 Enter unit or size.\n\n"
            "Example:\n"
            "per kg\n"
            "per litre\n"
            "each\n"
            "per 100 labels\n"
            "Leave blank by typing *NONE* if not applicable."
        )

        return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_sell_unit":

        unit = "" if incoming == "none" else incoming

        temp = get_marketplace_temp(phone)
        temp += f"|unit={unit}"
        save_marketplace_temp(phone, temp)

        set_state(phone, "marketplace_sell_seller_name")

        send_message(
            phone,
            "🏭 Enter seller or business name.\n\n"
            "Example:\n"
            "Tariro Chemicals\n"
            "Arachis Student Supplier\n"
            "Kuda Packaging"
        )

        return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_sell_seller_name":

        temp = get_marketplace_temp(phone)
        temp += f"|seller_name={incoming.title()}"
        save_marketplace_temp(phone, temp)

        set_state(phone, "marketplace_sell_location")

        send_message(
            phone,
            "📍 Enter seller location.\n\n"
            "Example:\n"
            "Harare CBD\n"
            "Gweru\n"
            "Bulawayo\n"
            "Online"
        )

        return jsonify({"status": "ok"})


    elif user["state"] == "marketplace_sell_location":

        temp = get_marketplace_temp(phone)
        temp += f"|seller_location={incoming.title()}"
        save_marketplace_temp(phone, temp)

        set_state(phone, "marketplace_sell_photo")

        send_message(
            phone,
            "🖼 *PRODUCT PICTURE*\n\n"
            "Upload a clear product picture if you have one.\n\n"
            "Or type *SKIP* if you do not want to add a picture now.\n\n"
            "⚠️ Product will be reviewed by Admin before appearing in the marketplace."
        )

        return jsonify({"status": "ok"})

    elif user["state"] == "marketplace_after_upload":

        if incoming in ["1", "add", "add another", "another", "next", "next product"]:
            set_state(phone, "marketplace_sell_category")

            send_message(
                phone,
                "📤 *ADD ANOTHER PRODUCT*\n\n"
                "Choose product category:\n\n"
                "1️⃣ Beverages\n"
                "2️⃣ Detergents\n"
                "3️⃣ Spices\n"
                "4️⃣ Advanced Products\n"
                "5️⃣ Packaging\n"
                "6️⃣ Machinery and Tools\n"
                "7️⃣ Branding and Labels\n\n"
                "Reply with category number."
            )

            return jsonify({"status": "ok"})

        elif incoming in ["2", "menu", "main", "done", "finish"]:
            set_state(phone, "main")
            send_main_menu_with_marketplace_placeholder(phone)
            return jsonify({"status": "ok"})

        else:
            send_message(
                phone,
                "Reply:\n"
                "1️⃣ Add another product\n"
                "2️⃣ Go to main menu"
            )
            return jsonify({"status": "ok"})

    elif user["state"] == "business_lessons":

        modules = list(BUSINESS_MODULES.keys())

        if not incoming.isdigit():

            ai_answer = ai_virtual_employee(
                phone,
                incoming
            )

            send_message(phone, ai_answer)

            ai_handled = True

            log_activity(phone, "ai_question", incoming)
            update_metrics(phone, "ai")
            log_activity(phone, "ai_answer", ai_answer[:500])

            return jsonify({"status": "ok"})

        if 1 <= int(incoming) <= len(modules):

            module = modules[int(incoming)-1]
            pdf, label = BUSINESS_MODULES[module]

            record_module_access(phone, module)
            update_metrics(phone, "module")

            send_message(
                phone,
                f"{label}\n\n📱 This lesson is now read inside the Arachis App.\n\nType *MENU* then choose *10 - Download App*.\n\n🤖 AI support is still available here."
            )

            send_audio_series(phone, module)

            send_pdf(
                phone,
                f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}", 
                label
            )

            send_message(phone, "Bvunza chero mubvunzo 🤖")

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE users SET active_module=%s WHERE phone=%s",
                (module, phone)
            )
            conn.commit()
            release_db(conn)

            return jsonify({"status": "ok"})

        else:
            send_message(phone, "Invalid choice")
            return jsonify({"status": "ok"})

    elif user["state"] == "photo_details":

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT item FROM temp_orders WHERE phone=%s", (phone,))
        row = c.fetchone()

        release_db(conn)

        if not row:
            send_message(phone, "❌ Image not found. Send photo again.")
            return jsonify({"status": "ok"})

        image_path = row[0]

        send_message(phone, "🔍 Ndiri kuongorora product yako...")

        student_details = incoming
        
        ai_result = ai_analyze_product(image_path, student_details)
        
        send_message(phone, ai_result)

        log_activity(phone, "ai_photo_analysis", incoming)

        set_state(phone, "ai_chat")

        return jsonify({"status": "ok"})

    elif user["state"] == "offline_intro":

        if incoming.lower() == "yes":

            set_state(phone, "offline_name")

            send_message(
                phone,
                "📝 *PRACTICAL TRAINING REGISTRATION*\n\n"

                "Thank you for choosing Arachis Practical Training.\n\n"

                "💵 Training Fee: *$20*\n"
                "💳 Deposit Required: *$5*\n"
                "💰 Balance: *$15* (pay on or before training day)\n\n"

                "✅ Your seat is only reserved after the $5 deposit has been confirmed.\n\n"

                "Let's begin.\n\n"

                "✍🏽 Please enter your *FULL NAME*."
            )

            return jsonify({"status":"ok"})

    elif user["state"] == "offline_name":

        conn = get_db()
        c = conn.cursor()

        c.execute("""
            INSERT INTO offline_registrations (phone, full_name)
            VALUES (%s, %s)
            ON CONFLICT (phone)
            DO UPDATE SET full_name = EXCLUDED.full_name
        """, (phone, incoming.title()))

        conn.commit()
        release_db(conn)

        set_state(phone, "offline_location")

        send_message(
            phone,
            "📍 Please enter your Town or Area."
        )

        return jsonify({"status":"ok"})

    elif user["state"] == "offline_location":

        conn = get_db()
        c = conn.cursor()

        c.execute("""
            UPDATE offline_registrations
            SET location=%s
            WHERE phone=%s
        """, (incoming.title(), phone))

        conn.commit()

        c.execute("""
            SELECT
                id,
                title,
                city,
                venue,
                event_date,
                fee,
                deposit
            FROM training_events
            WHERE status='Open'
            ORDER BY event_date
        """)

        events = c.fetchall()

        release_db(conn)

        if not events:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                "There are currently no open practical training events."
            )

            return jsonify({"status":"ok"})

        menu = "🎓 *SELECT YOUR TRAINING*\n\n"

        for i, event in enumerate(events, start=1):

            menu += (
                f"{i}. {event[1]}\n"
                f"📍 {event[2]}\n"
                f"📅 {event[4]}\n"
                f"💵 ${event[5]} | Deposit ${event[6]}\n\n"
            )

        menu += "Reply with the training number."

        set_state(phone, "offline_event")

        send_message(phone, menu)

        return jsonify({"status":"ok"})

    elif user["state"] == "offline_event":

        conn = get_db()
        c = conn.cursor()

        c.execute("""
            SELECT
                id,
                title
            FROM training_events
            WHERE status='Open'
            ORDER BY event_date
        """)

        events = c.fetchall()

        if not incoming.isdigit():

            release_db(conn)

            send_message(
                phone,
                "Reply with the training number."
            )

            return jsonify({"status":"ok"})

        choice = int(incoming)

        if choice < 1 or choice > len(events):

            release_db(conn)

            send_message(
                phone,
                "Invalid selection."
            )

            return jsonify({"status":"ok"})

        event = events[choice-1]

        c.execute("""
            UPDATE offline_registrations
            SET
                event_id=%s,
                event_title=%s
            WHERE phone=%s
        """, (
            event[0],
            event[1],
            phone
        ))

        conn.commit()
        release_db(conn)

        set_state(phone, "offline_choice")

        send_message(
            phone,
            "🧪 Choose your FREE 10L ingredient package:\n\n"
            "1️⃣ Dishwash\n"
            "2️⃣ Thick Bleach\n"
            "3️⃣ Foam Bath\n"
            "4️⃣ Pine Gel\n\n"
            "Reply with 1, 2, 3 or 4."
        )

        return jsonify({"status":"ok"})

    elif user["state"] == "offline_choice":

        choices = {
            "1": "Dishwash",
            "2": "Thick Bleach",
            "3": "Foam Bath",
            "4": "Pine Gel"
        }

        product = choices.get(incoming)

        if not product:

            send_message(
                phone,
                "Please reply with:\n\n"
                "1️⃣ Dishwash\n"
                "2️⃣ Thick Bleach\n"
                "3️⃣ Foam Bath\n"
                "4️⃣ Pine Gel"
            )

            return jsonify({"status":"ok"})

        conn = get_db()
        c = conn.cursor()

        # Get registration details
        c.execute("""
            SELECT
                event_id,
                event_title,
                full_name,
                location
            FROM offline_registrations
            WHERE phone=%s
        """, (phone,))

        row = c.fetchone()

        if not row:

            release_db(conn)

            send_message(
                phone,
                "Registration not found. Please start again."
            )

            set_state(phone, STATE_MAIN)

            return jsonify({"status":"ok"})

        event_id, event_title, full_name, location = row

        # Generate booking number
        booking_number = generate_booking_number(event_id)

        # Save registration
        c.execute("""
            UPDATE offline_registrations
            SET
                detergent_choice=%s,
                booking_number=%s,
                registration_status='Awaiting Deposit'
            WHERE phone=%s
        """, (
            product,
            booking_number,
            phone
        ))

        conn.commit()

        release_db(conn)

        set_state(phone, "awaiting_offline_deposit")

        # ===============================
        # STUDENT CONFIRMATION
        # ===============================

        send_message(
            phone,
            f"🎉 *REGISTRATION SUCCESSFUL!*\n\n"

            f"🎟 *Booking Number*\n"
            f"{booking_number}\n\n"

            f"👤 {full_name}\n"
            f"📍 {location}\n"
            f"🎓 {event_title}\n"
            f"🎁 FREE Product: {product}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"
            "💵 Training Fee: $20\n"
            "💳 Deposit Required: $5\n"
            "💰 Balance: $15\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "✅ Your seat will only be reserved once your $5 deposit has been approved.\n\n"

            "📲 *PAY YOUR DEPOSIT*\n\n"

            "*153*1*1*0773208904*5#\n\n"

            "👤 Recipient: Beloved Nkomo\n\n"

            "After payment, please forward your EcoCash confirmation SMS here."
        )

        # ===============================
        # ADMIN NOTIFICATION
        # ===============================

        send_message(
            ADMIN_NUMBERS[0],
            f"🆕 *NEW TRAINING REGISTRATION*\n\n"

            f"🎟 Booking: {booking_number}\n\n"

            f"👤 {full_name}\n"
            f"📞 {phone}\n"
            f"📍 {location}\n\n"

            f"🎓 {event_title}\n\n"

            f"🎁 FREE Product: {product}\n\n"

            "💳 Status: Awaiting $5 Deposit"
        )

        return jsonify({"status":"ok"})
    # ==========================================
    # AWAITING OFFLINE TRAINING DEPOSIT
    # ==========================================

    elif user["state"] == "awaiting_offline_deposit":

        if incoming.upper() in ["MENU", "BACK", "HOME"]:

            set_state(phone, STATE_MAIN)

            send_message(
                phone,
                main_menu(get_user(phone))
            )

            return jsonify({"status":"ok"})


        conn = get_db()
        c = conn.cursor()

        c.execute("""
            UPDATE offline_registrations
            SET
                payment_proof=%s,
                registration_status='Deposit Submitted'
            WHERE phone=%s
        """, (incoming, phone))

        conn.commit()

        c.execute("""
            SELECT
                booking_number,
                full_name,
                event_title
            FROM offline_registrations
            WHERE phone=%s
        """, (phone,))

        booking, name, event = c.fetchone()

        release_db(conn)

        # Notify Admin

        send_message(
            ADMIN_NUMBERS[0],
            f"💳 *DEPOSIT SUBMITTED*\n\n"

            f"🎟 {booking}\n\n"

            f"👤 {name}\n"

            f"📞 {phone}\n\n"

            f"🎓 {event}\n\n"

            f"Payment Proof:\n\n"

            f"{incoming}\n\n"

            f"Reply:\n"

            f"APPROVE {booking}\n\n"

            f"or\n\n"

            f"REJECT {booking}"
        )

        set_state(phone, STATE_MAIN)

        send_message(
            phone,
            "✅ Thank you.\n\n"

            "Your deposit has been submitted for verification.\n\n"

            "You'll receive confirmation once it has been approved."
        )

        return jsonify({"status":"ok"})

    elif user["state"] == "calc_menu":

        if incoming == "1":
            set_state(phone, "calc_detailed_units")

            # initialize temp storage
            conn = get_db()
            c = conn.cursor()
            c.execute("""
                INSERT INTO temp_orders (phone, item, quantity)
                VALUES (%s, %s, %s)
                ON CONFLICT (phone)
                DO UPDATE SET item = '', quantity = 0
            """, (phone, "", 0))
            conn.commit()
            release_db(conn)

            send_message(phone, "Enter total units produced/ Wagadzira zvingani (e.g. 40):")
            return jsonify({"status": "ok"})

        elif incoming == "2":
            set_state(phone, "calc_quick_raw")

            send_message(phone, "Enter total raw material cost/ Maingedients acho Wamatenga Marii:")
            return jsonify({"status": "ok"})

    elif user["state"] == "calc_detailed_units":

        units = float(incoming)

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE temp_orders SET quantity=%s WHERE phone=%s
        """, (units, phone))
        conn.commit()
        release_db(conn)

        set_state(phone, "calc_detailed_raw")

        send_message(phone, "Enter total raw material cost/ Maingredients Wamatenga Marii:")
        return jsonify({"status": "ok"})

    elif user["state"] == "calc_detailed_raw":

        raw_cost = float(incoming)

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE temp_orders SET item=%s WHERE phone=%s
        """, (str(raw_cost), phone))
        conn.commit()
        release_db(conn)

        set_state(phone, "calc_detailed_packaging")

        send_message(phone, "Enter packaging cost per unit/ Zvigubhu Zvekuisira Zvaita Mari Chimwe Chete:")
        return jsonify({"status": "ok"})

    elif user["state"] == "calc_detailed_packaging":

        packaging = float(incoming)

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT item, quantity FROM temp_orders WHERE phone=%s", (phone,))
        row = c.fetchone()

        raw_cost = float(row[0])
        units = float(row[1])

        packaging_total = packaging * units
        total_cost = raw_cost + packaging_total
        cost_per_unit = total_cost / units

        # store temp values
        c.execute("""
            UPDATE temp_orders SET item=%s WHERE phone=%s
        """, (f"{raw_cost}|{packaging}|{units}", phone))

        conn.commit()
        release_db(conn)

        set_state(phone, "calc_detailed_price")

        send_message(phone, "Enter selling price per unit/ Uchatengesa chigubhu Chimwe chete Marii:")
        return jsonify({"status": "ok"})

    elif user["state"] == "calc_detailed_price":

        selling_price = float(incoming)

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT item FROM temp_orders WHERE phone=%s", (phone,))
        row = c.fetchone()

        raw_cost, packaging, units = map(float, row[0].split("|"))

        packaging_total = packaging * units
        total_cost = raw_cost + packaging_total
        cost_per_unit = total_cost / units
        revenue = selling_price * units
        profit = revenue - total_cost
        profit_per_unit = selling_price - cost_per_unit

        release_db(conn)

        send_message(
            phone,
            f"📊 *PRODUCTION SUMMARY*\n\n"
            f"🧾 Raw Materials: ${raw_cost:.2f}\n"
            f"📦 Packaging: ${packaging_total:.2f}\n"
            f"💵 Total Cost: ${total_cost:.2f}\n\n"
            f"📦 Units: {units}\n"
            f"💲 Cost per Unit: ${cost_per_unit:.2f}\n\n"
            f"💰 Selling Price: ${selling_price:.2f}\n"
            f"📈 Revenue: ${revenue:.2f}\n\n"
            f"🔥 Profit: ${profit:.2f}\n"
            f"📊 Profit per Unit: ${profit_per_unit:.2f}"
        )

        set_state(phone, "main")
        return jsonify({"status": "ok"})

    elif user["state"] == "calc_quick_raw":

        raw_cost = float(incoming)

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO temp_orders (phone, item)
            VALUES (%s, %s)
            ON CONFLICT (phone)
            DO UPDATE SET item = %s
        """, (phone, str(raw_cost), str(raw_cost)))
        conn.commit()
        release_db(conn)

        set_state(phone, "calc_quick_units")

        send_message(phone, "Enter number of units/ Wapeka Zvigubhu Zvingani:")
        return jsonify({"status": "ok"})

    elif user["state"] == "calc_quick_units":

        units = float(incoming)

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE temp_orders SET quantity=%s WHERE phone=%s
        """, (units, phone))
        conn.commit()
        release_db(conn)

        set_state(phone, "calc_quick_packaging")

        send_message(phone, "Enter packaging cost per unit/ Chigubhu Chekuisira Chinoita Marii Chimwe Chete:")
        return jsonify({"status": "ok"})

    elif user["state"] == "calc_quick_packaging":

        packaging = float(incoming)

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT item, quantity FROM temp_orders WHERE phone=%s", (phone,))
        row = c.fetchone()

        raw_cost = float(row[0])
        units = float(row[1])

        c.execute("""
            UPDATE temp_orders SET item=%s WHERE phone=%s
        """, (f"{raw_cost}|{packaging}|{units}", phone))

        conn.commit()
        release_db(conn)

        set_state(phone, "calc_quick_price")

        send_message(phone, "Enter selling price per unit/ Uchatengesa Marii Chigubhu Chimwe Chete:")
        return jsonify({"status": "ok"})

    elif user["state"] == "calc_quick_price":

        selling_price = float(incoming)

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT item FROM temp_orders WHERE phone=%s", (phone,))
        row = c.fetchone()

        raw_cost, packaging, units = map(float, row[0].split("|"))

        packaging_total = packaging * units
        total_cost = raw_cost + packaging_total
        cost_per_unit = total_cost / units
        revenue = selling_price * units
        profit = revenue - total_cost
        profit_per_unit = selling_price - cost_per_unit

        release_db(conn)
        
        send_message(
            phone,
            f"📊 *QUICK RESULTS*\n\n"
            f"💵 Total Cost: ${total_cost:.2f}\n"
            f"💲 Cost per Unit: ${cost_per_unit:.2f}\n\n"
            f"📈 Revenue: ${revenue:.2f}\n\n"
            f"🔥 Profit: ${profit:.2f}\n"
            f"📊 Profit per Unit: ${profit_per_unit:.2f}"
        )

        set_state(phone, "main")
        return jsonify({"status": "ok"})
        
# =========================
# AUTO PAYMENT DETECTOR
# =========================
    if user["state"] == "awaiting_payment":

        success, reply = verify_and_apply_payment(phone, incoming)

        if success:
            set_state(phone, "main")
            send_message(phone, reply)
            send_message(phone, main_menu())
            return jsonify({"status": "ok"})
        else:
            send_message(phone, reply)
            return jsonify({"status": "ok"})
            
    if user["state"] == "awaiting_upgrade_payment":

        success, reply = verify_and_apply_payment(phone, incoming)

        if success:

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE users SET package='premium' WHERE phone=%s",
                (phone,)
            )
            conn.commit()
            release_db(conn)

            send_message(phone, "🎉 Upgrade successful! Wava pa Premium.")
            set_state(phone, "main")
            send_message(phone, main_menu())

            return jsonify({"status": "ok"})
        else:
            send_message(phone, reply)
            return jsonify({"status": "ok"})

    # =========================
    # PAID USER AI TRAINER
    # =========================

    if user["is_paid"] and not ai_handled:

    # -----------------------------------------
    # DAILY AI LIMIT
    # -----------------------------------------

        package = user.get("package", "basic")

        limit = 5

        if package == "premium":
            limit = 8

        elif package == "advanced":
            limit = 50

        elif package == "spices":
            limit = 5

        today_count = ai_questions_today(phone)

        if today_count >= limit:

            send_message(
                phone,
                f"⛔ Wapedza AI limit yako ye nhasi ({limit}).\n\n"
                "Unogona kuenderera mberi mangwana."
            )

            return jsonify({"status": "ok"})


    # -----------------------------------------
    # AI VIRTUAL EMPLOYEE
    # -----------------------------------------
    #
        # IMPORTANT:
        # Do NOT require the student to have opened
        # a module before asking the AI a question.
        #
        # The AI should be able to handle:
        # - manufacturing questions
        # - ingredient questions
        # - business questions
        # - supplier questions
        # - practical training questions
        # - costing/profit questions
        # - general Arachis questions
        # -----------------------------------------

        ai_answer = ai_virtual_employee(
            phone,
            incoming
        )


    # -----------------------------------------
    # LOG AI ACTIVITY
    # -----------------------------------------

        log_activity(
            phone,
            "ai_question",
            incoming
        )

        update_metrics(
            phone,
            "ai"
        )

        log_activity(
            phone,
            "ai_answer",
            ai_answer[:500]
        )


    # -----------------------------------------
    # SEND AI RESPONSE
    # -----------------------------------------

        send_message(
            phone,
            ai_answer
        )

        return jsonify({"status": "ok"})


# =========================
# FINAL WEBHOOK FALLBACK
# =========================

    return jsonify({"status": "ok"})

# =========================
# ADMIN WEB DASHBOARD
# =========================
@app.route("/admin", methods=["GET", "POST"])
@requires_auth
def admin_dashboard():

    if request.method == "POST":

        form_action = request.form.get("form_action", "").strip()

        # =========================
        # ADMIN ADD MARKETPLACE PRODUCT
        # =========================
        if form_action == "add_marketplace_product":

            category = request.form.get("category", "").strip()
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            price = request.form.get("price", "").strip()
            unit = request.form.get("unit", "").strip()
            seller_name = request.form.get("seller_name", "").strip()
            seller_phone = request.form.get("seller_phone", "").strip()
            seller_location = request.form.get("seller_location", "").strip()
            image_url = request.form.get("image_url", "").strip()

            image_file = request.files.get("marketplace_image")

            if not category or not name:
                return "Category and product name are required. Go back and complete the form."

            if not price:
                price = "Contact seller"

            if not seller_name:
                seller_name = "Arachis Marketplace"

            if not seller_phone:
                seller_phone = ADMIN_NUMBERS[0]

            seller_phone = normalize_phone(seller_phone)

            if not seller_location:
                seller_location = "Zimbabwe"

            # Optional image upload
            if image_file and image_file.filename and allowed_image_file(image_file.filename):
                os.makedirs(app.config["MARKETPLACE_FOLDER"], exist_ok=True)

                filename = secure_filename(image_file.filename)
                filename = f"marketplace_{int(time.time())}_{filename}"

                filepath = os.path.join(app.config["MARKETPLACE_FOLDER"], filename)
                image_file.save(filepath)

                base_url = request.host_url.rstrip("/")
                image_url = f"{base_url}/static/marketplace/{filename}"

            conn = get_db()
            c = conn.cursor()

            c.execute("""
                INSERT INTO marketplace_products (
                    category, name, description, price, unit,
                    seller_name, seller_phone, seller_location,
                    image_url, image_media_id, status, created_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,'active','admin_dashboard')
            """, (
                category,
                name,
                description,
                price,
                unit,
                seller_name,
                seller_phone,
                seller_location,
                image_url
            ))

            conn.commit()
            release_db(conn)

            return redirect(url_for("admin_dashboard"))

        # =========================
        # EXISTING PDF/APK UPLOAD LOGIC
        # =========================
        file = request.files.get("file")

        if file and allowed_file(file.filename):

            filename = secure_filename(file.filename)
            ext = filename.rsplit(".", 1)[1].lower()

            if ext == "apk":
                os.makedirs(app.config["APK_FOLDER"], exist_ok=True)

                filepath = os.path.join(app.config["APK_FOLDER"], APP_APK_FILENAME)
                file.save(filepath)

                return redirect(url_for("admin_dashboard"))

            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            module_name = filename.replace(".pdf", "")
            save_pdf_to_db(module_name, filename)

            return redirect(url_for("admin_dashboard"))

    stats = get_dashboard_stats()
    install_stats = get_app_install_stats()

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT phone, action, details, created_at
        FROM activity_log
        ORDER BY created_at DESC
        LIMIT 100
    """)

    activities = c.fetchall()

    c.execute("SELECT phone, is_paid, payment_status FROM users")
    users = c.fetchall()
    # ===== OFFLINE REGISTRATIONS =====
    c.execute("""
        SELECT phone, full_name, location, detergent_choice, created_at
        FROM offline_registrations
        ORDER BY created_at DESC
    """)
    offline_regs = c.fetchall()
    
    c.execute("""
    SELECT details, COUNT(*)
    FROM activity_log
    WHERE action='open_module'
    GROUP BY details
    ORDER BY COUNT(*) DESC
    """)
    popular_modules = c.fetchall()

    c.execute("""
    SELECT phone, COUNT(*)
    FROM activity_log
    WHERE action='blocked_access'
    GROUP BY phone
    ORDER BY COUNT(*) DESC
    LIMIT 20
    """)

    blocked_users = c.fetchall()

    c.execute("""
    SELECT phone, followup_stage, last_followup
    FROM users
    WHERE is_paid = 0
    AND followup_stage > 0
    ORDER BY last_followup DESC
    """)

    followups = c.fetchall()
    c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE last_followup::date = CURRENT_DATE
    """)

    followups_today = c.fetchone()[0]
    
    c.execute("""
    SELECT phone, total_messages, ai_questions, modules_opened, last_active
    FROM student_metrics
    ORDER BY last_active DESC
    LIMIT 50
    """)
    students = c.fetchall()
    
    c.execute("""
    SELECT phone, template_name, status, error_details, created_at, updated_at
    FROM template_messages
    ORDER BY updated_at DESC
    LIMIT 50
    """)
    template_logs = c.fetchall()

    c.execute("""
        SELECT id, category, name, price, unit, seller_name, seller_phone,
               seller_location, status, created_at
        FROM marketplace_products
        ORDER BY created_at DESC
        LIMIT 100
    """)
    marketplace_products = c.fetchall()


    release_db(conn)
    
    html = "<h2>Arachis Admin Dashboard</h2>"

    # ===== STATS =====
    html += f"""
    <h3>📊 System Stats</h3>
    <ul>
        <li>Total WhatsApp Users: <b>{stats['total_users']}</b></li>
        <li>Paid Users: <b>{stats['paid_users']}</b></li>
        <li>Module Opens: <b>{stats['module_opens']}</b></li>
        <li>AI Questions Asked: <b>{stats['ai_questions']}</b></li>
        <li>Blocked Access Attempts: <b>{stats['blocked_attempts']}</b></li>
    </ul>

    <h3>📱 Android App Installs</h3>
    <ul>
        <li>Total App Installs / First Opens: <b>{install_stats['total_installs']}</b></li>
        <li>Active Today: <b>{install_stats['active_today']}</b></li>
        <li>Devices Linked To WhatsApp Number: <b>{install_stats['logged_in_devices']}</b></li>
    </ul>
    <hr>
    """
    html += "<h3>📲 Recent Android App Opens</h3>"

    if not install_stats["recent_installs"]:
        html += "<p>No app opens tracked yet.</p>"
    else:
        for r in install_stats["recent_installs"]:
            html += f"""
            📱 Device: {r[3]} |
            Phone: {r[1]} |
            Version: {r[2]} |
            First Open: {r[4]} |
            Last Open: {r[5]} |
            Opens: {r[6]}
            <br>
            """

    html += "<hr>"

    html += "<hr><h3>🚫 Users Blocked From Modules</h3>"

    for b in blocked_users:
        html += f"{b[0]} | Attempts: {b[1]}<br>"
    
    # ===== UPLOAD =====
    html += """
    <h3>📤 Upload Lesson PDF or Android APK</h3>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file" required>
        <button type="submit">Upload PDF</button>
    </form>
    <hr>
    """
    html += """
    <h3>🛒 Add Marketplace Product</h3>

    <form method="POST" enctype="multipart/form-data">
        <input type="hidden" name="form_action" value="add_marketplace_product">

        <label>Category</label><br>
        <select name="category" required>
            <option value="">-- Select Category --</option>
            <option value="Beverages">Beverages</option>
            <option value="Detergents">Detergents</option>
            <option value="Spices">Spices</option>
            <option value="Advanced Products">Advanced Products</option>
            <option value="Packaging">Packaging</option>
            <option value="Machinery and Tools">Machinery and Tools</option>
            <option value="Branding and Labels">Branding and Labels</option>
        </select>
        <br><br>

        <label>Product Name</label><br>
        <input type="text" name="name" required placeholder="Example: 750ml Dishwash Bottles">
        <br><br>

        <label>Description</label><br>
        <textarea name="description" rows="4" cols="60" placeholder="Short product description"></textarea>
        <br><br>

        <label>Price</label><br>
        <input type="text" name="price" placeholder="Example: $0.25">
        <br><br>

        <label>Unit / Size</label><br>
        <input type="text" name="unit" placeholder="Example: each, per kg, per litre">
        <br><br>

        <label>Seller Name</label><br>
        <input type="text" name="seller_name" placeholder="Example: Arachis Production Store">
        <br><br>

        <label>Seller Phone</label><br>
        <input type="text" name="seller_phone" placeholder="Example: +263773208904">
        <br><br>

        <label>Seller Location</label><br>
        <input type="text" name="seller_location" placeholder="Example: Harare CBD">
        <br><br>

        <label>Product Image Upload</label><br>
        <input type="file" name="marketplace_image" accept="image/*">
        <br><br>

        <label>OR Product Image URL</label><br>
        <input type="text" name="image_url" size="80" placeholder="https://example.com/product.jpg">
        <br><br>

        <button type="submit">✅ Add Product To Marketplace</button>
    </form>

    <hr>
    """
    html += "<h3>🛒 Marketplace Products</h3>"

    if not marketplace_products:
        html += "<p>No marketplace products yet.</p>"
    else:
        html += """
        <table border="1" cellpadding="6" cellspacing="0">
            <tr>
                <th>ID</th>
                <th>Category</th>
                <th>Name</th>
                <th>Price</th>
                <th>Seller</th>
                <th>Phone</th>
                <th>Location</th>
                <th>Status</th>
                <th>Actions</th>
            </tr>
        """

        for p in marketplace_products:
            product_id = p[0]
            category = p[1]
            name = p[2]
            price = p[3]
            unit = p[4]
            seller_name = p[5]
            seller_phone = p[6]
            seller_location = p[7]
            status = p[8]

            html += f"""
            <tr>
                <td>{product_id}</td>
                <td>{category}</td>
                <td>{name}</td>
                <td>{price} {unit}</td>
                <td>{seller_name}</td>
                <td>{seller_phone}</td>
                <td>{seller_location}</td>
                <td><b>{status}</b></td>
                <td>
                    <a href="/admin/marketplace/status/{product_id}/active">Approve/Active</a> |
                    <a href="/admin/marketplace/status/{product_id}/pending">Pending</a> |
                    <a href="/admin/marketplace/status/{product_id}/rejected">Reject</a> |
                    <a href="/admin/marketplace/delete/{product_id}" style="color:red;">Delete</a>
                </td>
            </tr>
            """

        html += "</table><hr>"

    # ===== USERS =====
    html += "<h3>👥 Users</h3>"
    for u in users:
        phone = u[0]
        is_paid = u[1]
        payment_status = u[2]
   
        html += f"""
        {phone} | Paid: {is_paid} | Status: {payment_status}
        | <a href='/admin/approve-package/{phone}/basic'>Approve Basic</a>
        | <a href='/admin/approve-package/{phone}/premium'>Approve Premium</a>
        | <a href='/admin/approve-package/{phone}/advanced'>Approve Advanced</a>
        | <a href='/admin/approve-package/{phone}/spices'>Approve Spices</a>
        | <a href='/admin/reset-device/{phone}'>Reset Device</a>
        | <a href='/admin/revoke/{phone}' style='color:red;'>Revoke Access</a><br>
        """

    html += "<hr><h3>📣 Follow-Up Funnel</h3>"

    if not followups:
        html += "<p>No users in follow-up funnel.</p>"
    else:
        for f in followups:
            phone = f[0]
            stage = f[1]
            last = f[2]

            html += f"""
            📱 {phone} |
            Stage: {stage} |
            Last Followup: {last} |
            <a href="/admin/send-followup/{phone}">📤 Send Message</a>
            <br>
            """
    html += "<hr><h3>🧑🏽‍🏫 Offline Registrations</h3>"

    if not offline_regs:
        html += "<p>No offline registrations yet.</p>"
    else:
        for reg in offline_regs:
            phone = reg[0]
            full_name = reg[1]
            location = reg[2]
            detergent = reg[3]
            created = reg[4]

            html += f"""
            <b>{full_name}</b><br>
            📞 {phone}<br>
            📍 {location}<br>
            🧪 {detergent}<br>
            🗓 {created}<br>
            <a href='/admin/approve-offline/{phone}'>✅ Approve</a>
            <hr>
            """
        html += "<hr><h3>🧠 Student Intelligence</h3>"

        for s in students:
            html += f"""
            📱 {s[0]} |
            💬 Msgs: {s[1]} |
            🤖 AI: {s[2]} |
            📚 Modules: {s[3]} |
            🕒 Last: {s[4]}
            <br>
            """    

        html += """
        <hr>
        <h3>📣 Marketing</h3>
        <a href="/admin/followup-unpaid">Send follow-up to unpaid users</a>
        <hr>
        """

    html += "<hr><h3>📨 Template Delivery Logs</h3>"

    if not template_logs:
        html += "<p>No template logs yet.</p>"
    else:
        for t in template_logs:
            html += f"""
            📱 {t[0]} |
            Template: {t[1]} |
            Status: <b>{t[2]}</b> |
            Error: {t[3]} |
            Sent: {t[4]} |
            Updated: {t[5]}
            <br>
            """

    html += "<hr><h3>📜 Activity Feed (Latest 1000)</h3>"

    # ===== ACTIVITY FEED =====
    for a in activities:
        phone = a[0]
        action = a[1]
        details = a[2]
        created_at = a[3]

        html += f"""
        <small>
        [{created_at}] <b>{phone}</b> → {action} ({details})
        </small><br>
        """
        
    return html

@app.route("/payment-result", methods=["POST"])
def payment_result():
    return "OK", 200

@app.route("/payment-success")
def payment_success():
    return "Payment received. You may return to WhatsApp."

@app.route("/admin/approve/<phone>")
@requires_auth
def admin_approve(phone):
    mark_paid(normalize_phone(phone))
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/approve-package/<phone>/<package>")
@requires_auth
def admin_approve_package(phone, package):
    phone = normalize_phone(phone)
    package = package.lower()

    if package not in ["basic", "premium", "advanced", "spices"]:
        return "Invalid package"

    has_spices = 1 if package in ["spices", "advanced"] else 0
    has_advanced = 1 if package == "advanced" else 0

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET is_paid=1,
            payment_status='approved',
            package=%s,
            has_spices=%s,
            has_advanced=%s,
            pending_purchase=NULL
        WHERE phone=%s
    """, (package, has_spices, has_advanced, phone))

    conn.commit()
    release_db(conn)

    send_message(
        phone,
        f"🎉 Payment Approved!\nPackage: {package.upper()}\nWava kukwanisa kuona malesson ako."
    )

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/revoke/<phone>")
@requires_auth
def admin_revoke(phone):
    phone = normalize_phone(phone)

    revoke_access(phone)

    send_message(
        phone,
        "⚠️ Your course access has been removed. If this is a mistake, contact Admin."
    )

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/reset-device/<phone>")
@requires_auth
def admin_reset_device(phone):
    phone = normalize_phone(phone)

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET device_id=NULL,
            device_model=NULL,
            device_locked_at=NULL
        WHERE phone=%s
    """, (phone,))

    conn.commit()
    release_db(conn)

    log_activity(phone, "device_lock_reset", "admin")

    send_message(
        phone,
        "✅ Your Arachis app device access has been reset.\n\n"
        "You can now login again using your approved WhatsApp number on your new phone."
    )

    return redirect(url_for("admin_dashboard"))
    
@app.route("/admin/approve-offline/<phone>")
def approve_offline(phone):

    phone = normalize_phone(phone)

    # mark user as paid
    mark_paid(phone)

    # optional: log activity
    log_activity(phone, "offline_approved", "admin")

    # send confirmation message
    send_message(phone, "🎉 Wagamuchirwa! Wava kukwanisa kuona zvidzidzo zviripo.")

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/marketplace/status/<int:product_id>/<status>")
@requires_auth
def admin_marketplace_status(product_id, status):

    if status not in ["active", "pending", "rejected"]:
        return "Invalid status"

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE marketplace_products
        SET status=%s
        WHERE id=%s
        RETURNING name, seller_phone
    """, (status, product_id))

    row = c.fetchone()

    conn.commit()
    release_db(conn)

    if row:
        product_name, seller_phone = row

        if seller_phone and status == "active":
            send_message(
                seller_phone,
                f"🎉 Your marketplace product is now active:\n\n"
                f"✔ {product_name}\n\n"
                "It can now appear in Arachis Marketplace."
            )

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/marketplace/delete/<int:product_id>")
@requires_auth
def admin_marketplace_delete(product_id):

    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM marketplace_products WHERE id=%s", (product_id,))

    conn.commit()
    release_db(conn)

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/followup-unpaid")
def followup_unpaid():

    conn = get_db()
    c = conn.cursor()

    c.execute("""
    SELECT phone, followup_stage
    FROM users
    WHERE is_paid = 0
    AND (last_followup IS NULL OR last_followup < NOW() - INTERVAL '24 HOURS')
    """)

    rows = c.fetchall()

    count = 0

    for phone, stage in rows:

        message = followup_message(stage)

        if message:
            send_template(phone, "reactivate_training")

            c.execute("""
            UPDATE users
            SET last_followup = NOW(),
                followup_stage = followup_stage + 1
            WHERE phone=%s
            """, (phone,))

            count += 1

    conn.commit()
    release_db(conn)

    return f"Sent {count} followups"

@app.route("/admin/send-followup/<phone>")
def admin_send_followup(phone):

    phone = normalize_phone(phone)

    conn = get_db()
    c = conn.cursor()

    c.execute("""
    SELECT followup_stage
    FROM users
    WHERE phone=%s
    """, (phone,))

    row = c.fetchone()

    if not row:
        DATABASE_POOL.putconn(conn)
        return "User not found"

    stage = row[0]

    message = followup_message(stage)

    if message:
        send_template(phone, "reactivate_training")

        c.execute("""
        UPDATE users
        SET last_followup = NOW(),
            followup_stage = followup_stage + 1
        WHERE phone=%s
        """, (phone,))

        conn.commit()

    release_db(conn)

    return redirect(url_for("admin_dashboard"))

@app.route("/data-deletion")
def data_deletion():
    return """
    <h2>Arachis Brands Data Deletion Policy</h2>
    <p>Users may request deletion of their WhatsApp data by contacting us at:</p>
    <p>Email: nkomobeloved3@gmail.com</p>
    <p>Or WhatsApp: +263773208904</p>
    <p>All requested data will be deleted within 7 working days.</p>
    """
@app.route("/api/mobile/install", methods=["POST"])
def mobile_install():
    try:
        data = request.get_json() or {}

        device_id = data.get("device_id", "").strip()
        phone = data.get("phone", "").strip()
        app_version = data.get("app_version", "").strip()
        device_model = data.get("device_model", "").strip()

        if phone:
            phone = normalize_phone(phone)

        if not device_id:
            return jsonify({
                "success": False,
                "message": "Device ID required"
            }), 400

        conn = get_db()
        c = conn.cursor()

        c.execute("""
            INSERT INTO app_installs (
                device_id,
                phone,
                app_version,
                device_model
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (device_id)
            DO UPDATE SET
                phone = COALESCE(NULLIF(EXCLUDED.phone, ''), app_installs.phone),
                app_version = EXCLUDED.app_version,
                device_model = EXCLUDED.device_model,
                last_opened_at = CURRENT_TIMESTAMP,
                open_count = app_installs.open_count + 1
        """, (
            device_id,
            phone,
            app_version,
            device_model
        ))

        conn.commit()
        release_db(conn)

        return jsonify({
            "success": True,
            "message": "Install tracked"
        })

    except Exception as e:
        print("MOBILE INSTALL TRACK ERROR:", e)
        return jsonify({
            "success": False,
            "message": "Server error"
        }), 500

@app.route("/api/mobile/login", methods=["POST"])
def mobile_login():
    try:
        data = request.get_json() or {}

        phone = data.get("phone", "").strip()
        device_id = data.get("device_id", "").strip()
        device_model = data.get("device_model", "").strip()
        app_version = data.get("app_version", "").strip()

        if not phone:
            return jsonify({
                "success": False,
                "message": "Phone number required"
            }), 400

        phone = normalize_phone(phone)

        # Admin can login without device restriction
        admin_login = is_admin_phone(phone)

        # Non-admin students must send device_id
        # TEMPORARY LEGACY APP SUPPORT
        # Old app versions such as v3.5 may not send device_id.
        # Allow them for now, but do not apply device lock.
        # Remove this grace support after most students update.
        legacy_app_without_device_id = False

        if not admin_login and not device_id:
            legacy_app_without_device_id = True

        conn = get_db()
        c = conn.cursor()

        c.execute("""
            SELECT phone, is_paid, package, device_id, device_model, device_locked_at
            FROM users
            WHERE phone = %s
        """, (phone,))

        user = c.fetchone()

        if not user:
            release_db(conn)
            return jsonify({
                "success": False,
                "message": "Number not found. Please contact admin."
            }), 404

        db_phone, is_paid, package, saved_device_id, saved_device_model, device_locked_at = user

        if not is_paid:
            release_db(conn)
            return jsonify({
                "success": False,
                "message": "Payment not approved yet."
            }), 403

        # TEMPORARY: allow old app versions without device_id
        # This keeps v3.5 students working while you push the new APK.
        if legacy_app_without_device_id:
            DATABASE_POOL.putconn(conn)

            allowed_modules = get_allowed_modules_for_user(phone)

            return jsonify({
                "success": True,
                "phone": db_phone,
                "package": package,
                "allowed_modules": allowed_modules,
                "device_lock": {
                    "locked": False,
                    "legacy_mode": True,
                    "message": (
                        "Login allowed temporarily. "
                        "Please update your Arachis app to the latest version for secure access."
                    )
                },
                "warning": "Please update your Arachis app to the latest version."
            })

        # =========================
        # DEVICE LOCK SECURITY
        # =========================
        if not admin_login:

            # First successful login: bind this WhatsApp number to this device
            if not saved_device_id:
                c.execute("""
                    UPDATE users
                    SET device_id=%s,
                        device_model=%s,
                        device_locked_at=CURRENT_TIMESTAMP
                    WHERE phone=%s
                """, (device_id, device_model, phone))

                conn.commit()

                log_activity(
                    phone,
                    "device_lock_created",
                    f"{device_model} | {device_id[:12]}"
                )

            # Same device: allow login and refresh device model
            elif saved_device_id == device_id:
                c.execute("""
                    UPDATE users
                    SET device_model=%s
                    WHERE phone=%s
                """, (device_model, phone))

                conn.commit()

            # Different device: check if 30 days have passed
            else:
                c.execute("""
                    SELECT
                    CASE
                        WHEN device_locked_at IS NULL THEN TRUE
                        WHEN device_locked_at < NOW() - INTERVAL '30 DAYS' THEN TRUE
                        ELSE FALSE
                    END
                    FROM users
                    WHERE phone=%s
                """, (phone,))

                can_change_device = c.fetchone()[0]

                if can_change_device:
                    c.execute("""
                        UPDATE users
                        SET device_id=%s,
                            device_model=%s,
                            device_locked_at=CURRENT_TIMESTAMP
                        WHERE phone=%s
                    """, (device_id, device_model, phone))

                    conn.commit()

                    log_activity(
                        phone,
                        "device_lock_changed_after_30_days",
                        f"New: {device_model} | {device_id[:12]}"
                    )

                else:
                    release_db(conn)

                    log_activity(
                        phone,
                        "device_lock_blocked",
                        f"Attempted device: {device_model} | {device_id[:12]}"
                    )

                    return jsonify({
                        "success": False,
                        "message": (
                            "This WhatsApp number is already linked to another device for 30 days. "
                            "If you changed phone, please contact Arachis Admin to reset your device access."
                        ),
                        "device_locked": True,
                        "reset_required": True
                    }), 403

        # Track install/open after successful login
        if device_id:
            c.execute("""
                INSERT INTO app_installs (
                    device_id,
                    phone,
                    app_version,
                    device_model
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (device_id)
                DO UPDATE SET
                    phone = COALESCE(NULLIF(EXCLUDED.phone, ''), app_installs.phone),
                    app_version = EXCLUDED.app_version,
                    device_model = EXCLUDED.device_model,
                    last_opened_at = CURRENT_TIMESTAMP,
                    open_count = app_installs.open_count + 1
            """, (
                device_id,
                phone,
                app_version,
                device_model
            ))

            conn.commit()

        release_db(conn)

        allowed_modules = get_allowed_modules_for_user(phone)

        return jsonify({
            "success": True,
            "phone": db_phone,
            "package": package,
            "allowed_modules": allowed_modules,
            "device_locked": False,
            "admin": admin_login
        })

    except Exception as e:
        print("MOBILE LOGIN ERROR:", e)
        return jsonify({
            "success": False,
            "message": "Server error. Please try again."
        }), 500

@app.route("/api/mobile/marketplace/products", methods=["GET"])
def mobile_marketplace_products():
    try:
        category = request.args.get("category", "").strip()
        search = request.args.get("search", "").strip()

        conn = get_db()
        c = conn.cursor()

        if search:
            term = f"%{search}%"

            c.execute("""
                SELECT id, category, name, description, price, unit,
                       seller_name, seller_phone, seller_location,
                       image_url, image_media_id, status, created_at
                FROM marketplace_products
                WHERE status='active'
                AND (
                    LOWER(name) LIKE LOWER(%s)
                    OR LOWER(category) LIKE LOWER(%s)
                    OR LOWER(description) LIKE LOWER(%s)
                    OR LOWER(seller_location) LIKE LOWER(%s)
                )
                ORDER BY created_at DESC
                LIMIT 100
            """, (term, term, term, term))

        elif category:
            c.execute("""
                SELECT id, category, name, description, price, unit,
                       seller_name, seller_phone, seller_location,
                       image_url, image_media_id, status, created_at
                FROM marketplace_products
                WHERE status='active'
                AND LOWER(category)=LOWER(%s)
                ORDER BY created_at DESC
                LIMIT 100
            """, (category,))

        else:
            c.execute("""
                SELECT id, category, name, description, price, unit,
                       seller_name, seller_phone, seller_location,
                       image_url, image_media_id, status, created_at
                FROM marketplace_products
                WHERE status='active'
                ORDER BY created_at DESC
                LIMIT 100
            """)

        rows = c.fetchall()
        release_db(conn)

        products = []

        for r in rows:
            product_id = r[0]
            image_url = r[9]
            image_media_id = r[10]

            # If product has a public image_url, use it.
            # If it only has WhatsApp media ID, the app may not display it permanently.
            final_image_url = image_url or ""

            products.append({
                "id": product_id,
                "category": r[1] or "",
                "name": r[2] or "",
                "description": r[3] or "",
                "price": r[4] or "Contact seller",
                "unit": r[5] or "",
                "seller_name": r[6] or "",
                "seller_phone": r[7] or "",
                "seller_location": r[8] or "",
                "image_url": final_image_url,
                "image_media_id": image_media_id or "",
                "status": r[11] or "",
                "created_at": str(r[12])
            })

        return jsonify({
            "success": True,
            "products": products
        })

    except Exception as e:
        print("MOBILE MARKETPLACE PRODUCTS ERROR:", e)

        return jsonify({
            "success": False,
            "message": "Failed to load marketplace products",
            "products": []
        }), 500

@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

try:
    init_db()
    auto_sync_lessons()
    seed_prices()
    seed_marketplace_products()
    print("Startup successful")
except Exception as e:
    print("Startup error:", e)

@app.route("/test-template")
def test_template():

    phone = "+263773208904"  # ⚠️ NOT your bot number

    print("🚀 TEST TEMPLATE TRIGGERED")

    send_template(phone, "reactivate_training")

    return "Template sent"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


































































































































































































































































































































































































































































































































      
           


































































































































































































































































































































































































































































































































