import PyPDF2
import requests
from openai import OpenAI
from flask import Flask, request, jsonify, redirect, url_for
import psycopg2
from urllib.parse import urlparse
import os
from werkzeug.utils import secure_filename


app = Flask(__name__)

# =========================
# CONFIG
# =========================
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

ADMIN_NUMBER = "+263773208904"  # MUST include +

UPLOAD_FOLDER = "static/lessons"
ALLOWED_EXTENSIONS = {"pdf"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# DATABASE
# =========================
def get_db():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise Exception("DATABASE_URL not set")

    url = urlparse(database_url)

    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port,
        sslmode="require"
    )

    return conn
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
    
    
    conn.commit()
    conn.close()


# ✅ call once only
init_db()

    


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



def create_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (phone)
        VALUES (%s)
        ON CONFLICT (phone) DO NOTHING
    """, (phone,))
    conn.commit()
    conn.close()

def get_unpaid_active_users():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    SELECT u.phone
    FROM users u
    LEFT JOIN student_metrics s ON u.phone = s.phone
    WHERE u.is_paid = 0
    AND (s.total_messages > 2 OR s.modules_opened > 0)
    """)

    rows = c.fetchall()
    conn.close()

    return [r[0] for r in rows]

def followup_message():
    return (
        "👋 Makadii!\n\n"
        "Takaona makamboshandisa Arachis Training Bot asi hamusati mapedza kunyoresa.\n\n"
        "Vanhu vazhinji vari kutotanga kugadzira dishwash & bleach vari kumba 🧼\n\n"
        "💵 Full course: $5 once-off\n"
        "✔ 20 detergent modules\n"
        "✔ 6 drink modules\n"
        "✔ Rubatsiro rwe AI kana wasangana nedambudziko\n\n"
        "Nyora *PAY* kuti utange kana *MENU* kuona zvirimo."
    )

def get_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone, state, payment_status, is_paid FROM users WHERE phone=%s", (phone,))
    row = c.fetchone()
    conn.close()

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
    conn.close()

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
    conn.close()

def set_payment_status(phone, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET payment_status=%s WHERE phone=%s", (status, phone))
    conn.commit()
    conn.close()

def mark_paid(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET is_paid=1, payment_status='approved' WHERE phone=%s",
        (phone,)
    )
    conn.commit()
    conn.close()

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
    conn.close()
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
    conn.close()
        
def log_activity(phone, action, details=""):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO activity_log (phone, action, details)
        VALUES (%s, %s, %s)
    """, (phone, action, details))
    conn.commit()
    conn.close()

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

def save_pdf_to_db(module_name, pdf_filename):

    text = extract_pdf_text(pdf_filename)

    if not text:
        print("No text extracted")
        return

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO lesson_content (module, content)
        VALUES (%s, %s)
        ON CONFLICT (module)
        DO UPDATE SET content = EXCLUDED.content
    """, (module_name, text))

    conn.commit()
    conn.close()

    print(f"Saved {module_name} to database")

def get_lesson_from_db(module_name):

    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT content FROM lesson_content WHERE module=%s",
        (module_name,)
    )

    row = c.fetchone()
    conn.close()

    if row:
        return row[0]

    return ""

    
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

    conn.close()

    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "module_opens": module_opens,
        "ai_questions": ai_questions,
        "blocked_attempts": blocked_attempts
    }



# ✅ NEW (REQUIRED FOR AI RESTRICTION)
def get_user_modules(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT module FROM module_access WHERE phone=%s",
        (phone,)
    )
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

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
        "1️⃣ Detergents\n"
        "2️⃣ Concentrate Drinks\n"
        "3️⃣ Mitengo & Kubhadhara\n"
        "4️⃣ Free Lesson\n"
        "5️⃣ Join Full Online Training\n"
        "6️⃣ Register for Offline Classes\n"
        "7️⃣ Online Store (Chemicals)\n"
        "8️⃣ Tsvaga Rubatsiro\n"
        "9️⃣ Supplier Directory")
    
def free_lesson():
    return (
        "🎁 *FREE LESSON*\n\n"
        "Dishwash basics:\n"
        "✔ SLES\n✔ Salt\n✔ Dye\n✔ Perfume\n✔ Mvura\n\n"
        "⚠ Pfeka magloves, mask ne apron.\n\n"
        "↩ Nyora *MENU* kudzokera kumusoro."
    )

# =========================
# AI FAQ
# =========================
def ai_faq_reply(msg):
    if any(k in msg for k in ["price", "cost", "fee", "marii"]):
        return "💵 Full training: $10 once-off\nNyora *PAY*"
    if "certificate" in msg:
        return "🎓 Ehe — unowana certificate."
    if "kupi" in msg:
        return " Tinowanika kuMataga"
    return None

# ✅ MODIFIED (MODULE-AWARE AI)
def ai_trainer_reply(question, allowed_modules):

    pdf_text_blocks = []

    module_pdf_map = {
        "dishwash": "dishwash.pdf",
        "thick_bleach": "thick_bleach.pdf",
        "foam_bath": "foam_bath.pdf",
        "pine_gel": "pine_gel.pdf",
        "toilet_cleaner": "toilet_cleaner.pdf",
        "engine_cleaner": "engine_cleaner.pdf",
        "laundry_bar": "laundry_bar.pdf",
        "fabric_softener": "fabric_softener.pdf",
        "petroleum_jelly": "petroleum_jelly.pdf",
        "floor_polish": "floor_polish.pdf",
        "orange_drink": "orange_drink.pdf",
        "raspberry_drink": "raspberry_drink.pdf",
        "cream_soda": "cream_soda.pdf"
    }
    pdf_text_blocks = []

    for module in allowed_modules:
        lesson_text = get_lesson_from_db(module)

        if lesson_text:
            pdf_text_blocks.append(lesson_text)

    combined_text = "\n\n".join(pdf_text_blocks)

    # Limit lesson content size to prevent token overload
    combined_text = combined_text[:8000]

    
    prompt = f"""
You are a professional hands-on chemical production trainer.

Below is the official lesson material:

{combined_text}

Student question:
{question}

Your job:
- If the student asks HOW TO FIX a product that is already made, give immediate practical rescue steps first.
- If the student asks WHY something happened, explain clearly.
- If the student asks for formula guidance, give direct structured answer.
- Only diagnose when necessary.
- Always give practical step-by-step instructions.
- Tell them exactly what to add, how much to add gradually, and what to observe.
- Give prevention advice for next batch only after solving the current issue.
- Do NOT invent new ingredients outside lesson but if students asks about a certain chemical and its relevance, give needed direction.
- When fixing thickness problems, give gradual measurable steps (e.g., add 1 tablespoon at a time, mix 2 minutes, observe).
- Speak naturally like a trainer and only correct grammatical shona
"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.6
    )

    return response.choices[0].message.content.strip()


def detect_module_from_question(question):
    q = question.lower()

    if "dishwash" in q or "dish wash" in q:
        return "dishwash"
    if "bleach" in q:
        return "thick_bleach"
    if "foam" in q:
        return "foam_bath"
    if "pine" in q:
        return "pine_gel"
    if "toilet" in q:
        return "toilet_cleaner"
    if "engine" in q:
        return "engine_cleaner"
    if "laundry" in q or "soap" in q:
        return "laundry_bar"
    if "fabric" in q or "softener" in q:
        return "fabric_softener"
    if "petroleum" in q or "vaseline" in q:
        return "petroleum_jelly"
    if "polish" in q:
        return "floor_polish"

    return None


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
        incoming = message["text"]["body"].strip().lower()
        update_metrics(phone, "message")
        log_activity(phone, "incoming_message", incoming)
    except Exception:
        return "OK", 200

    create_user(phone)
    user = get_user(phone)
    if not user:
        return "OK", 200


    # START OF YOUR OLD LOGIC

    faq = ai_faq_reply(incoming)
    if faq and incoming not in ["1","2","3","4","5","6","menu","pay","join","admin"]:
        send_message(phone, faq)
        return jsonify({"status": "ok"})

    if incoming == "admin" and phone == ADMIN_NUMBER:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_paid=1")
        paid = c.fetchone()[0]
        conn.close()
        send_message(phone, f"📊 *ADMIN DASHBOARD*\n\n👥 Users: {total}\n💰 Paid: {paid}")
        return jsonify({"status": "ok"})

    if incoming.startswith("approve ") and phone == ADMIN_NUMBER:
        target = normalize_phone(incoming.replace("approve ", ""))
        log_activity(target, "payment_approved", "admin")
        mark_paid(target)
        send_message(target, "🎉 Payment Approved!\nYou now have full access.")
        send_message(phone, f"✅ Approved: {target}")
        return jsonify({"status": "ok"})

    if incoming in ["menu", "start", "makadini", "hie",]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        log_activity(phone, "open_menu", "main")
        return jsonify({"status": "ok"})

    if incoming == "pay":
        set_state(phone, "pay_menu")
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
            set_state(phone, "detergent_menu")
            log_activity(phone, "open_menu", "detergents")
            send_message(phone,
                "🧼 *DETERGENTS – PAID LESSONS*\n\n"
                "1️⃣ Dishwash\n"
                "2️⃣ Thick Bleach\n"
                "3️⃣ Foam Bath\n"
                "4️⃣ Pine Gel\n"
                "5️⃣ Toilet Cleaner\n"
                "6️⃣ Engine Cleaner\n"
                "7️⃣ Laundry Bar Soap\n"
                "8️⃣ Fabric Softener\n"
                "9️⃣ Petroleum Jelly\n"
                "🔟 Floor Polish\n\n"
                "Nyora *MENU* kudzokera kumusoro"
            )
            return jsonify({"status": "ok"})

        if incoming == "2":
            set_state(phone, "drink_menu")
            send_message(
                phone,
                "🥤 *CONCENTRATE DRINKS – PAID LESSONS*\n\n"
                "1️⃣ Orange Concentrate\n"
                "2️⃣ Raspberry Concentrate\n"
                "3️⃣ Cream Soda\n\n"
                "Nyora *MENU* kudzokera"
            )
            log_activity(phone, "open_menu", "drinks")
            return jsonify({"status": "ok"})

        elif incoming == "3":
            send_message(phone, "💵 Full training: $10 once-off\nNyora *PAY*")
            return jsonify({"status": "ok"})

        elif incoming == "4":
            send_message(phone, free_lesson())
            return jsonify({"status": "ok"})

        elif incoming == "5":
            send_message(phone, "📝 Join full online training — Nyora *PAY*")
            return jsonify({"status": "ok"})

        elif incoming == "6":
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

        elif incoming == "7":
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

        elif incoming == "8":
            send_message(phone, "📝 Kana une dambudziko raungada rubatsiro — Taura nesu pa *+263719208904*")
            return jsonify({"status": "ok"})

        elif incoming == "9":
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

    elif user["state"] == "pay_menu":

        if incoming == "1":
            set_state(phone, "awaiting_payment")
            send_message(
               phone,
               "📲 *Bhadhara neEcoCash *\n\n"
               "Nyora izvi pafoni yako 👇\n\n"
               "*153*1*1*0773208904*10#\n\n"
               "👤 Recipient: *Beloved Nkomo*\n"
               "💵 Amount: *$10*\n\n"
               "✔ Chibva waisa EcoCash PIN\n"
               "✔ Kana wapedza kubhadhara, nyora: *DONE*"
            )
            return jsonify({"status": "ok"})

        elif incoming == "2":
           set_state(phone, "main")
           send_message(phone, main_menu())
           return jsonify({"status": "ok"})

    elif user["state"] == "awaiting_payment" and incoming == "done":
        set_payment_status(phone, "awaiting_approval")
        send_message(
            phone,
            "⏳ Payment noted.\n"
            "Mirira zvishoma tiongorore.\n\n"
            "Tichakuzivisa nekukurumidza ✅\n\n"
             "↩ Nyora *MENU* kudzokera."
        )

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
            conn.close()

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
        conn.close()

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
        
    elif user["state"] == "detergent_menu":

        fresh_user = get_user(phone)

        if not fresh_user["is_paid"]:

            send_message(phone, "🔒 *Paid Members Only*\nNyora *PAY*")
            return jsonify({"status": "ok"})

        modules = {
            "1": ("dishwash", "dishwash.pdf", "🧼 DISHWASH"),
            "2": ("thick_bleach", "thick_bleach.pdf", "🧴 THICK BLEACH"),
            "3": ("foam_bath", "foam_bath.pdf", "📘 FOAM BATH"),
            "4": ("pine_gel", "pine_gel.pdf", "🌲 PINE GEL"),
            "5": ("toilet_cleaner", "toilet_cleaner.pdf", "🚽 TOILET CLEANER"),
            "6": ("engine_cleaner", "engine_cleaner.pdf", "🛠 ENGINE CLEANER"),
            "7": ("laundry_bar", "laundry_bar.pdf", "📘 LAUNDRY BAR"),
            "8": ("fabric_softener", "fabric_softener.pdf", "🌲 FABRIC SOFTENER"),
            "9": ("petroleum_jelly", "petroleum_jelly.pdf", "🚽 PETROLEUM JELLY"),
            "10": ("floor_polish", "floor_polish.pdf", "🛠 FLOOR POLISH")
        }

        if incoming in modules:
            module, pdf, label = modules[incoming]
            update_metrics(phone, "module")
            record_module_access(phone, module),
            send_pdf(phone,
                     
                f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}",
                label
            )
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
        conn.close()

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
        conn.close()

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
        conn.close()

        set_state(phone, "main")
        send_message(
            phone,
            "✅ Registration received!\n\n"
            "💳 Pay *$50* to Ecocash 0773 208904\n"
            "Send proof here.\n\n"
            "We will confirm your seat after approval."
        )
        return jsonify({"status": "ok"})


    # =========================
# DRINK MODULE MENU
# =========================
    if user["state"] == "drink_menu":

        fresh_user = get_user(phone)

        if not fresh_user["is_paid"]:
            send_message(phone, "🔒 *Paid Members Only*\nNyora *PAY*")
            log_activity(phone, "blocked_access", "drink_modules")
            return jsonify({"status": "ok"})

        drink_modules = {
            "1": ("orange_drink", "orange_drink.pdf", "🍊 ORANGE CONCENTRATE"),
            "2": ("raspberry_drink", "raspberry_drink.pdf", "🍓 RASPBERRY CONCENTRATE"),
            "3": ("cream_soda", "cream_soda.pdf", "🥤 CREAM SODA")
        }

        if incoming in drink_modules:
            module, pdf, label = drink_modules[incoming]

            record_module_access(phone, module)
            log_activity(phone, "open_module", module)
            update_metrics(phone, "module")

            send_pdf(
                phone,
                f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}",
                label
            )
            return jsonify({"status": "ok"})

   

    # =========================
    # AI TRAINER (MODULE RESTRICTED)
    # =========================
    blocked_commands = ["1","2","3","4","5","6","menu","start","pay","admin","hie","makadini"]

    if incoming not in blocked_commands and user["is_paid"]:
               
        today_count = ai_questions_today(phone)

        if today_count >= 15:
            send_message(
                phone,
                "⛔ Wapfuura 15 AI questions nhasi.\n"
                "Dzokazve mangwana kuti uenderere mberi."
            )
            return jsonify({"status": "ok"})

        allowed_modules = get_user_modules(phone)

        if not allowed_modules:
            send_message(phone, "🔒 Tapota vhura module kutanga.")
            return jsonify({"status": "ok"})

        # If user has 2 or more modules → allow full cross-module AI
        if len(allowed_modules) >= 2:
            ai_answer = ai_trainer_reply(incoming, allowed_modules)
            log_activity(phone, "ai_question", incoming)
            send_message(phone, ai_answer)
            return jsonify({"status": "ok"})

        # If user has only 1 module → still allow AI but only that module
        ai_answer = ai_trainer_reply(incoming, allowed_modules)
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
    """)
    c.execute("""
    SELECT phone, total_messages, ai_questions, modules_opened, last_active
    FROM student_metrics
    ORDER BY last_active DESC
    LIMIT 50
    """)
    students = c.fetchall() 


    conn.close()

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

    html += "<hr><h3>📜 Activity Feed (Latest 100)</h3>"

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
        html += """
        <hr>
        <h3>📣 Marketing</h3>
        <a href="/admin/followup-unpaid">Send follow-up to unpaid users</a>
        <hr>
        """
    return html

    if status == "Paid":
        mark_paid(phone)
        send_message(phone, "✅ Payment received. You now have full access.")

    return "OK", 200



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

    users = get_unpaid_active_users()

    count = 0
    for phone in users:
        send_message(phone, followup_message())
        count += 1

    return f"Sent followups to {count} users"

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

















































































































































































































