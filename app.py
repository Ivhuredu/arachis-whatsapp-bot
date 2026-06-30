import PyPDF2
import requests
from openai import OpenAI
from flask import Flask, request, jsonify, redirect, url_for
import psycopg2
from psycopg2 import pool
from urllib.parse import urlparse
import os
import base64
from werkzeug.utils import secure_filename
from functools import wraps
from flask import Response

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

DATABASE_POOL = None


app = Flask(__name__)

BASIC_PRICE = 5.0
PREMIUM_PRICE = 10.0
SPICES_PRICE = 10.0
ADVANCED_PRICE = 20.0
CUSTOM_PRICE_PER_MODULE = 2.0

UPGRADE_BASIC_TO_PREMIUM = 5.0
UPGRADE_BASIC_TO_SPICES = 5.0
UPGRADE_BASIC_TO_ADVANCED = 10.0
UPGRADE_PREMIUM_TO_SPICES = 5.0
UPGRADE_PREMIUM_TO_ADVANCED = 7.0    
PAYMENT_TOLERANCE = 1.5   # allows EcoCash charges
MIN_ACCEPTABLE = BASIC_PRICE
MAX_ACCEPTABLE = PREMIUM_PRICE + PAYMENT_TOLERANCE

# =========================
# CONFIG
# =========================
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

ADMIN_NUMBERS = [
    "+263773208904",
    "+263719208904"   # backup admin
]
DEVICE_LOCK_DAYS = 30

DISABLE_WHATSAPP_MEDIA_FROM = "2026-06-15"
UPLOAD_FOLDER = "static/lessons"
APK_FOLDER = "static/apk"
MARKETPLACE_FOLDER = "static/marketplace"

APP_APK_FILENAME = "arachis.apk"
APKPURE_URL = "https://apkpure.com/p/com.arachis.training"

ALLOWED_EXTENSIONS = {"pdf", "apk"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

app.config["MARKETPLACE_FOLDER"] = MARKETPLACE_FOLDER
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["APK_FOLDER"] = APK_FOLDER

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PACKAGES = {
    "basic": {
        "price": 5.0,
        "modules": [
            "dishwash",
            "liquid_laundry_soap",
            "fabric_softener",
            "thick_bleach",
            "washing_paste",
            "petroleum_jelly",
            "hair_shampoo",
            "universal_cordial",
            "low_cost_orange_drink",
            "low_cost_raspberry_drink",
            "freezits",
            "baobab_drink"
        ]
    },
    "premium": {
        "price": 10.0,
        "modules": "ALL"
    }
}

# =========================
# DATABASE
# =========================
def get_db():

    global DATABASE_POOL

    if DATABASE_POOL is None:

        database_url = os.getenv("DATABASE_URL")

        url = urlparse(database_url)

        DATABASE_POOL = psycopg2.pool.SimpleConnectionPool(
            1,
            10,
            dbname=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port,
            sslmode="require"
        )

    return DATABASE_POOL.getconn()
    
def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        phone TEXT UNIQUE,
        state TEXT DEFAULT 'main',
        payment_status TEXT DEFAULT 'none',
        is_paid INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS module_access (
        id SERIAL PRIMARY KEY,
        phone TEXT,
        module TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(phone, module)
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS custom_module_access (
        id SERIAL PRIMARY KEY,
        phone TEXT,
        module TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(phone, module)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS temp_orders (
        phone TEXT PRIMARY KEY,
        item TEXT,
        quantity INTEGER DEFAULT 1
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS offline_registrations (
        id SERIAL PRIMARY KEY,
        phone TEXT UNIQUE,
        full_name TEXT,
        location TEXT,
        detergent_choice TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    ALTER TABLE offline_registrations
    ADD COLUMN IF NOT EXISTS location TEXT
    """)

    c.execute("""
    ALTER TABLE offline_registrations
    ADD COLUMN IF NOT EXISTS detergent_choice TEXT
    """)

        
    c.execute("""
       CREATE TABLE IF NOT EXISTS activity_log (
       id SERIAL PRIMARY KEY,
       phone TEXT,
       action TEXT,
       details TEXT,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
        ALTER TABLE activity_log 
        ADD COLUMN IF NOT EXISTS details TEXT
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS lesson_content (
        id SERIAL PRIMARY KEY,
        module TEXT UNIQUE,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS student_metrics (
        phone TEXT PRIMARY KEY,
        total_messages INTEGER DEFAULT 0,
        ai_questions INTEGER DEFAULT 0,
        modules_opened INTEGER DEFAULT 0,
        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS processed_messages (
        whatsapp_message_id TEXT PRIMARY KEY,
        phone TEXT,
        incoming TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_followup TIMESTAMP
    """)
    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS active_module TEXT
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS ai_memory (
        id SERIAL PRIMARY KEY,
        phone TEXT,
        module TEXT,
        role TEXT,
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS template_messages (
        id SERIAL PRIMARY KEY,
        phone TEXT,
        template_name TEXT,
        whatsapp_message_id TEXT UNIQUE,
        status TEXT DEFAULT 'accepted',
        error_details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS outbound_messages (
        id SERIAL PRIMARY KEY,
        phone TEXT,
        whatsapp_message_id TEXT UNIQUE,
        message_type TEXT,
        status TEXT DEFAULT 'accepted',
        error_details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        phone TEXT,
        reference TEXT UNIQUE,
        amount REAL,
        raw_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS followup_stage INTEGER DEFAULT 0
    """)
    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS package TEXT DEFAULT 'none'
    """)
    
    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS device_id TEXT
    """)

    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS device_model TEXT
    """)

    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS device_locked_at TIMESTAMP
    """)
    c.execute("""
    ALTER TABLE module_access
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    """)
    
    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS has_spices INTEGER DEFAULT 0
    """)

    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS has_advanced INTEGER DEFAULT 0
    """)

    c.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS pending_purchase TEXT
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS marketplace_products (
        id SERIAL PRIMARY KEY,
        category TEXT,
        name TEXT,
        description TEXT,
        price TEXT,
        unit TEXT,
        seller_name TEXT,
        seller_phone TEXT,
        seller_location TEXT,
        image_url TEXT,
        image_media_id TEXT,
        status TEXT DEFAULT 'pending',
        created_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS marketplace_temp (
        phone TEXT PRIMARY KEY,
        data TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS marketplace_carts (
        phone TEXT PRIMARY KEY,
        cart TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ingredient_prices (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        price_per_unit REAL,
        unit TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS app_installs (
        id SERIAL PRIMARY KEY,
        device_id TEXT UNIQUE,
        phone TEXT,
        app_version TEXT,
        device_model TEXT,
        first_opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        open_count INTEGER DEFAULT 1
    )
    """)
    
    conn.commit()
    DATABASE_POOL.putconn(conn)
    


# =========================
# HELPERS
# =========================
def normalize_phone(phone):
    return phone if phone.startswith("+") else "+" + phone

def is_admin_phone(phone):
    return phone in ADMIN_NUMBERS

def safe_text(value):
    if value is None:
        return ""

    text = str(value)

    # remove broken emoji surrogate characters like \ud83d
    text = text.encode("utf-8", "ignore").decode("utf-8", "ignore")

    return text
    
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
                DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

def get_all_prices():

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT name, price_per_unit, unit FROM ingredient_prices")

    rows = c.fetchall()
    DATABASE_POOL.putconn(conn)

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

def create_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (phone)
        VALUES (%s)
        ON CONFLICT (phone) DO NOTHING
    """, (phone,))
    conn.commit()
    DATABASE_POOL.putconn(conn)

def get_unpaid_active_users():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    SELECT u.phone
    FROM users u
    LEFT JOIN student_metrics s ON u.phone = s.phone
    WHERE u.is_paid = 0
    AND (s.total_messages > 2 OR s.modules_opened > 0)
    AND (
        u.last_followup IS NULL
        OR u.last_followup < NOW() - INTERVAL '24 HOURS'
    )
    """)

    rows = c.fetchall()
    DATABASE_POOL.putconn(conn)

    return [r[0] for r in rows]
    
def followup_message(stage):

    stage = stage % 7   # 🔁 recycle messages forever

    messages = {

        0: (
            "👋 Makadii!\n\n"
            "Makamboshandisa Arachis Training Bot asi hamusati majoina training.\n\n"
            "Vanhu vakawanda vari kutotanga kugadzira dishwash & bleach kumba.\n\n"
            "💵 Full training: $5 once-off.\n"
            "Nyora *PAY* kuti utange."
        ),

        1: (
            "🧼 Vanhu vakawanda vari kutotanga kugadzira ma detergents kumba.\n\n"
            "Course ine:\n"
            "✔ 20 detergent modules\n"
            "✔ 10 drink modules\n"
            "✔ Rubatsiro rwe AI kana product yako ikakanganisika\n\n"
            "Nyora *PAY* kuti utange kudzidza."
        ),

        2: (
            "🎉 Ma students akawanda ari kutotanga mabhizinesi madiki.\n\n"
            "Vamwe vari kutengesa:\n"
            "✔ Dishwash\n"
            "✔ Bleach\n"
            "✔ Cream soda\n\n"
            "Unogonawo kutanga.\n"
            "Nyora *PAY* kuti utange course."
        ),

        3: (
            "🤖 Course iyi ine *AI trainer*.\n\n"
            "Kana formula yako yakanganisika unogona kubvunza bot.\n\n"
            "Inokuudza:\n"
            "✔ chii chakanganisika\n"
            "✔ kuti ugadzirise sei\n\n"
            "Nyora *PAY* kuti uvhure course."
        ),

        4: (
            "💰 Bhizinesi re madetergents rinogona kutangwa nemari shoma.\n\n"
            "Example:\n"
            "20L Dishwash inogona kugadzirwa nemari isingapfuuri $15\n"
            "wozoitengesa mari ingasvika $25.\n\n"
            "Nyora *PAY* kuti udzidze maformula."
        ),

        5: (
            "📚 Course yedu inosanganisira:\n\n"
            "✔ 30 production lessons\n"
            "✔ AI trainer\n"
            "✔ Supplier directory\n"
            "✔ Business guidance\n\n"
            "💵 Only $5 once-off.\n"
            "Nyora *PAY* kuti utange."
        ),

        6: (
            "⚠ *Reminder*\n\n"
            "Course ichiri $5 chete asi promotion iyi inogona kupera mumazuva mashoma anotevera.\n\n"
            "Kana uchida kudzidza kugadzira detergents nemadrinks,\n"
            "Nyora *PAY* kuti utange."
        )
    }

    return messages.get(stage)

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
        DATABASE_POOL.putconn(conn)

    except Exception as e:
        print("TEMPLATE SAVE ERROR:", e)

    return response.status_code, response.text
    
def get_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone, state, payment_status, is_paid, package FROM users WHERE phone=%s", (phone,))
    row = c.fetchone()
    DATABASE_POOL.putconn(conn)

    if not row:
        return None

    return {
        "phone": row[0],
        "state": row[1],
        "payment_status": row[2],
        "is_paid": row[3],
        "package": row[4]
    }

def get_allowed_modules_for_user(phone):
    user = get_user(phone)

    if not user or not user["is_paid"]:
        return []

    package = user.get("package")

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT has_spices, has_advanced
        FROM users
        WHERE phone=%s
    """, (phone,))

    row = c.fetchone()
    DATABASE_POOL.putconn(conn)

    has_spices = row[0] if row else 0
    has_advanced = row[1] if row else 0

    allowed_modules = []

    if package == "basic":
        allowed_modules += PACKAGES["basic"]["modules"]

    elif package in ["premium", "advanced"]:
        allowed_modules += DETERGENT_MODULES + BEVERAGE_MODULES

    elif package == "spices":
        allowed_modules += SPICE_MODULES

    elif package == "custom":
        allowed_modules += get_custom_modules(phone)

    if has_spices == 1:
        allowed_modules += SPICE_MODULES

    if has_advanced == 1 or package == "advanced":
        allowed_modules += DETERGENT_MODULES + BEVERAGE_MODULES + SPICE_MODULES + ADVANCED_MODULES

    return list(dict.fromkeys(allowed_modules))

def set_state(phone, state):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET state=%s WHERE phone=%s", (state, phone))
    conn.commit()
    DATABASE_POOL.putconn(conn)

    log_activity(phone, "state_change", state)

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
    DATABASE_POOL.putconn(conn)

def set_payment_status(phone, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET payment_status=%s WHERE phone=%s", (status, phone))
    conn.commit()
    DATABASE_POOL.putconn(conn)

def mark_paid(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_paid=1, payment_status='approved' WHERE phone=%s",
        (phone,)
    )
    conn.commit()
    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

    log_activity(phone, "access_revoked", "admin")

def ai_questions_today(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT COUNT(*) FROM activity_log
        WHERE phone = %s
        AND action = 'ai_question'
        AND DATE(created_at) = CURRENT_DATE
    """, (phone,))

    count = c.fetchone()[0]
    DATABASE_POOL.putconn(conn)
    return count

   
def record_module_access(phone, module):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO module_access (phone, module)
        VALUES (%s, %s)
        ON CONFLICT (phone, module) DO NOTHING
    """, (phone, module))
    conn.commit()
    DATABASE_POOL.putconn(conn)

def add_custom_module(phone, module):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO custom_module_access (phone, module)
        VALUES (%s, %s)
        ON CONFLICT (phone, module) DO NOTHING
    """, (phone, module))

    conn.commit()
    DATABASE_POOL.putconn(conn)


def get_custom_modules(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT module FROM custom_module_access
        WHERE phone=%s
        ORDER BY created_at ASC
    """, (phone,))

    rows = c.fetchall()
    DATABASE_POOL.putconn(conn)

    return [r[0] for r in rows]


def clear_custom_modules(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM custom_module_access WHERE phone=%s", (phone,))

    conn.commit()
    DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

        return inserted is None

    except Exception as e:
        print("DEDUP ERROR:", e)
        conn.rollback()
        DATABASE_POOL.putconn(conn)
        return False
        
def log_activity(phone, action, details=""):
    details = safe_text(details)[:1000]
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO activity_log (phone, action, details)
        VALUES (%s, %s, %s)
    """, (phone, action, details))
    conn.commit()
    DATABASE_POOL.putconn(conn)

def get_app_install_stats():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM app_installs")
    total_installs = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*)
        FROM app_installs
        WHERE last_opened_at::date = CURRENT_DATE
    """)
    active_today = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*)
        FROM app_installs
        WHERE phone IS NOT NULL
        AND phone <> ''
    """)
    logged_in_devices = c.fetchone()[0]

    c.execute("""
        SELECT device_id, phone, app_version, device_model, first_opened_at, last_opened_at, open_count
        FROM app_installs
        ORDER BY last_opened_at DESC
        LIMIT 50
    """)
    recent_installs = c.fetchall()

    DATABASE_POOL.putconn(conn)

    return {
        "total_installs": total_installs,
        "active_today": active_today,
        "logged_in_devices": logged_in_devices,
        "recent_installs": recent_installs
    }

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
        DATABASE_POOL.putconn(conn)
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
            DATABASE_POOL.putconn(conn)
            return False, "Mari ishoma. Advanced Full Package iri $20."
        package = "advanced"

    elif pending_purchase == "spices_full":
        if amount < SPICES_PRICE:
            DATABASE_POOL.putconn(conn)
            return False, "Mari ishoma. Spices & Seasonings package iri $10."
        package = "spices"

    elif pending_purchase == "upgrade_basic_to_premium":
        if amount < UPGRADE_BASIC_TO_PREMIUM:
            DATABASE_POOL.putconn(conn)
            return False, "Mari ishoma. Upgrade yeBasic to Premium iri $5."
        package = "premium"

    elif pending_purchase == "upgrade_basic_to_spices":
        if amount < UPGRADE_BASIC_TO_SPICES:
            DATABASE_POOL.putconn(conn)
            return False, "Mari ishoma. Add Spices iri $5."
        package = current_package

    elif pending_purchase == "upgrade_basic_to_advanced":
        if amount < UPGRADE_BASIC_TO_ADVANCED:
            DATABASE_POOL.putconn(conn)
            return False, "Mari ishoma. Basic to Advanced upgrade iri $10."
        package = "advanced"

    elif pending_purchase == "upgrade_premium_to_spices":
        if amount < UPGRADE_PREMIUM_TO_SPICES:
            DATABASE_POOL.putconn(conn)
            return False, "Mari ishoma. Premium add Spices iri $5."
        package = current_package

    elif pending_purchase == "upgrade_premium_to_advanced":
        if amount < UPGRADE_PREMIUM_TO_ADVANCED:
            DATABASE_POOL.putconn(conn)
            return False, "Mari ishoma. Premium to Advanced upgrade iri $7."
        package = "advanced"

    elif current_package == "custom":
        selected_modules = get_custom_modules(phone)
        expected_amount = len(selected_modules) * CUSTOM_PRICE_PER_MODULE

        if expected_amount <= 0:
            DATABASE_POOL.putconn(conn)
            return False, "Hausati wasarudza ma formula eCustom Package."

        if amount < expected_amount:
            DATABASE_POOL.putconn(conn)
            return False, f"Mari ishoma. Custom package yako iri ${expected_amount:.2f}."

        package = "custom"

    elif current_package == "basic":
        if amount < BASIC_PRICE:
            DATABASE_POOL.putconn(conn)
            return False, f"Mari ishoma. Basic package iri ${BASIC_PRICE:.2f}."
        package = "basic"

    elif current_package == "premium":
        if amount < PREMIUM_PRICE:
            DATABASE_POOL.putconn(conn)
            return False, f"Mari ishoma. Premium package iri ${PREMIUM_PRICE:.2f}."
        package = "premium"
        
    c.execute("""
        INSERT INTO payments (phone, reference, amount, raw_text)
        VALUES (%s,%s,%s,%s)
    """, (phone, reference, amount, message))

    conn.commit()
    DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

    send_admin_alert(
        "AUTO PAYMENT APPROVED",
        f"Phone: {phone}\nPaid: ${amount}\nPackage: {package.upper()}\nRef: {reference}"
    )

    return True, f"🎉 Payment confirmed!\nPackage: {package.upper()}\nWava kukwanisa kuvhura ma lessons."

# =========================
# AI MEMORY SYSTEM
# =========================

MAX_MEMORY_MESSAGES = 4   # last 6 exchanges

def save_memory(phone, module, role, message):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO ai_memory (phone, module, role, message)
        VALUES (%s,%s,%s,%s)
    """, (phone, module, role, message))

    # Trim old memory (keep only last N)
    c.execute("""
        DELETE FROM ai_memory
        WHERE id NOT IN (
            SELECT id FROM ai_memory
            WHERE phone=%s AND module=%s
            ORDER BY created_at DESC
            LIMIT %s
        )
        AND phone=%s AND module=%s
    """, (phone, module, MAX_MEMORY_MESSAGES, phone, module))

    conn.commit()
    DATABASE_POOL.putconn(conn)


def get_memory(phone, module):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT role, message
        FROM ai_memory
        WHERE phone=%s AND module=%s
        ORDER BY created_at ASC
    """, (phone, module))

    rows = c.fetchall()
    DATABASE_POOL.putconn(conn)

    memory = []
    for r in rows:
        memory.append({"role": r[0], "content": r[1]})

    return memory

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
    DATABASE_POOL.putconn(conn)

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

    DATABASE_POOL.putconn(conn)

def get_lesson_from_db(module_name):

    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT content FROM lesson_content WHERE module=%s",
        (module_name,)
    )

    row = c.fetchone()
    DATABASE_POOL.putconn(conn)

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

    
def get_dashboard_stats():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE is_paid=1")
    paid_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM activity_log WHERE action='open_module'")
    module_opens = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM activity_log WHERE action='ai_question'")
    ai_questions = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM activity_log WHERE action='blocked_access'")
    blocked_attempts = c.fetchone()[0]

    DATABASE_POOL.putconn(conn)

    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "module_opens": module_opens,
        "ai_questions": ai_questions,
        "blocked_attempts": blocked_attempts
    }



# ✅ NEW (REQUIRED FOR AI RESTRICTION)
def get_user_modules(phone, message):

    conn = get_db()
    c = conn.cursor()

    # get modules user opened
    c.execute(
        "SELECT module FROM module_access WHERE phone=%s",
        (phone,)
    )

    rows = c.fetchall()
    user_modules = [r[0] for r in rows]

    # get active module
    c.execute(
        "SELECT active_module FROM users WHERE phone=%s",
        (phone,)
    )

    row = c.fetchone()

    DATABASE_POOL.putconn(conn)

    if row and row[0]:
        return [row[0]]

    # detect module from question
    detected = detect_module_from_question(message, user_modules)

    if detected:

        conn = get_db()
        c = conn.cursor()

        c.execute(
            "UPDATE users SET active_module=%s WHERE phone=%s",
            (detected, phone)
        )

        conn.commit()
        DATABASE_POOL.putconn(conn)

        return [detected]

    if user_modules:
        return [user_modules[-1]]

    return []
    
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


def get_detergent_modules():

    modules = load_lessons()

    drinks = get_drink_modules()

    return [k for k in modules if k not in drinks]

STORE_ITEMS = {
    "sles": {
        "name": "SLES (Sodium Lauryl Ether Sulfate)",
        "price": "$3.25 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "caustic": {
        "name": "Caustic Soda",
        "price": "$2.25 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "hypo": {
        "name": "Sodium Hypochlorite",
        "price": "$2 per litre",
        "sizes": "1L | 5L | 20L"
    },
    "cde": {
        "name": "CDE (Cocamide DEA)",
        "price": "$0.0 per litre",
        "sizes": "1L | 5L"
    },
    "perfume": {
        "name": "Detergent Perfumes",
        "price": "$1 per 30ml",
        "sizes": "30ml | 50ml | 100ml"
    },
     "soda": {
        "name": "Soda Ash",
        "price": "$2.25 per kg",
        "sizes": "500ml| 1L | 5L"
    },
    "bermacol": {
        "name": "Bermacol",
        "price": "$7 per 1kg",
        "sizes": "50g | 100g | 500g | 1kg"
    },
    "amido": {
        "name": "Amido",
        "price": "$3.5 per litre",
        "sizes": "50ml | 100mL | 5L"
    },
    "formalin": {
        "name": "Formalin",
        "price": "$1 per 50ml",
        "sizes": "20ml | 50ml | 500ml"
    },
     "dye": {
        "name": "Detergents Dye",
        "price": "$3 per 100g",
        "sizes": "20ml | 50ml | 100g"
    },
    "ardogen": {
        "name": "Ardogen",
        "price": "$0.0 per 1kg",
        "sizes": "100g | 500g | 1kg"
    },
    "sulphonic": {
        "name": "Sulphonic Acid",
        "price": "$3.25 per kg",
        "sizes": "1ltr | 5ltr | 25ltr"
    },
    "glycerin": {
        "name": "Glycerin",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "np6": {
        "name": "Np6",
        "price": "$6 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "pineoil": {
        "name": "Pine Oil",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "tallow": {
        "name": "Tallow",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "dolomite": {
        "name": "Dolomite",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "soapdye": {
        "name": "Liquid Soap Dye",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "petroleumjelly": {
        "name": "Petroleum Jelly",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "dye": {
        "name": "Dye (Oil-based",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "whiteoil": {
        "name": "White Oil",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    }, 
     "wax": {
        "name": "Wax",
        "price": "$3 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "hardener": {
        "name": "Hardener",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "oxide": {
        "name": "Oxide",
        "price": "$3.5 per kg",
        "sizes": "1kg | 5kg | 25kg"
    }, 
     "paraffin": {
        "name": "Paraffin",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "savenix": {
        "name": "Savenix",
        "price": "$3.5 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "thickener": {
        "name": "Thickener",
        "price": "$5.5 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "colesents": {
        "name": "Colesents",
        "price": "$6.5 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "np9": {
        "name": "NP9",
        "price": "$6 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    
}

MARKETPLACE_CATEGORIES = {
    "1": "Beverages",
    "2": "Detergents",
    "3": "Spices",
    "4": "Advanced Products",
    "5": "Packaging",
    "6": "Machinery and Tools",
    "7": "Branding and Labels"
}


def save_marketplace_temp(phone, data):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO marketplace_temp (phone, data)
        VALUES (%s, %s)
        ON CONFLICT (phone)
        DO UPDATE SET data = EXCLUDED.data,
                      created_at = CURRENT_TIMESTAMP
    """, (phone, data))

    conn.commit()
    DATABASE_POOL.putconn(conn)


def get_marketplace_temp(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT data FROM marketplace_temp WHERE phone=%s", (phone,))
    row = c.fetchone()

    DATABASE_POOL.putconn(conn)

    return row[0] if row else ""


def clear_marketplace_temp(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM marketplace_temp WHERE phone=%s", (phone,))

    conn.commit()
    DATABASE_POOL.putconn(conn)


def seed_marketplace_products():
    """
    Adds a few example products only if marketplace is empty.
    You can edit these products later.
    """

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM marketplace_products")
    count = c.fetchone()[0]

    if count > 0:
        DATABASE_POOL.putconn(conn)
        return

    products = [
        {
            "category": "Detergents",
            "name": "SLES",
            "description": "Used for dishwash, foam bath, shampoo and other foaming detergents.",
            "price": "$3.50",
            "unit": "per kg",
            "seller_name": "Arachis Production Store",
            "seller_phone": "+263773208904",
            "seller_location": "Zimbabwe",
            "image_url": "https://arachis-whatsapp-bot-2.onrender.com/static/marketplace/sles.jpg",
            "status": "active"
        },
        {
            "category": "Detergents",
            "name": "Sulphonic Acid",
            "description": "Used in dishwash, liquid soap and many detergent formulas.",
            "price": "$4.50",
            "unit": "per litre",
            "seller_name": "Arachis Production Store",
            "seller_phone": "+263773208904",
            "seller_location": "Zimbabwe",
            "image_url": "https://arachis-whatsapp-bot-2.onrender.com/static/marketplace/sulphonic_acid.jpg",
            "status": "active"
        },
        {
            "category": "Detergents",
            "name": "Caustic Soda",
            "description": "Used for neutralising sulphonic acid and other detergent applications. Handle with care.",
            "price": "$3.00",
            "unit": "per kg",
            "seller_name": "Arachis Production Store",
            "seller_phone": "+263773208904",
            "seller_location": "Zimbabwe",
            "image_url": "https://arachis-whatsapp-bot-2.onrender.com/static/marketplace/caustic_soda.jpg",
            "status": "active"
        },
        {
            "category": "Packaging",
            "name": "750ml Dishwash Bottles",
            "description": "Empty bottles suitable for packaging dishwash and other liquid products.",
            "price": "$0.25",
            "unit": "each",
            "seller_name": "Arachis Production Store",
            "seller_phone": "+263773208904",
            "seller_location": "Zimbabwe",
            "image_url": "https://arachis-whatsapp-bot-2.onrender.com/static/marketplace/dishwash_bottle.jpg",
            "status": "active"
        },
        {
            "category": "Spices",
            "name": "Chicken Spice Ingredients",
            "description": "Ingredients for blending chicken spice for resale.",
            "price": "Contact seller",
            "unit": "",
            "seller_name": "Arachis Production Store",
            "seller_phone": "+263773208904",
            "seller_location": "Zimbabwe",
            "image_url": "https://arachis-whatsapp-bot-2.onrender.com/static/marketplace/chicken_spice.jpg",
            "status": "active"
        },
        {
            "category": "Machinery and Tools",
            "name": "Mixing Bucket",
            "description": "Plastic bucket for small-scale detergent production.",
            "price": "Contact seller",
            "unit": "",
            "seller_name": "Arachis Production Store",
            "seller_phone": "+263773208904",
            "seller_location": "Zimbabwe",
            "image_url": "https://arachis-whatsapp-bot-2.onrender.com/static/marketplace/mixing_bucket.jpg",
            "status": "active"
        },
        {
            "category": "Branding and Labels",
            "name": "Product Label Design",
            "description": "Custom label design for dishwash, bleach, drinks, spices and cosmetics.",
            "price": "Contact seller",
            "unit": "",
            "seller_name": "Arachis Branding Desk",
            "seller_phone": "+263773208904",
            "seller_location": "Online",
            "image_url": "https://arachis-whatsapp-bot-2.onrender.com/static/marketplace/label_design.jpg",
            "status": "active"
        }
    ]

    for p in products:
        c.execute("""
            INSERT INTO marketplace_products (
                category, name, description, price, unit,
                seller_name, seller_phone, seller_location,
                image_url, status, created_by
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            p["category"],
            p["name"],
            p["description"],
            p["price"],
            p["unit"],
            p["seller_name"],
            p["seller_phone"],
            p["seller_location"],
            p["image_url"],
            p["status"],
            "system"
        ))

    conn.commit()
    DATABASE_POOL.putconn(conn)


def get_featured_products(limit=5):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT id, name, category, price, unit, seller_location
        FROM marketplace_products
        WHERE status='active'
        ORDER BY created_at DESC
        LIMIT %s
    """, (limit,))

    rows = c.fetchall()
    DATABASE_POOL.putconn(conn)

    return rows


def get_products_by_category(category, limit=20):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT id, name, category, price, unit, seller_location
        FROM marketplace_products
        WHERE status='active'
        AND LOWER(category)=LOWER(%s)
        ORDER BY created_at DESC
        LIMIT %s
    """, (category, limit))

    rows = c.fetchall()
    DATABASE_POOL.putconn(conn)

    return rows


def search_marketplace_products(search_term, limit=20):
    conn = get_db()
    c = conn.cursor()

    term = f"%{search_term}%"

    c.execute("""
        SELECT id, name, category, price, unit, seller_location
        FROM marketplace_products
        WHERE status='active'
        AND (
            LOWER(name) LIKE LOWER(%s)
            OR LOWER(category) LIKE LOWER(%s)
            OR LOWER(description) LIKE LOWER(%s)
            OR LOWER(seller_location) LIKE LOWER(%s)
        )
        ORDER BY created_at DESC
        LIMIT %s
    """, (term, term, term, term, limit))

    rows = c.fetchall()
    DATABASE_POOL.putconn(conn)

    return rows


def get_marketplace_product(product_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT id, category, name, description, price, unit,
               seller_name, seller_phone, seller_location,
               image_url, image_media_id, status
        FROM marketplace_products
        WHERE id=%s
    """, (product_id,))

    row = c.fetchone()
    DATABASE_POOL.putconn(conn)

    return row


def build_marketplace_home(phone):
    featured = get_featured_products(5)

    save_marketplace_temp(
        phone,
        "featured:" + ",".join([str(p[0]) for p in featured])
    )

    text = (
        "🛒 *ARACHIS MARKETPLACE*\n\n"
        "Buy and sell ingredients, packaging, tools and services used by Arachis students.\n\n"
        "📂 *CATEGORIES*\n"
        "1️⃣ Beverages\n"
        "2️⃣ Detergents\n"
        "3️⃣ Spices\n"
        "4️⃣ Advanced Products\n"
        "5️⃣ Packaging\n"
        "6️⃣ Machinery and Tools\n"
        "7️⃣ Branding and Labels\n\n"
        "🔎 Type *SEARCH* to search for a product.\n"
        "🛒 Type *CART* to view selected products.\n"
        "📤 Type *SELL* to upload your product for sale.\n\n"
    )

    if featured:
        text += "⭐ *FEATURED PRODUCTS*\n"
        for i, p in enumerate(featured, start=1):
            product_id, name, category, price, unit, location = p
            text += f"P{i}. {name} - {price} {unit} | {location}\n"

        text += "\nReply with category number or featured product code, e.g. *P1*.\n"

    text += "\n↩ Type *MENU* to go back."

    return text


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
    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)


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

    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)


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

DELIVERY_FEES = {
    "mataga": 7,
    "mberengwa": 7,
    "gweru": 5,
    "bulawayo": 7,
    "harare": 3
}

DEFAULT_DELIVERY_FEE = 7  # if town not listed

BUSINESS_MODULES = {
    "business_pricing_profit": ("business_pricing_profit.pdf", "💰 Pricing & Profit"),
    "business_packaging": ("business_packaging.pdf", "📦 Packaging & Branding"),
    "business_selling": ("business_selling.pdf", "📍 Where To Sell"),
    "business_scaling": ("business_scaling.pdf", "📈 Scaling Business"),
    "business_strategy": ("business_strategy.pdf", "🇿🇼 Zimbabwe Strategy")
}
DETERGENT_MODULES = [
    "dishwash",
    "liquid_laundry_soap",
    "fabric_softener",
    "thick_bleach",
    "washing_paste",
    "toilet_cleaner",
    "pine_gel",
    "foam_bath",
    "car_shampoo",
    "engine_cleaner",
    "perfume",
    "acidic_metal_degreaser",
    "tile_cleaner",
    "floor_polish",
    "tyre_polish",
    "paste_shoe_polish",
    "liquid_shoe_polish",
    "hair_shampoo",
    "hair_conditioner",
    "petroleum_jelly",
    "bath_soap",
    "laundry_bar",
    "floor_glaze",
    "washing_powder",
    "scouring_powder",
    "roll_on"
]
BEVERAGE_MODULES = sorted([
    "universal_cordial",
    "low_cost_raspberry_drink",
    "low_cost_orange_drink",
    "baobab_drink",
    "juice_cascade",
    "ice_cream",
    "cream_soda",
    "orange_drink",
    "raspberry_drink",
    "freezits"
])
ADVANCED_MODULES = [
    "paint",
    "gummies",
    "glue",
    "maheu",
    "lotion",
    "body_cream",
    "body_butter",
    "peanut_butter",
    "lollipop_sweets",
    "peanut_butter",
    "thinners",
    "yoghurt",
    "methylated_spirit",
    "battery_acid",
    "deo_blocks"
]
SPICE_MODULES = [
    "chicken_spice",
    "peri_peri_spice",
    "curry_powder",
    "curry_beef_spice",
    "curry_garlic_herb",
    "rice_spice",
    "tea_masala",
    "ginger_powder",
    "cinnamon_blend",
    "royco_style_soup",
    "sauce_spice_base"
]



# =========================
# MENUS
# =========================
def main_menu():
    return (
        "🏠 *ARACHIS DASHBOARD*\n\n"

        "📚 *LEARN*\n"
        "1️⃣ Course Lessons\n"
        "2️⃣ 💼 Business Training\n\n"

        "🧠 *TOOLS*\n"
        "3️⃣ 📊 Profit Calculator\n"
        "4️⃣ 🤖 Ask AI Trainer\n\n"

        "🛒 *RESOURCES*\n"
        "5️⃣ 🛒 Marketplace - Buy & Sell Products\n"
        "6️⃣ 🏭 Supplier Directory\n\n"

        "💳 *ACCOUNT*\n"
        "7️⃣ Upgrade Plan\n"
        "8️⃣ Help\n"
        "9️⃣ Account Dashboard\n"
        "🔟 Download App\n"
    )

def welcome_message():
    return (
        "👋 Makadini!\n\n"
        "Mazvita mauya! Vanhu vakawanda vari kutotanga kugadzira ma detergents nemadrinks vachibatsirwa nekosi ino. Nemiwo munogona kudzidza kugadzira:\n\n"
        "✔ Dishwash\n"
        "✔ Thick Bleach\n"
        "✔ Ice Cream\n"
        "✔ Concentrate Drinks nezvimwe\n\n"
        "🏠 Unogona kutanga kutodzidza izvozvi pafoni pako uye kutanga bhizinesi rako uri kumba.\n\n"
        "📚 Full training:Basic $5 | Premium $10\n\n"
        "🏠 Kana une zvimwe zvaungada kuziva kana kubatsirwa taura naAdmin wedu pa +263773208904.\n\n"
        "Reply *PAY* kuti ubhadhare uye utange kudzidza."
    )

# =========================
# AI FAQ
# =========================
def faq_engine(msg):

    m = msg.lower()

    faq_map = {
        "ingredients": "Unogona kuwana ma ingredients kuma chemical suppliers. Nyora *9* paMENU uone supplier directory.",
        "ndomawana kupi": "Nyora *9* paMENU uone vatengesi vemachemicals vari pedyo.",
        "kubhadhara sei": "Kubhadhara nyora *PAY* wobva watevera mirairo yeEcoCash.",
        "payment": "Nyora *PAY* kuti utange kubhadhara.",
        "send payment": "Tumira EcoCash confirmation SMS pano kana wapedza.",
        "certificate": "Ehe, unopihwa certificate kana wapedza kudzidza.",
        "imwe mari": "Kwete. Unobhadhara kamwe chete chete — hapana monthly fee.",
        "refund": "Hatina refund nekuti ma lessons anobva avhurwa ipapo ipapo.",
        "time": "Unodzidza paunoda, hapana nguva yakatarwa.",
        "duration": "Unogona kupedza nekukurumidza kana zvishoma nezvishoma — self paced."
    }

    for key in faq_map:
        if key in m:
            return faq_map[key]

    return None

def simple_ai_bypass(msg):

    m = msg.lower().strip()

    simple = {

        "hi": "Makadii 👋",
        "hello": "Makadii 👋",
        "thanks": "Makorokoto 👍",
        "thank you": "Makorokoto 👍",

        "price": "Basic $5 | Premium $10",
        "course price": "Basic $5 | Premium $10",

        "ecocash": "Pay to 0773208904",
        "payment": "Pay to 0773208904",

        "where can i sell":
        "Unogona kutengesa kuma shops, markets, schools, tuckshops nemuma locations.",

        "profit":
        "Profit inoenderana neproduction cost yako uye packaging."
    }

    return simple.get(m)

# ✅ MODIFIED (MODULE-AWARE AI)
def ai_trainer_reply(phone, question, allowed_modules=None):
    active_module = "general"

    if allowed_modules:
        active_module = allowed_modules[-1]

    memory_messages = get_memory(phone, active_module)

    memory_text = ""
    for m in memory_messages:
        memory_text += f"{m['role']}: {m['content']}\n"

    instructions = f"""
You are Arachis AI Trainer.

You help Zimbabwean students learn:
- detergent manufacturing
- drink manufacturing
- small business management

You explain things simply and professionally.

You must:
- give exact measurements
- explain production steps clearly
- explain causes of product failures
- help students calculate profit
- suggest selling prices in Zimbabwe
- explain where to sell products

When users ask in Shona, reply in proper Shona.

Always behave like a serious business mentor.

Never invent dangerous chemical procedures.

Always prioritize practical low-cost production suitable for Zimbabwe.

Use the Arachis Knowledge Base files first before giving an answer.

Recent conversation:
{memory_text}

Current student question:
{question}
"""

    try:
        response = openai_client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            instructions=instructions,
            input=question,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [
                        os.getenv("ARACHIS_VECTOR_STORE_ID")
                    ]
                }
        
            ]
        )

        answer = response.output_text.strip()

        save_memory(phone, active_module, "user", question)
        save_memory(phone, active_module, "assistant", answer)

        return answer

    except Exception as e:
        print("OPENAI AGENT ERROR:", e)
        return "Pane problem paAI trainer parizvino. Ndapota edzai zvakare kana taurai naAdmin."

def ai_analyze_product(image_path, student_details):

    import base64

    with open(image_path, "rb") as img:
        image_bytes = img.read()

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = f"""
You are a PROFESSIONAL detergent production trainer.

You must diagnose the product failure or appraise the good done and give EXACT rescue steps.

STUDENT DESCRIPTION:
{student_details}

RULES:

1. Use ONLY chemicals from the lesson formula but do not just retain the original formula, do further research.
2. Diagnose the MOST LIKELY cause and tell which stage was misdone or which product was misapplied.
3. Give STEP-BY-STEP rescue instructions.
4. Use exact measurements (grams, ml).
5. Include mixing time and waiting time.
6. Explain briefly WHY the failure happened  but do not just generalize the response even it means doing further research.
7. Then give prevention advice for next batch.
8. Use correct grammatical shona where applicable.
"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this product."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        max_completion_tokens=600,
        temperature=0.3
    )

    return response.choices[0].message.content

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
    DATABASE_POOL.putconn(conn)

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

def build_detergent_menu(phone):
    fresh_user = get_user(phone)
    detergent_list = DETERGENT_MODULES

    if fresh_user.get("package") == "basic":
        allowed = PACKAGES["basic"]["modules"]
        detergent_list = [m for m in DETERGENT_MODULES if m in allowed]

    elif fresh_user.get("package") == "custom":
        allowed = get_custom_modules(phone)
        detergent_list = [m for m in DETERGENT_MODULES if m in allowed]

    if not detergent_list:
        return "Hauna detergent lessons pa package yako."

    menu = "🧪 *DETERGENT LESSONS*\n\n"
    for i, module in enumerate(detergent_list, start=1):
        menu += f"{i}️⃣ {module.replace('_', ' ').title()}\n"

    menu += "\nReply with number\nType *NEXT* to come back here."
    return menu


def build_beverage_menu(phone):
    fresh_user = get_user(phone)
    beverages = BEVERAGE_MODULES

    if fresh_user.get("package") == "basic":
        allowed = PACKAGES["basic"]["modules"]
        beverages = [m for m in beverages if m in allowed]

    elif fresh_user.get("package") == "custom":
        allowed = get_custom_modules(phone)
        beverages = [m for m in beverages if m in allowed]

    if not beverages:
        return "Hauna beverage lessons pa package yako."

    menu = "🥤 *BEVERAGE LESSONS*\n\n"
    for i, module in enumerate(beverages, start=1):
        menu += f"{i}️⃣ {module.replace('_', ' ').title()}\n"

    menu += "\nReply with number\nType *NEXT* to come back here."
    return menu

def build_advanced_menu(phone):
    allowed = get_allowed_modules_for_user(phone)
    advanced = [m for m in ADVANCED_MODULES if m in allowed]

    if not advanced:
        return (
            "🔒 Advanced Manufacturing is locked.\n\n"
            "💵 Full Advanced Package: $20\n"
            "Upgrade prices:\n"
            "✔ Basic to Advanced: $10\n"
            "✔ Premium to Advanced: $7\n\n"
            "Nyora *UPGRADE* kuti uvhure."
        )

    menu = "🏭 *ADVANCED MANUFACTURING*\n\n"

    for i, module in enumerate(advanced, start=1):
        menu += f"{i}️⃣ {module.replace('_', ' ').title()}\n"

    menu += "\nReply with number\nType *NEXT* to come back here."
    return menu

def build_spices_menu(phone):
    allowed = get_allowed_modules_for_user(phone)
    spices = [m for m in SPICE_MODULES if m in allowed]

    if not spices:
        return (
            "🔒 Spices & Seasonings is locked.\n\n"
            "💵 Full Spices Package: $10\n"
            "Upgrade price:\n"
            "✔ Basic/Premium add Spices: $5\n\n"
            "Nyora *UPGRADE* kuti uvhure."
        )

    menu = "🌶️ *SPICES & SEASONINGS MANUFACTURING*\n\n"

    for i, module in enumerate(spices, start=1):
        menu += f"{i}️⃣ {module.replace('_', ' ').title()}\n"

    menu += "\nReply with number\nType *NEXT* to come back here."
    return menu

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
            DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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

    # =========================
    # DIRECT LESSON OPENING
    # =========================
    direct_module = find_direct_lesson_match(incoming)

    if direct_module:
        fresh_user = get_user(phone)

        if not fresh_user["is_paid"]:
            send_message(phone, "🔒 Lessons are for paid students only.\nNyora *PAY* kuti utange.")
            return jsonify({"status": "ok"})

        allowed_modules = get_allowed_modules_for_user(phone)

        if direct_module not in allowed_modules:
            send_message(phone, "🔒 This lesson is not unlocked on your current package.")
            return jsonify({"status": "ok"})

        if direct_module in DETERGENT_MODULES:
            set_state(phone, "detergents_menu")
        elif direct_module in BEVERAGE_MODULES:
            set_state(phone, "beverages_menu")
        elif direct_module in ADVANCED_MODULES:
            set_state(phone, "advanced_menu")
        elif direct_module in SPICE_MODULES:
            set_state(phone, "spices_menu")

        open_lesson_direct(phone, direct_module)
        return jsonify({"status": "ok"})

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
    # NEXT / BACK TO CURRENT LESSON MENU
    # =========================
    if incoming in ["next", "next lesson", "next lessons", "back", "lessons"]:

        if user["state"] == "detergents_menu":
            send_message(phone, build_detergent_menu(phone))
            return jsonify({"status": "ok"})

        elif user["state"] == "beverages_menu":
            send_message(phone, build_beverage_menu(phone))
            return jsonify({"status": "ok"})

        elif user["state"] == "advanced_menu":
            send_message(phone, build_advanced_menu(phone))
            return jsonify({"status": "ok"})

        else:
            set_state(phone, "course_lessons")
            send_message(
                phone,
                "📚 *COURSE LESSONS*\n\n"
                "Type one of these:\n\n"
                "🧪 *Detergents*\n"
                "🥤 *Beverages*\n"
                "🏭 *Advanced Manufacturing*\n"
                "*Spices & Seasonings*\n\n"
                "Or reply with number:\n"
                "1️⃣ Detergents\n"
                "2️⃣ Beverages\n"
                "3️⃣ 🏭 Advanced Manufacturing\n"
                "4️⃣ 🌶️ Spices & Seasonings\n\n"
            )
            return jsonify({"status": "ok"})

    # 🔥 HANDLE TEMPLATE REPLIES (FIXED)
    if incoming in ["yes", "ok", "sure", "interested", "view"]:

        set_state(phone, "pay_menu")

        send_message(
            phone,
            "🔥 Great!\n\n"
            "Choose your package:\n\n"
            "1️⃣ Basic – $5\n"
            "2️⃣ Premium – $10\n"
            "3️⃣ Custom – $2 per formula\n"
            "4️⃣ Advanced Manufacturing – $20\n"
            "5️⃣ Spices & Seasonings – $10\n\n"
            "Reply 1, 2 , 3 , 4 or 5"
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
        DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)
        send_message(phone, f"📊 *ADMIN DASHBOARD*\n\n👥 Users: {total}\n💰 Paid: {paid}")
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
            DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

        send_message(target, f"🎉 Payment Approved!\nPackage: {package.upper()}")
        send_message(phone, f"✅ Approved: {target} ({package})")

        return jsonify({"status": "ok"})

    if incoming in ["menu", "start", "makadini", "hie"]:

        conn = get_db()
        c = conn.cursor()

        c.execute("""
            SELECT total_messages 
            FROM student_metrics 
            WHERE phone=%s
        """, (phone,))

        row = c.fetchone()
        DATABASE_POOL.putconn(conn)

        # If user is new or has few messages → show sales message
        if not row or row[0] < 1:

            set_state(phone, "qualify")

            send_message(
                phone,
                "👋 Welcome to ARACHIS Training\n\n"
                "Nei uchida kudzidza kosi iyi:\n\n"
                "1️⃣ Ndinoda kutanga bhizinesi\n"
                "2️⃣ Ndinoda kugadzira zvekushandisa ini pachangu\n\n"
                "Reply with 1 or 2"
            )

            log_activity(phone, "open_menu", "welcome")

        else:

            set_state(phone, "main")
            send_message(phone, main_menu())

            log_activity(phone, "open_menu", "main")

        return jsonify({"status": "ok"})

    if incoming == "pay":

        set_state(phone, "pay_menu")

        send_message(
            phone,
            "💳 *SELECT PACKAGE*\n\n"
            "1️⃣ Basic – $5\n"
            "2️⃣ Premium – $10\n"
            "3️⃣ Custom – $2 per formula\n"
            "4️⃣ Advanced Manufacturing – $20\n"
            "5️⃣ Spices & Seasonings – $10\n\n"
            "Reply with 1, 2, 3 , 4 or 5"
        )

        return jsonify({"status": "ok"})

    if user["state"] == "main":

        if incoming == "1":

            fresh_user = get_user(phone)

            if not fresh_user["is_paid"]:
                send_message(phone, "🔒 Paid Members Only\nNyora PAY")
                return jsonify({"status": "ok"})

            set_state(phone, "course_lessons")

            send_message(
                phone,
                "📚 *COURSE LESSONS*\n\n"
                "1️⃣ Detergents\n"
                "2️⃣ Beverages\n"
                "3️⃣ 🏭 Advanced Manufacturing\n"
                "4️⃣ 🌶️ Spices & Seasonings\n\n"
                "Reply with number"
            )
            return jsonify({"status": "ok"})
        
        elif incoming == "2":

            fresh_user = get_user(phone)

            if not fresh_user["is_paid"]:
                send_message(phone, "🔒 Business lessons are for paid users.\nNyora *PAY*")
                return jsonify({"status": "ok"})

            set_state(phone, "business_lessons")

            menu = "💼 *BUSINESS LESSONS*\n\n"

            for i, key in enumerate(BUSINESS_MODULES, start=1):
                label = BUSINESS_MODULES[key][1]
                menu += f"{i}️⃣ {label}\n"

            menu += "\nNyora *MENU* kudzokera."

            send_message(phone, menu)
            return jsonify({"status": "ok"})
            
        elif incoming == "3":
            set_state(phone, "calc_menu")

            send_message(
                phone,
                "📊 *PRODUCTION COST CALCULATOR*\n\n"
                "Choose option:\n\n"
                "1️⃣ Detailed (Ingredients Step-By-Step)\n"
                "2️⃣ Quick (Fast Calculation)\n\n"
                "Reply with 1 or 2"
            )
            return jsonify({"status": "ok"})

        elif incoming == "5":
            set_state(phone, "marketplace_home")
            send_message(phone, build_marketplace_home(phone))
            return jsonify({"status": "ok"})

        elif incoming == "4":

            fresh_user = get_user(phone)

            if fresh_user.get("package") == "basic":
                set_state(phone, "upgrade_offer")

                send_message(
                    phone,
                    "🤖 *AI Trainer iri mu Premium chete*\n\n"
                    "Upgrade uone:\n"
                    "✔ Full AI help\n"
                    "✔ Product fixing\n"
                    "✔ Business advice\n\n"
                    "Pay only $5 more\n\n"
                    "1️⃣ Upgrade now\n"
                    "2️⃣ Later"
                )
                return jsonify({"status": "ok"})

            set_state(phone, "ai_chat")

            send_message(
                phone,
                "🤖 *AI TRAINER (PRODUCTION + BUSINESS)*\n\n"
                "Bvunza chero chinhu:\n\n"
                "✔ Kugadzira ma products\n"
                "✔ Kugadzirisa problem\n"
                "✔ Pricing & profit\n"
                "✔ Kuti utengese kupi\n"
                "✔ Kutanga bhizinesi\n\n"
                "Example:\n"
                "👉 Dishwash inotengeswa marii?\n"
                "👉 Ndotangira papi kutengesa?\n\n"
                "↩ Nyora MENU kudzokera."
            )

            return jsonify({"status": "ok"})

        elif incoming == "7":

            fresh_user = get_user(phone)

            if fresh_user.get("package") == "premium":
                send_message(
                    phone,
                    "✅ Uri pa *PREMIUM PLAN*\n\n"
                    "✔ All lessons unlocked\n"
                    "✔ AI Trainer\n"
                    "✔ Full business training"
                )
                return jsonify({"status": "ok"})

            set_state(phone, "upgrade_offer")

            send_message(
                phone,
                "🚀 *UPGRADE TO PREMIUM*\n\n"
                "Unlock everything:\n"
                "✔ All lessons\n"
                "✔ AI Trainer\n"
                "✔ Advanced business training\n\n"
                "💵 Pay only $5 more\n\n"
                "1️⃣ Upgrade now\n"
                "2️⃣ Back"
            )
            return jsonify({"status": "ok"})


        elif incoming == "8":

            set_state(phone, "help_menu")

            send_message(
                phone,
                "🆘 *HELP CENTER*\n\n"
                "1️⃣ How to pay\n"
                "2️⃣ How to use course\n"
                "3️⃣ Talk to admin\n\n"
                "Reply with number"
            )
            return jsonify({"status": "ok"})

        elif incoming == "9":

            conn = get_db()
            c = conn.cursor()

            # get user package
            c.execute("SELECT package FROM users WHERE phone=%s", (phone,))
            package_row = c.fetchone()
            package = package_row[0] if package_row else "none"

            # count lessons opened
            c.execute("""
                SELECT COUNT(*) FROM module_access
                WHERE phone=%s
            """, (phone,))
            lessons_done = c.fetchone()[0]

            DATABASE_POOL.putconn(conn)

            # get AI usage today
            ai_used = ai_questions_today(phone)

            custom_text = ""

            if package == "custom":
                selected = get_custom_modules(phone)
                custom_text = "\n🧩 *Your Custom Lessons:*\n"
                custom_text += "\n".join([f"✔ {m.replace('_',' ').title()}" for m in selected])
                custom_text += "\n"

            send_message(
                phone,
                "📊 *ACCOUNT DASHBOARD*\n\n"
                f"👤 Package: *{package.upper()}*\n\n"
                f"📚 Lessons Opened: {lessons_done}\n\n"
                f"{custom_text}\n\n"
                f"🤖 AI Questions Today: {ai_used}/10\n\n"
                "↩ Nyora MENU kudzokera"
            )

            return jsonify({"status": "ok"})
            
        elif incoming == "10":
            send_app_download(phone)
            return jsonify({"status": "ok"})
            
        elif incoming == "6":
            set_state(phone, "supplier_directory")
            send_message(
                phone,
                "🏭 *SUPPLIER DIRECTORY*\n\n"
                "1️⃣ Detergent Ingredients\n"
                "2️⃣ Drink Ingredients\n"
                "3️⃣ Containers & Bottles\n"
                "4️⃣ Ph Paper\n\n"
                "Reply with 1, 2 ,3 or 4.\n"
                "↩ Nyora *MENU* kudzokera."
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

        

    # =========================
    # QUALIFY STAGE
    # =========================
    if user["state"] == "qualify":

        if incoming == "1":
            set_state(phone, "pitch")

            send_message(phone,
                "🔥 Zvakanaka!\n\n"
                "Vanhu vakawanda vari kutotengesa:\n"
                "✔ Dishwash\n✔ Bleach\n✔ Drinks\n\n"
                "💵 Course: Basic $5 | Premium $10\n\n"
                "Reply YES to continue"
            )
            return jsonify({"status": "ok"})

        elif incoming == "2":
            set_state(phone, "pitch")

            send_message(phone,
                "👌 Uchadzidza kugadzira ma products.\n\n"
                "💵 Course: Basic $5 | Premium $10\n\n"
                "Reply YES to continue"
            )
            return jsonify({"status": "ok"})

        else:
            send_message(phone, "Sarudza 1 or 2")
            return jsonify({"status": "ok"})


    # =========================
    # PITCH STAGE
    # =========================
    if user["state"] == "pitch":

        if incoming in ["yes", "ok", "start"]:
            set_state(phone, "pay_menu")

            send_message(phone,
                "💳 SELECT PACKAGE\n\n"
                "1️⃣ Basic – $5\n"
                "2️⃣ Premium – $10\n"
                "3️⃣ Custom – $2 per formula\n"
                "4️⃣ Advanced Manufacturing – $20\n"
                "5️⃣ Spices & Seasonings – $10\n\n"
            )
            return jsonify({"status": "ok"})

        else:
            send_message(phone, "Reply YES")
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

            ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)

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
        DATABASE_POOL.putconn(conn)

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

            ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)

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
        DATABASE_POOL.putconn(conn)

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
            ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)
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
        DATABASE_POOL.putconn(conn)

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
            ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)
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

    if incoming == "upgrade":

        user = get_user(phone)
        package = user.get("package")

        if package == "basic":
            set_state(phone, "upgrade_select")
            send_message(
                phone,
                "🚀 *UPGRADE OPTIONS*\n\n"
                "1️⃣ Upgrade to Premium – $5\n"
                "2️⃣ Add Spices – $5\n"
                "3️⃣ Upgrade to Advanced – $10\n\n"
                "Reply 1, 2 or 3"
            )
            return jsonify({"status": "ok"})

        elif package == "premium":
            set_state(phone, "upgrade_select")
            send_message(
                phone,
                "🚀 *UPGRADE OPTIONS*\n\n"
                "1️⃣ Add Spices – $5\n"
                "2️⃣ Upgrade to Advanced – $7\n\n"
                "Reply 1 or 2"
            )
            return jsonify({"status": "ok"})

        else:
            send_message(phone, "No upgrade option available for your current package.")
            return jsonify({"status": "ok"})

    elif user["state"] == "upgrade_select":

        package = user.get("package")

        if package == "basic":

            if incoming == "1":
                pending = "upgrade_basic_to_premium"
                amount = 5
                title = "BASIC TO PREMIUM UPGRADE"

            elif incoming == "2":
                pending = "upgrade_basic_to_spices"
                amount = 5
                title = "ADD SPICES"

            elif incoming == "3":
                pending = "upgrade_basic_to_advanced"
                amount = 10
                title = "BASIC TO ADVANCED UPGRADE"

            else:
                send_message(phone, "Sarudza 1, 2 or 3")
                return jsonify({"status": "ok"})

        elif package == "premium":

            if incoming == "1":
                pending = "upgrade_premium_to_spices"
                amount = 5
                title = "ADD SPICES"

            elif incoming == "2":
                pending = "upgrade_premium_to_advanced"
                amount = 7
                title = "PREMIUM TO ADVANCED UPGRADE"

            else:
                send_message(phone, "Sarudza 1 or 2")
                return jsonify({"status": "ok"})

        else:
            send_message(phone, "Upgrade not available.")
            return jsonify({"status": "ok"})

        conn = get_db()
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET pending_purchase=%s
            WHERE phone=%s
        """, (pending, phone))

        conn.commit()
        DATABASE_POOL.putconn(conn)

        set_state(phone, "awaiting_payment")

        send_message(
            phone,
            f"📲 *{title}*\n\n"
            f"*153*1*1*0773208904*{amount}#\n\n"
            "👤 Recipient: Beloved Nkomo\n"
            f"💵 Amount: ${amount} + charges\n\n"
            "Send confirmation SMS here."
        )

        return jsonify({"status": "ok"})

    elif user["state"] == "pay_menu":

        if incoming == "1":
            selected_package = "basic"
            price = BASIC_PRICE

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE users SET package=%s WHERE phone=%s",
                (selected_package, phone)
            )
            conn.commit()
            DATABASE_POOL.putconn(conn)

            set_state(phone, "awaiting_payment")

            send_message(
                phone,
                "📲 *Bhadhara neEcoCash*\n\n"
                "*153*1*1*0773208904*5#\n\n"
                "👤 Recipient: Beloved Nkomo\n"
                f"💵 Amount: ${price} + charges\n\n"
                "Send confirmation SMS here"
            )
            return jsonify({"status": "ok"})

        elif incoming == "2":
            selected_package = "premium"
            price = PREMIUM_PRICE

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE users SET package=%s WHERE phone=%s",
                (selected_package, phone)
            )
            conn.commit()
            DATABASE_POOL.putconn(conn)

            set_state(phone, "awaiting_payment")

            send_message(
                phone,
                "📲 *Bhadhara neEcoCash*\n\n"
                "*153*1*1*0773208904*10#\n\n"
                "👤 Recipient: Beloved Nkomo\n"
                f"💵 Amount: ${price} + charges\n\n"
                "Send confirmation SMS here"
            )
            return jsonify({"status": "ok"})

        elif incoming == "3":
            clear_custom_modules(phone)
            set_state(phone, "custom_selecting")

            all_modules = DETERGENT_MODULES + BEVERAGE_MODULES

            menu = "🧩 *CUSTOM PACKAGE*\n\n"
            menu += "Sarudza ma Formula Aunoda kudzidza.\n"
            menu += f"Price: ${CUSTOM_PRICE_PER_MODULE} per formula\n\n"

            for i, module in enumerate(all_modules, start=1):
                name = module.replace("_", " ").title()
                menu += f"{i}️⃣ {name}\n"

            menu += "\nReply with numbers separated by comma.\n"
            menu += "Example: 1,3,7\n\n"
            menu += "Type *DONE* when finished."

            send_message(phone, menu)
            return jsonify({"status": "ok"})

        elif incoming == "4":
            conn = get_db()
            c = conn.cursor()

            c.execute("""
                UPDATE users
                SET pending_purchase='advanced_full'
                WHERE phone=%s
            """, (phone,))

            conn.commit()
            DATABASE_POOL.putconn(conn)

            set_state(phone, "awaiting_payment")

            send_message(
                phone,
                "📲 *ADVANCED FULL PACKAGE PAYMENT*\n\n"
                "*153*1*1*0773208904*20#\n\n"
                "👤 Recipient: Beloved Nkomo\n"
                "💵 Amount: $20 + charges\n\n"
                "Send confirmation SMS here"
            )

            return jsonify({"status": "ok"})

        elif incoming == "5":
            conn = get_db()
            c = conn.cursor()

            c.execute("""
                UPDATE users
                SET pending_purchase='spices_full'
                WHERE phone=%s
            """, (phone,))

            conn.commit()
            DATABASE_POOL.putconn(conn)

            set_state(phone, "awaiting_payment")

            send_message(
                phone,
                "📲 *SPICES & SEASONINGS PAYMENT*\n\n"
                "*153*1*1*0773208904*10#\n\n"
                "👤 Recipient: Beloved Nkomo\n"
                "💵 Amount: $10 + charges\n\n"
                "Send confirmation SMS here"
            )

            return jsonify({"status": "ok"})

        else:
            send_message(phone, "Sarudza 1, 2, 3 , 4 or 5")
            return jsonify({"status": "ok"})

    elif user["state"] == "custom_selecting":

        all_modules = DETERGENT_MODULES + BEVERAGE_MODULES

        if incoming == "done":
            selected = get_custom_modules(phone)

            if not selected:
                send_message(phone, "Hausati wasarudza formula. Reply numbers like 1,3,7")
                return jsonify({"status": "ok"})

            total = len(selected) * CUSTOM_PRICE_PER_MODULE

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE users SET package='custom' WHERE phone=%s",
                (phone,)
            )
            conn.commit()
            DATABASE_POOL.putconn(conn)

            set_state(phone, "awaiting_payment")

            selected_names = "\n".join(
                [f"✔ {m.replace('_',' ').title()}" for m in selected]
            )

            send_message(
                phone,
                "🧩 *CUSTOM PACKAGE SUMMARY*\n\n"
                f"{selected_names}\n\n"
                f"Total formulas: {len(selected)}\n"
                f"Amount to pay: ${total:.2f}\n\n"
                "📲 *Bhadhara neEcoCash*\n\n"
                f"*153*1*1*0773208904*{total:.2f}#\n\n"
                "👤 Recipient: Beloved Nkomo\n"
                "Send confirmation SMS here after payment."
            )
            return jsonify({"status": "ok"})

        try:
            numbers = incoming.replace(" ", "").split(",")

            added = []

            for n in numbers:
                if not n.isdigit():
                    continue

                index = int(n) - 1

                if 0 <= index < len(all_modules):
                    module = all_modules[index]
                    add_custom_module(phone, module)
                    added.append(module.replace("_", " ").title())

            if not added:
                send_message(phone, "Invalid selection. Example: 1,3,7")
                return jsonify({"status": "ok"})

            selected = get_custom_modules(phone)

            send_message(
                phone,
                "✅ Added:\n"
                + "\n".join([f"✔ {a}" for a in added])
                + f"\n\nTotal selected: {len(selected)}"
                + f"\nCurrent amount: ${len(selected) * CUSTOM_PRICE_PER_MODULE:.2f}"
                + "\n\nAdd more numbers or type *DONE*."
            )

            return jsonify({"status": "ok"})

        except Exception as e:
            print("CUSTOM SELECT ERROR:", e)
            send_message(phone, "Invalid format. Example: 1,3,7")
            return jsonify({"status": "ok"})

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

    elif user["state"] == "supplier_directory":

        if incoming == "1":
            send_message(
                phone,
                "🧪 *DETERGENT INGREDIENT SUPPLIERS*\n\n"
                "1. Grace Rita Plastics\n"
                "📞 +263775641533\n"
                "📍 Harare\n\n"
                "2. Tamayi Chemicals\n"
                "📞 +27655521810\n"
                "📍 South Africa\n\n"
                "3. Nastovert Chemicals\n"
                "📞 +263774692352\n"
                "📍 Harare\n\n"
                "4. MazChem\n"
                "📞 +263772597141\n"
                "📍 Harare\n\n"
                "5. ArrowChem\n"
                "📞 +263780381618\n"
                "📍 Bulawayo / Gweru\n\n"
                "↩ Nyora *MENU* kudzokera."
            )
            return jsonify({"status": "ok"})

        elif incoming == "2":
            send_message(
                phone,
                "🥤 *DRINK INGREDIENT SUPPLIERS*\n\n"
                "1. Codchem Chemicals\n"
                "📞 +263772866766\n"
                "📍 Harare\n\n"
                "2. Acol Chemicals\n"
                "📞 +263778730915\n"
                "📍 Bulawayo / Harare\n\n"
                "↩ Nyora *MENU* kudzokera."
            )
            return jsonify({"status": "ok"})

        elif incoming == "3":
            send_message(
                phone,
                "🧴 *CONTAINER & BOTTLE SUPPLIERS*\n\n"
                "1. Grace Rita Plastics\n"
                "📞 +263775641533\n"
                "📍 Harare\n\n"
                "2. BriPak Packaging\n"
                "📞 +263783213322\n"
                "📍 Harare\n\n"
                "3. TekPak Plastics\n"
                "📞 +263775142283\n"
                "📍 Harare\n\n"
                "↩ Nyora *MENU* kudzokera."
            )
            return jsonify({"status": "ok"})

        elif incoming == "4":
            send_message(
                phone,
                "🧴 *PH PAPER*\n\n"
                "1. Reditek Chemicals\n"
                "📞 +263773903806\n"
                "📍 Bulawayo\n\n"
                "2. Graniteside Chemicals\n"
                "📞 +263774547609\n"
                "📍 Harare\n\n"
                "3. Mega Mark Scientific\n"
                "📞 +263771263978\n"
                "📍 Bulawayo\n\n"
                "↩ Nyora *MENU* kudzokera."
            )
            return jsonify({"status": "ok"})

    elif user["state"] == "business_lessons":

        modules = list(BUSINESS_MODULES.keys())

        if not incoming.isdigit():

            allowed_modules = get_user_modules(phone, incoming)
            ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)

            send_message(phone, ai_answer)

            ai_handled = True

            log_activity(phone, "ai_question", incoming)
            update_metrics(phone, "ai")

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
            DATABASE_POOL.putconn(conn)

            return jsonify({"status": "ok"})

        else:
            send_message(phone, "Invalid choice")
            return jsonify({"status": "ok"})

    elif user["state"] == "ai_chat":

        if incoming == "menu":
            set_state(phone, "main")
            send_message(phone, main_menu())
            return jsonify({"status": "ok"})

        allowed_modules = get_user_modules(phone, incoming)
        ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)

        send_message(phone, ai_answer)

        ai_handled = True

        log_activity(phone, "ai_question", incoming)
        update_metrics(phone, "ai")

        return jsonify({"status": "ok"})

    elif user["state"] == "photo_details":

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT item FROM temp_orders WHERE phone=%s", (phone,))
        row = c.fetchone()

        DATABASE_POOL.putconn(conn)

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

        if incoming == "yes":
            set_state(phone, "offline_name")
            send_message(phone, "✍🏽 Please enter your *FULL NAME*")
            return jsonify({"status": "ok"})


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
        DATABASE_POOL.putconn(conn)

        set_state(phone, "offline_location")
        send_message(phone, "📍 Enter your *Town / Area*")
        return jsonify({"status": "ok"})


    elif user["state"] == "offline_location":

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE offline_registrations
            SET location = %s
            WHERE phone = %s
        """, (incoming.title(), phone))
        conn.commit()
        DATABASE_POOL.putconn(conn)

        set_state(phone, "offline_choice")
        send_message(
            phone,
            "🧪 Choose detergent for your *FREE 10L ingredients*:\n"
            "Dishwash / Thick Bleach / Foam Bath / Pine Gel"
        )
        return jsonify({"status": "ok"})


    elif user["state"] == "offline_choice":

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE offline_registrations
            SET detergent_choice = %s
            WHERE phone = %s
        """, (incoming.title(), phone))
        conn.commit()
        DATABASE_POOL.putconn(conn)

        set_state(phone, "main")
        send_message(
            phone,
            "✅ Registration received!\n\n"
            "💳 Pay *$50* to Ecocash 0773 208904\n"
            "Send proof here.\n\n"
            "We will confirm your seat after approval."
        )
        return jsonify({"status": "ok"})

    elif user["state"] == "upgrade_offer":

        if incoming == "1":
            set_state(phone, "awaiting_upgrade_payment")

            send_message(
                phone,
                "📲 *UPGRADE PAYMENT*\n\n"
                "Pay ONLY difference: *$5*\n\n"
                "*153*1*1*0773208904*6#\n\n"
                "Send EcoCash confirmation SMS here."
            )
            return jsonify({"status": "ok"})

        elif incoming == "2":
            set_state(phone, "course_lessons")
            send_message(phone, "📚 Dzokera kuma lessons.")
            return jsonify({"status": "ok"}) 

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
            DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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

        DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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

        DATABASE_POOL.putconn(conn)

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
            DATABASE_POOL.putconn(conn)

            send_message(phone, "🎉 Upgrade successful! Wava pa Premium.")
            set_state(phone, "main")
            send_message(phone, main_menu())

            return jsonify({"status": "ok"})
        else:
            send_message(phone, reply)
            return jsonify({"status": "ok"})

# =========================
# UNPAID USER PROTECTION
# =========================
    if not user["is_paid"]:

        faq = faq_engine(incoming)

        if faq:
            send_message(phone, faq)
            return jsonify({"status": "ok"})

        if incoming not in ["menu","start","pay","1","2","3","4","5","6","7","8","9","10","app","apk","download app","download apk","android app"]:
            send_message(
                phone,
                "📚 AI trainer & ma formula anovhurwa kune vakabhadhara chete.\nNyora *PAY* kuti utange."
            )
            return jsonify({"status":"ok"}) 
    blocked_commands = ["1","2","3","4","5","6","menu","start","pay","admin","hie","makadini"]
    
    if not incoming.isdigit() and user["is_paid"] and not ai_handled:
        simple_reply = simple_ai_bypass(incoming)

        if simple_reply:
            send_message(phone, simple_reply)
            return jsonify({"status":"ok"})
               
        package = user.get("package","basic")

        limit = 5

        if package == "premium":
            limit = 10

        today_count = ai_questions_today(phone)

        if today_count >= limit:

            send_message(
                phone,
                f"⛔ Wapedza AI limit yako ye nhasi ({limit})."
            )

            return jsonify({"status":"ok"})

        allowed_modules = get_user_modules(phone, incoming)

        if not allowed_modules:

            # Allow business questions even without module
            business_keywords = ["profit", "price", "sell", "business", "market"]

            if any(k in incoming.lower() for k in business_keywords):
                combined_text = ""
            else:
                send_message(
                      phone,
                      "Ndapota vhura module kutanga kuti ndikubatsire zvakarurama."
                )

                return jsonify({"status":"ok"})

        # If user has 2 or more modules → allow full cross-module AI
        if len(allowed_modules) >= 2:
            # multi-module question → no memory
            memory_messages = []
            ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)
            log_activity(phone, "ai_question", incoming)
            update_metrics(phone, "ai")   # ← ADD THIS LINE
            log_activity(phone, "ai_answer", ai_answer[:500])
            
            send_message(phone, ai_answer)
            return jsonify({"status": "ok"})

        # If user has only 1 module → still allow AI but only that module
        ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)
        log_activity(phone, "ai_question", incoming)
        send_message(phone, ai_answer)
        update_metrics(phone, "ai")
        log_activity(phone, "ai_answer", ai_answer[:500])
        return jsonify({"status": "ok"})

    # ===== DEFAULT FALLBACK =====
    send_message(phone, "Nyora *MENU*")
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
            DATABASE_POOL.putconn(conn)

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


    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

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
    DATABASE_POOL.putconn(conn)

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

    DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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
            DATABASE_POOL.putconn(conn)
            return jsonify({
                "success": False,
                "message": "Number not found. Please contact admin."
            }), 404

        db_phone, is_paid, package, saved_device_id, saved_device_model, device_locked_at = user

        if not is_paid:
            DATABASE_POOL.putconn(conn)
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
                    DATABASE_POOL.putconn(conn)

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

        DATABASE_POOL.putconn(conn)

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
        DATABASE_POOL.putconn(conn)

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

































































































































































































































































