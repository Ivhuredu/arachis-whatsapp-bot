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

COURSE_PRICE = 5.0
PAYMENT_TOLERANCE = 1.5   # allows EcoCash charges
MIN_ACCEPTABLE = COURSE_PRICE
MAX_ACCEPTABLE = COURSE_PRICE + PAYMENT_TOLERANCE

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

UPLOAD_FOLDER = "static/lessons"
ALLOWED_EXTENSIONS = {"pdf"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    
    
    conn.commit()
    DATABASE_POOL.putconn(conn)


# =========================
# HELPERS
# =========================
def normalize_phone(phone):
    return phone if phone.startswith("+") else "+" + phone
    
def send_message(phone, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+", ""),
        "type": "text",
        "text": {"body": text}
    }

    response = requests.post(url, headers=headers, json=payload)

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

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


def send_pdf(phone, pdf_url, caption):
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

    response = requests.post(url, headers=headers, json=payload)
    print(response.text)

def send_voice(phone, audio_url):

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

    response = requests.post(url, headers=headers, json=payload)

    print("VOICE STATUS:", response.status_code)
    print("VOICE RESPONSE:", response.text)

import time

def send_audio_series(phone, module):

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

def send_template(phone, reactivate_training):

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+",""),
        "type": "template",
        "template": {
            "name": reactivate_training,
            "language": {"code": "en"}
        }
    }

    r = requests.post(url, headers=headers, json=payload)

    print("TEMPLATE STATUS:", r.status_code)
    print("TEMPLATE RESPONSE:", r.text)

def get_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone, state, payment_status, is_paid FROM users WHERE phone=%s", (phone,))
    row = c.fetchone()
    DATABASE_POOL.putconn(conn)

    if not row:
        return None

    return {
        "phone": row[0],
        "state": row[1],
        "payment_status": row[2],
        "is_paid": row[3]
    }

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
        
def log_activity(phone, action, details=""):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO activity_log (phone, action, details)
        VALUES (%s, %s, %s)
    """, (phone, action, details))
    conn.commit()
    DATABASE_POOL.putconn(conn)

import re

def extract_ecocash_details(text):

    text = text.replace(",", "")

    amount_match = re.search(r"\$?(\d+(\.\d{1,2})?)", text)
    ref_match = re.search(r"(reference|ref|code)[:\s]*([A-Za-z0-9]{5,})", text, re.I)
    phone_match = re.search(r"07\d{8}", text)

    amount = float(amount_match.group(1)) if amount_match else None
    reference = ref_match.group(2) if ref_match else None
    sender = phone_match.group(0) if phone_match else None

    return amount, reference, sender

def verify_and_apply_payment(phone, message):

    amount, reference, sender = extract_ecocash_details(message)

    if not reference:
        return False, "Handina kuona reference number mu message."

    conn = get_db()
    c = conn.cursor()

    # prevent reuse
    c.execute("SELECT 1 FROM payments WHERE reference=%s", (reference,))
    if c.fetchone():
        DATABASE_POOL.putconn(conn)
        return False, "Reference yakamboshandiswa kare."
        
    ecocash_keywords = ["ecocash", "transfer", "paid", "you have received", "transaction", "cash out"]
    if not any(k in message.lower() for k in ecocash_keywords):
        return False, "Tumira EcoCash confirmation SMS chaiyo."

    if not amount:
        DATABASE_POOL.putconn(conn)
        return False, "Handina kuona mari yatumirwa muSMS."

    if amount < MIN_ACCEPTABLE:
        DATABASE_POOL.putconn(conn)
        return False, f"Mari ishoma. Course iri ${COURSE_PRICE}."

    if amount > MAX_ACCEPTABLE:
        DATABASE_POOL.putconn(conn)
        return False, f"Mari yakawandisa zvisina kujairika (${amount}). Bata admin."

    # save payment
    c.execute("""
        INSERT INTO payments (phone, reference, amount, raw_text)
        VALUES (%s,%s,%s,%s)
    """, (phone, reference, amount, message))

    conn.commit()
    DATABASE_POOL.putconn(conn)

    # APPROVE USER
    mark_paid(phone)

    send_admin_alert(
        "AUTO PAYMENT APPROVED",
        f"Phone: {phone}\nPaid: ${amount}\nCourse Price: ${COURSE_PRICE}\nRef: {reference}"
    )

    return True, "🎉 Payment confirmed automatically!\nWava kukwanisa kuvhura ma lessons ese."

# =========================
# AI MEMORY SYSTEM
# =========================

MAX_MEMORY_MESSAGES = 12   # last 6 exchanges

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

    text = text[:120000]

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

    # split lesson into chunks
    chunks = lesson.split("\n")

    question_words = question.lower().split()

    best_chunk = ""
    best_score = 0

    for chunk in chunks:

        text = chunk.lower()

        score = sum(1 for w in question_words if w in text)

        if score > best_score:
            best_score = score
            best_chunk = chunk

    if best_chunk:
        return best_chunk

    return lesson[:1000]  # fallback

    
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
STORE_PACKS = {

    "dishwash": {
        "starter": {
            "name": "Dishwash Starter Pack (20L)",
            "price": "$14",
            "items": [
                "SLES 1.5kg",
                "Sulphonic Acid 1L",
                "Caustic Soda 300g",
                "Salt 500g",
                "Bermacol 100g",
                "Dye 20g",
                "Perfume 30ml"
            ]
        },
        "medium": {
            "name": "Dishwash Medium Pack (40L)",
            "price": "$27.5",
            "items": [
                "SLES 3kg",
                "Sulphonic Acid 2L",
                "Caustic Soda 600g",
                "Salt 1kg",
                "Bermacol 200g",
                "Dye 40g",
                "Perfume 60ml"
            ]
        },
        "bulk": {
            "name": "Dishwash Bulk Business Pack (100L)",
            "price": "$65",
            "items": [
                "SLES 7kg",
                "Sulphonic Acid 5L",
                "Caustic Soda 1.5kg",
                "Salt 3kg",
                "Bermacol 500g",
                "Dye 100g",
                "Perfume 150ml"
            ]
        }
    },

    "bleach": {
        "starter": {
            "name": "Thick Bleach Starter (20L)",
            "price": "$15",
            "items": [
                "SLES 2kg",
                "Hypochlorite 3L",
                "Caustic Soda 300g"
            ]
        },
        "medium": {
            "name": "Thick Bleach Medium (40L)",
            "price": "$29.5",
            "items": [
                "SLES 4kg",
                "Hypochlorite 6L",
                "Caustic Soda 600g"
            ]
        },
        "bulk": {
            "name": "Thick Bleach Bulk (100L)",
            "price": "$55",
            "items": [
                "SLES 10kg",
                "Hypochlorite 15L",
                "Caustic Soda 1.5kg"
            ]
        }
    },

    "orange_drink": {
        "starter": {
            "name": "Orange Concentrate Starter (10L)",
            "price": "$20",
            "items": [
                "Sugar 8kg",
                "Orange Flavour 100ml",
                "Citric Acid 50g",
                "Sodium Benzoate 20g",
                "Colour"
            ]
        },
        "medium": {
            "name": "Orange Concentrate Medium (20L)",
            "price": "$35",
            "items": [
                "Sugar 16kg",
                "Orange Flavour 200ml",
                "Citric Acid 100g",
                "Sodium Benzoate 40g",
                "Colour"
            ]
        },
        "bulk": {
            "name": "Orange Concentrate Bulk (50L)",
            "price": "$80",
            "items": [
                "Sugar 40kg",
                "Orange Flavour 500ml",
                "Citric Acid 250g",
                "Sodium Benzoate 100g",
                "Colour"
            ]
        }
    }
}
DELIVERY_FEES = {
    "mataga": 7,
    "mberengwa": 7,
    "gweru": 5,
    "bulawayo": 7,
    "harare": 3
}

DEFAULT_DELIVERY_FEE = 7  # if town not listed



# =========================
# MENUS
# =========================
def main_menu():
    return (
        "👋 *TINOKUGAMUCHIRAI KU ARACHIS ONLINE TRAINING*\n\n"
        "1️⃣ Course Lessons\n"
        "2️⃣ 🧼 Laundry Bar Training (NEW)\n"
        "3️⃣ 📊 Production Cost Calculator\n"
        "4️⃣ Join Full Online Training\n"
        "5️⃣ Register for Offline Classes\n"
        "6️⃣ Online Store (Chemicals)\n"
        "7️⃣ 🤖 Ask AI Trainer\n"
        "8️⃣ Supplier Directory"
    )
    
def free_lesson():
    return (
        "🎁 *FREE LESSON*\n\n"
        "Dishwash basics:\n"
        "✔ SLES\n✔ Salt\n✔ Dye\n✔ Perfume\n✔ Mvura\n\n"
        "⚠ Pfeka magloves, mask ne apron.\n\n"
        "↩ Nyora *MENU* kudzokera kumusoro."
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
        "📚 Full training: $5 once-off kuti udzidze ma formula ese, pari zvino anosvika 30\n\n"
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
        "course yacho inoita marii": f"Course irikungori ${COURSE_PRICE} once-off.",
        "marii": f"Full course: ${COURSE_PRICE} once-off.",
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

# ✅ MODIFIED (MODULE-AWARE AI)
def ai_trainer_reply(phone, question, allowed_modules):

    pdf_text_blocks = []

    for module in allowed_modules:

        chunk = get_relevant_lesson_chunk(module, question)

        if chunk:
            pdf_text_blocks.append(chunk)

    combined_text = "\n\n".join(pdf_text_blocks)
    if not combined_text.strip():
        return "Ndapota vhura module rine chidzidzo ichi kutanga kuti ndikubatsire zvakarurama."
        
    # Limit lesson content size to prevent token overload
    combined_text = combined_text.rsplit(".", 1)[0]

    # determine active module (latest opened)
    active_module = allowed_modules[-1]

    memory_messages = get_memory(phone, active_module)

    
    prompt = f"""
    You are an INDUSTRIAL PRACTICAL TRAINER teaching a paid student.
    You MUST STRICTLY follow the lesson material below.
    You are NOT allowed to introduce chemicals, methods, or formulas not present in the lesson.

    LESSON MATERIAL:
    ----------------
    {combined_text}
    ----------------

    RULES (VERY IMPORTANT):

    1) If a chemical is not in the lesson → DO NOT mention it.
    2) If the student asks something outside lesson → explain using closest concept FROM lesson only.
    3) If fixing a product → give rescue steps FIRST using only lesson chemicals.
    4) Always give exact measurable actions:
       - teaspoons
       - grams
       - ml
       - mixing time
       - waiting time
    5) Never give vague advice like "adjust slowly" — be specific.
    6) After fixing, give prevention advice for next batch.
    7) Speak like a hands-on trainer guiding someone next to you.
    8) No theory unless student asks WHY,use only correct grammatical shona.

    STUDENT QUESTION:
    {question}
    """   

    messages = [
    {"role": "system", "content": prompt}
    ]

    messages.extend(memory_messages)
    messages.append({"role": "user", "content": question})

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=600,
        temperature=0.5
    )

    answer = response.choices[0].message.content.strip()

    # save conversation
    save_memory(phone, active_module, "user", question)
    save_memory(phone, active_module, "assistant", answer)

    return answer

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
        max_tokens=600,
        temperature=0.3
    )

    return response.choices[0].message.content
    
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

        "low cost orange": "low_cost_orange_syrup",
        "orange syrup": "low_cost_orange_syrup",

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

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = normalize_phone(message["from"])

        msg_type = message["type"]

        if msg_type == "text":
            incoming = message["text"]["body"].strip().lower()
        else:
            incoming = ""

        update_metrics(phone, "message")
        log_activity(phone, "incoming_message", msg_type)

    except Exception:
        return "OK", 200

    create_user(phone)
    user = get_user(phone)
    if not user:
        return "OK", 200

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

    if incoming.startswith("approve ") and phone in ADMIN_NUMBERS:
        target = normalize_phone(incoming.replace("approve ", ""))
        log_activity(target, "payment_approved", "admin")
        mark_paid(target)
        send_message(target, "🎉 Payment Approved!\nYou now have full access.")
        send_message(phone, f"✅ Approved: {target}")
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

            set_state(phone, "main")
            send_message(phone, welcome_message())

            log_activity(phone, "open_menu", "welcome")

        else:

            set_state(phone, "main")
            send_message(phone, main_menu())

            log_activity(phone, "open_menu", "main")

        return jsonify({"status": "ok"})
    
    if incoming == "pay":
        set_state(phone, "pay_menu")

        send_admin_alert(
            "Customer opened payment menu",
            f"Phone: {phone}\nStage: Payment interest"
        )

        send_message(
           phone,
           "💳 *PAYMENT METHOD*\n\n"
           "1️⃣ EcoCash\n"
           "2️⃣ Cancel\n\n"
           "Reply with 1 or 2"
        )
        return jsonify({"status": "ok"})

    if user["state"] == "main":

        if incoming == "1":

            fresh_user = get_user(phone)

            if not fresh_user["is_paid"]:
                send_message(phone, "🔒 *Paid Members Only*\nNyora *PAY*")
                log_activity(phone, "blocked_access", "course_lessons")
                return jsonify({"status": "ok"})

            set_state(phone, "course_lessons")

            modules = load_lessons()

            menu = "📚 *COURSE LESSONS*\n\n"

            for i, key in enumerate(modules, start=1):
                label = modules[key][1]
                menu += f"{i}️⃣ {label}\n"

            menu += "\nNyora *MENU* kudzokera."

            send_message(phone, menu)
            return jsonify({"status": "ok"})

        
        elif incoming == "2":

            set_state(phone, "laundry_course_menu")

            send_message(
                phone,
                "🧼 *LAUNDRY BAR TRAINING*\n\n"
                "Learn how to make:\n"
                "✔ Premium bar\n"
                "✔ Budget bar\n"
                "✔ Ultra cheap bar\n\n"
                "Choose lesson:\n\n"
                "1️⃣ Day 1: Basics (FREE)\n"
                "2️⃣ Day 2: Safety 🔒\n"
                "3️⃣ Day 3: Premium Bar 🔒\n"
                "4️⃣ Day 4: Budget Bars 🔒\n"
                "5️⃣ Day 5: Ultra Cheap + Business 🔒\n"
                "Reply with number.\n"
                "↩ Nyora *MENU* kudzokera."
            )

            return jsonify({"status": "ok"})

        elif incoming == "3":
            set_state(phone, "calc_menu")

            send_message(
                phone,
                "📊 *PRODUCTION COST CALCULATOR*\n\n"
                "Choose option:\n\n"
                "1️⃣ Detailed (ingredients step-by-step)\n"
                "2️⃣ Quick (fast calculation)\n\n"
                "Reply with 1 or 2"
            )
            return jsonify({"status": "ok"})

        elif incoming == "4":
            send_message(phone, "📝 Join full online training — Nyora *PAY*")
            return jsonify({"status": "ok"})

        elif incoming == "5":
            set_state(phone, "offline_intro")
            send_message(
                 phone,
                 "🧑🏽‍🏫 *ARACHIS OFFLINE PRACTICAL TRAINING*\n\n"
                 "✔ 3 days in-person training\n"
                 "✔ Videos + hands-on practicals\n"
                 "✔ Ingredients to make 10L detergent\n"
                 "✔ Certificate included\n\n"
                 "💵 Fee: $50\n\n"
                 "Reply *YES* to register\n"
                  "Reply *MENU* to cancel"
            )
            return jsonify({"status": "ok"})

        elif incoming == "6":
            set_state(phone, "store_category")
            send_message(
                phone,
                "🛒 *ARACHIS PRODUCTION STORE*\n\n"
                "1️⃣ Dishwash Packs\n"
                "2️⃣ Thick Bleach Packs\n"
                "3️⃣ Orange Drink Packs\n\n"
                "Reply with number."
            )
            return jsonify({"status": "ok"})

        elif incoming == "7":

            set_state(phone, "ai_chat")

            send_message(
                phone,
                "🤖 *AI TRAINER*\n\n"
                "Unogona:\n"
                "✔ Kubvunza mubvunzo\n"
                "✔ Kutumira photo ye product yako\n\n"
                "Example questions:\n"
                "• Thick Bleach yangu yakoresa ndoita sei?\n"
                "• Dishwash yangu haisi kupupuma?\n\n"
                "📷 Kana product yakanganisika tumira *PHOTO*.\n\n"
                "↩ Nyora *MENU* kudzokera."
            )

            return jsonify({"status": "ok"})

        elif incoming == "8":
            set_state(phone, "supplier_directory")
            send_message(
                phone,
                "🏭 *SUPPLIER DIRECTORY*\n\n"
                "1️⃣ Detergent Ingredients\n"
                "2️⃣ Drink Ingredients\n"
                "3️⃣ Containers & Bottles\n\n"
                "Reply with 1, 2 or 3.\n"
                "↩ Nyora *MENU* kudzokera."
            )
            return jsonify({"status": "ok"})

    elif user["state"] == "course_lessons":

        fresh_user = get_user(phone)

        if not fresh_user["is_paid"]:
            send_message(phone, "🔒 *Paid Members Only*\nNyora *PAY*")
            return jsonify({"status": "ok"})

        modules = load_lessons()
        module_keys = list(modules.keys())

        if not incoming.isdigit():

            allowed_modules = get_user_modules(phone, incoming)

            if allowed_modules:
                ai_answer = ai_trainer_reply(phone, incoming, allowed_modules)

                send_message(phone, ai_answer)

                log_activity(phone, "ai_question", incoming)
                update_metrics(phone, "ai")

                return jsonify({"status": "ok"})

            send_message(phone, "Nyora number ye lesson.")
            return jsonify({"status": "ok"})

        if 1 <= int(incoming) <= len(module_keys):

            module = module_keys[int(incoming)-1]
            pdf, label = modules[module]

            record_module_access(phone, module)
            log_activity(phone, "open_module", module)
            update_metrics(phone, "module")

            # 📘 Send lesson title first
            send_message(
                phone,
                f"{label}\n\n🎧 Teerera voice lesson wobva waona manotes 👇"
            )

            # 🎧 Send voice lesson(s)
            send_message(phone, "🎧 Lesson audio (listen in order) 👇")

            send_audio_series(phone, module)

            # 📄 Send PDF
            send_pdf(
                phone,
                f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}",
                label
            )

            # 🤖 Encourage AI use
            send_message(
                phone,
                "Kana pane chausinganzwisise, bvunza pano 🤖"
            )
            conn = get_db()
            c = conn.cursor()

            # clear old AI memory for this module
            c.execute(
                "DELETE FROM ai_memory WHERE phone=%s AND module=%s",
                (phone, module)
            )

            # set the active module for follow-up questions
            c.execute(
                "UPDATE users SET active_module=%s WHERE phone=%s",
                (module, phone)
            )

            conn.commit()
            DATABASE_POOL.putconn(conn)
            
            return jsonify({"status": "ok"})

    elif user["state"] == "pay_menu":

        if incoming == "1":
            set_state(phone, "awaiting_payment")

            send_admin_alert(
                "Customer requested payment instructions",
                f"Phone: {phone}\nMethod: EcoCash"
            )

            send_message(
               phone,
               "📲 *Bhadhara neEcoCash *\n\n"
               "Nyora izvi pafoni yako 👇\n\n"
               "*153*1*1*0773208904*6#\n\n"
               "👤 Recipient: *Beloved Nkomo*\n"
               f"💵 Amount: *${COURSE_PRICE}* add cashout charges\n"
               "✔ Chibva waisa EcoCash PIN\n"
               "✔ Kana wapedza kubhadhara, tumira confirmation message yacho pano:"
            )
            return jsonify({"status": "ok"})

        elif incoming == "2":
           set_state(phone, "main")
           send_message(phone, main_menu())
           return jsonify({"status": "ok"})


    elif user["state"] == "store_category":

        categories = {
            "1": "dishwash",
            "2": "bleach",
            "3": "orange_drink"
        }

        if incoming in categories:
            selected = categories[incoming]
            set_state(phone, f"store_pack_{selected}")

            send_message(
                phone,
                "📦 Choose Pack Size:\n\n"
                "1️⃣ Starter\n"
                "2️⃣ Medium\n"
                "3️⃣ Bulk Business\n\n"
                "Reply with 1, 2 or 3"
            )
            return jsonify({"status": "ok"})

    elif user["state"].startswith("store_pack_"):

        category = user["state"].replace("store_pack_", "")

        sizes = {
            "1": "starter",
            "2": "medium",
            "3": "bulk"
        }

        if incoming in sizes:

            size = sizes[incoming]
            pack = STORE_PACKS[category][size]

            conn = get_db()
            c = conn.cursor()
            c.execute("""
                INSERT INTO temp_orders (phone, item)
                VALUES (%s, %s)
                ON CONFLICT (phone)
                DO UPDATE SET item = EXCLUDED.item
            """, (phone, pack["name"]))
            conn.commit()
            DATABASE_POOL.putconn(conn)

            items_list = "\n".join([f"✔ {i}" for i in pack["items"]])

            send_message(
                phone,
                f"📦 *{pack['name']}*\n\n"
                f"{items_list}\n\n"
                f"💵 Product Price: {pack['price']}\n\n"
                "Reply *ORDER* to confirm."
            )

            set_state(phone, "store_confirm")
            return jsonify({"status": "ok"})

    elif user["state"] == "store_confirm":

        if incoming == "order":
            set_state(phone, "store_delivery")

            send_message(
                phone,
                "🚚 Enter your *Town / Area* for delivery fee calculation.\n\n"
                "Example: Gweru"
            )
            return jsonify({"status": "ok"})

    elif user["state"] == "store_delivery":

        town = incoming.lower()
        delivery_fee = DELIVERY_FEES.get(town, DEFAULT_DELIVERY_FEE)

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT item FROM temp_orders WHERE phone=%s", (phone,))
        order = c.fetchone()
        DATABASE_POOL.putconn(conn)

        if not order:
            send_message(phone, "❌ Order not found. Nyora *MENU*")
            return jsonify({"status": "ok"})

        item_name = order[0]

        base_price = None
        for category in STORE_PACKS.values():
            for size in category.values():
                if size["name"] == item_name:
                    base_price = int(size["price"].replace("$", ""))
                    break

        if base_price is None:
            send_message(phone, "❌ Price error.")
            return jsonify({"status": "ok"})

        total = base_price + delivery_fee

        set_state(phone, "main")

        send_message(
            phone,
            f"📦 Order: {item_name}\n"
            f"🚚 Delivery to: {town.title()}\n"
            f"💵 Product Price: ${base_price}\n"
            f"🚚 Delivery Fee: ${delivery_fee}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 TOTAL: ${total}\n\n"
            "📲 Pay via EcoCash 0773 208904\n"
            "Send proof here.\n\n"
            "↩ Nyora *MENU* kudzokera."
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
                "📍 Bulawayo/ Harare\n\n"
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

    elif user["state"] == "laundry_course_menu":

        if incoming == "menu":
            set_state(phone, "main")
            send_message(phone, main_menu())
            return jsonify({"status": "ok"})

        # FREE lesson only
        if incoming == "1":
            send_message(
                phone,
                "📘 *DAY 1: BASICS (FREE)*\n\n"
                "Soap is made when:\n"
                "👉 Caustic soda reacts with oil/fat\n\n"
                "Ingredients:\n"
                "✔ Tallow/Oil\n"
                "✔ Caustic soda\n"
                "✔ Sulphonic acid\n\n"
                "🔓 To unlock full training nyora *PAY*"
            )
            return jsonify({"status": "ok"})

        # LOCKED lessons
        if incoming in ["2", "3", "4", "5"] and not user["is_paid"]:
            send_message(
                phone,
                "🔒 *FULL TRAINING LOCKED*\n\n"
                "Unongowana Day 1 chete mahara.\n\n"
                "💵 Full Laundry Bar Training + All formulas: $5\n\n"
                "Nyora *PAY* kuti uvhure."
            )
            return jsonify({"status": "ok"})

        lessons = {
            "2": (
                "⚠ *DAY 2: SAFETY*\n\n"
                "✔ Always add caustic soda into water\n"
                "✔ Do not touch fresh soap\n"
                "✔ Work in open space\n\n"
                "Steps:\n"
                "1. Make lye\n"
                "2. Melt oil\n"
                "3. Mix properly\n\n"
                "Reply 3 for next lesson"
            ),

            "3": (
                "🟢 *DAY 3: PREMIUM BAR*\n\n"
                "Formula (10kg):\n"
                "Tallow 8.3kg\n"
                "Caustic soda 1.2kg\n"
                "Sulphonic acid 0.7kg\n\n"
                "Steps:\n"
                "1. Make lye\n"
                "2. Melt tallow\n"
                "3. Mix → thick\n"
                "4. Add sulphonic acid\n\n"
                "Result:\n"
                "✔ Smooth\n✔ High quality\n\n"
                "Reply 4 for next lesson"
            ),

            "4": (
                "🟡 *DAY 4: BUDGET BARS*\n\n"
                "Option 1:\n"
                "Tallow + Chalk\n\n"
                "Option 2:\n"
                "Tallow + Dolomite\n\n"
                "Key:\n"
                "✔ Add filler slowly\n"
                "✔ Mix well (no lumps)\n\n"
                "Result:\n"
                "✔ Cheaper\n✔ Good profit\n\n"
                "Reply 5 for next lesson"
            ),

            "5": (
                "⚫ *DAY 5: ULTRA CHEAP + BUSINESS*\n\n"
                "Formula:\n"
                "Used oil + filler\n\n"
                "Key:\n"
                "✔ Very low cost\n"
                "✔ Strong cleaning\n\n"
                "Business:\n"
                "Premium → brand\n"
                "Budget → daily sales\n"
                "Ultra → volume\n\n"
                "🎉 You completed training!\n"
                "Nyora *MENU* kudzokera"
            )
        }

        if incoming in lessons:
            send_message(phone, lessons[incoming])
            return jsonify({"status": "ok"})

        send_message(phone, "Sarudza lesson 1–5 kana nyora MENU")
        return jsonify({"status": "ok"})

    elif user["state"] == "ai_chat":

        if incoming == "menu":
            set_state(phone, "main")
            send_message(phone, main_menu())
            return jsonify({"status": "ok"})

        ai_answer = ai_trainer_reply(phone, incoming, [])

        send_message(phone, ai_answer)

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

            send_message(phone, "Enter total units produced (e.g. 40):")
            return jsonify({"status": "ok"})

        elif incoming == "2":
            set_state(phone, "calc_quick_raw")

            send_message(phone, "Enter total raw material cost:")
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

        send_message(phone, "Enter total raw material cost:")
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

        send_message(phone, "Enter packaging cost per unit:")
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

        send_message(phone, "Enter selling price per unit:")
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

        send_message(phone, "Enter number of units:")
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

        send_message(phone, "Enter packaging cost per unit:")
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

        send_message(phone, "Enter selling price per unit:")
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

# =========================
# UNPAID USER PROTECTION
# =========================
    if not user["is_paid"]:

        faq = faq_engine(incoming)

        if faq:
            send_message(phone, faq)
            return jsonify({"status": "ok"})

        if incoming not in ["menu","start","pay","1","2","3","4","5","6","7","8","9"]:
            send_message(
                phone,
                "📚 AI trainer & ma formula anovhurwa kune vakabhadhara chete.\nNyora *PAY* kuti utange."
            )
            return jsonify({"status":"ok"}) 
    blocked_commands = ["1","2","3","4","5","6","menu","start","pay","admin","hie","makadini"]
    
    if not incoming.isdigit() and user["is_paid"]:
               
        today_count = ai_questions_today(phone)

        if today_count >= 15:
            send_message(
                phone,
                "⛔ Wapfuura 15 AI questions nhasi.\n"
                "Dzokazve mangwana kuti uenderere mberi."
            )
            return jsonify({"status": "ok"})

        allowed_modules = get_user_modules(phone, incoming)

        if not allowed_modules:
            send_message(phone, "🔒 Tapota vhura module kutanga.")
            return jsonify({"status": "ok"})

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
        file = request.files.get("file")

        if file and allowed_file(file.filename):

            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            file.save(filepath)

            # determine module name from filename
            module_name = filename.replace(".pdf", "")

            save_pdf_to_db(module_name, filename)

            return redirect(url_for("admin_dashboard"))

    stats = get_dashboard_stats()

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


    DATABASE_POOL.putconn(conn)

    html = "<h2>Arachis Admin Dashboard</h2>"

    # ===== STATS =====
    html += f"""
    <h3>📊 System Stats</h3>
    <ul>
        <li>Total Users: <b>{stats['total_users']}</b></li>
        <li>Paid Users: <b>{stats['paid_users']}</b></li>
        <li>Module Opens: <b>{stats['module_opens']}</b></li>
        <li>AI Questions Asked: <b>{stats['ai_questions']}</b></li>
        <li>Blocked Access Attempts: <b>{stats['blocked_attempts']}</b></li>
    </ul>
    <hr>
    """
    html += "<hr><h3>🚫 Users Blocked From Modules</h3>"

    for b in blocked_users:
        html += f"{b[0]} | Attempts: {b[1]}<br>"
    
    # ===== UPLOAD =====
    html += """
    <h3>📤 Upload Lesson PDF</h3>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file" required>
        <button type="submit">Upload PDF</button>
    </form>
    <hr>
    """

    # ===== USERS =====
    html += "<h3>👥 Users</h3>"
    for u in users:
        phone = u[0]
        is_paid = u[1]
        payment_status = u[2]
   
        html += f"""
        {phone} | Paid: {is_paid} | Status: {payment_status}
        | <a href='/admin/approve/{phone}'>Approve</a><br>
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
def admin_approve(phone):
    mark_paid(normalize_phone(phone))
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
            send_message(phone, message)

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
        send_message(phone, message)

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

@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

try:
    init_db()
    auto_sync_lessons()
    print("Startup successful")
except Exception as e:
    print("Startup error:", e)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

































































































































































































































































