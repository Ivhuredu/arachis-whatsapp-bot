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
# MODULE CONTENT FOR AI TRAINER
# =========================

MODULE_CONTENT = {

    "dishwash": """
Ingredients:
- SLES 1.5kg
- Sulphonic acid 1 litre
- Caustic soda 3 tablespoons
- Soda ash 3 tablespoons
- Salt 500g
- Bermacol 3 tablespoons
- Amido 100ml
- Dye 20g
- Perfume 33ml
- Water 17.5 litres

Steps:
1. Mix 10L water with SLES until dissolved
2. Add sulphonic acid and mix well
3. Add caustic soda
4. Add soda ash
5. Add salt slowly
6. Add bermacol (pre-mixed)
7. Add dye gradually
8. Add perfume
9. Add amido
10. Top up with water
""",

    "thick_bleach": """
Ingredients:
- SLES 2kg
- Hypochlorite 3kg
- Caustic soda 300g
- Water 15 litres

Steps:
1. Dissolve SLES in water
2. Add caustic soda
3. Add hypochlorite slowly
4. Add perfume
5. Adjust thickness with water
""",

    "foam_bath": """
Ingredients:
- SLES 2kg
- CDE 500ml
- Glycerin 500ml
- Salt 1 cup
- Dye 20g
- Formalin 10ml
- Perfume
- Amido

Steps:
1. Mix SLES and CDE
2. Add glycerin
3. Add salt gradually
4. Add dye
5. Add formalin
6. Add perfume
7. Add amido
""",

    "pine_gel": """
Ingredients:
- Pine oil 1L
- Sulphonic Acid 3kg
- Caustic Soda 350g
- Np6 1kg
- Water 15 litres
- Green Dye

Steps:
1. Water 15l
2. Add 3kg Sulphonic Acid
3. Add 350g Caustic Soda
4. Add 1kg Np6
5. Add dye
6. Add 1litre pine oil
7. ph inofanira kuita pH7
""",

    "toilet_cleaner": """
Ma ingredients anodiwa kugadzira 
1.125ml Sulphonic Acid
2.250g Sless
3.125g Salt
4.3 Spoons Caustic Soda
5.Perfume Lavender kana kuti Pine
6.Dye (Blue kana kuti Purple)
7.Bermacol (hafu ye satchet)
8.4.5 litres mvura
""",

    "engine_cleaner": """
Ma ingredients anodiwa
1.19.5 litres Paraffin
2.NP-9 400ml
3.5-10 grams Oil-soluble Red Dye
4.30-50ml Oil- Soluble Perfume (Orange,Strawberry kana kuti Lavender)
""",

    "laundry_bar": """
Ma ingredients anodiwa kugadzira 10 magreen bar
1. 7.2 kg Tallow
2. 3.2 kg Dolomite
3. 1kg Sulphonic acid
4.1.1 kg Caustic soda
5. 10 mls Liquid soap dye
6. 20mls Fragrance optional
""",

    "fabric_softener": """
Ma ingredientes anodiwa kugadzira 20 litres
1.19 litres water
2. 1kg  Ardogen
3. Fabric Softener Dye (shoma)
4. Fabric Softener Perfume 30-50ml
""",

    "floor_polish": """
Ingredients 
1 Wax 4 kg
2 Hardener 1kg 
3 Oxide 200g-400g 
4 perfume 30 mls 
5 Paraffin 10-12 litres

red and back liquid polish
Ma ingredients anodiwa:
1.Savenix 4ltrs 
2.Thickener 50mls 
3.Colesents 500mls 
4.Oxide 100-200g
""",

    "petroleum_jelly": """
Maingredients anodiwa kugadzira 
1.Petroleum jelly 1kg
2.Perfume 15ml (Pinnacle Ladder)
3.Dye (Yellow- oil based) 
3.White oil  20ml
"""
}
# =========================
# CONCENTRATE DRINK MODULES
# =========================

DRINK_MODULE_CONTENT = {
    "orange_drink": """
Ingredients:
- Sugar 8kg
- Water 10 litres
- Orange flavour 100ml
- Citric acid 50g
- Sodium benzoate 20g
- Food colour (orange)

Steps:
1. Dissolve sugar in warm water
2. Add citric acid and mix well
3. Add sodium benzoate
4. Add flavour and colour
5. Top up with water
6. Filter and bottle
""",

    "raspberry_drink": """
Ingredients:
- Sugar 8kg
- Water 10 litres
- Raspberry flavour 100ml
- Citric acid 50g
- Sodium benzoate 20g
- Red food colour

Steps:
1. Dissolve sugar
2. Add citric acid
3. Add preservative
4. Add flavour & colour
5. Filter and bottle
""",

    "cream_soda": """
Ingredients:
- Sugar 8kg
- Water 10 litres
- Cream soda flavour 100ml
- Citric acid 50g
- Sodium benzoate 20g
- Green food colour

Steps:
1. Dissolve sugar
2. Add citric acid
3. Add preservative
4. Add flavour & colour
5. Bottle
"""
}



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

    requests.post(url, headers=headers, json=payload)


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

    requests.post(url, headers=headers, json=payload)


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
        "price": "$2 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "hypo": {
        "name": "Sodium Hypochlorite",
        "price": "$2 per litre",
        "sizes": "1L | 5L | 20L"
    },
    "cde": {
        "name": "CDE (Cocamide DEA)",
        "price": "$5 per litre",
        "sizes": "1L | 5L"
    },
    "perfume": {
        "name": "Detergent Perfumes",
        "price": "$1 per 30ml",
        "sizes": "30ml | 50ml | 100ml"
    },
     "soda": {
        "name": "Soda Ash",
        "price": "$2 per kg",
        "sizes": "500ml| 1L | 5L"
    },
    "bermacol": {
        "name": "Bermacol",
        "price": "$7 per 1kg",
        "sizes": "50g | 100g | 500g | 1kg"
    },
    "amido": {
        "name": "Amido",
        "price": "$3 per litre",
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
        "price": "$5 per 1kg",
        "sizes": "100g | 500g | 1kg"
    }
}



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
        "8️⃣ Tsvaga Rubatsiro")

def free_lesson():
    return (
        "🎁 *FREE LESSON*\n\n"
        "Dishwash basics:\n"
        "✔ SLES\n✔ Salt\n✔ Dye\n✔ Perfume\n✔ Mvura\n\n"
        "⚠ Pfeka magloves, mask ne apron."
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

    content_blocks = []

    for m in allowed_modules:
        if m in MODULE_CONTENT:
            content_blocks.append(MODULE_CONTENT[m])
        if m in DRINK_MODULE_CONTENT:
            content_blocks.append(DRINK_MODULE_CONTENT[m])

    lessons_text = "\n\n".join(content_blocks)

    prompt = f"""
You are an Arachis Online Training instructor.

Below are the exact lessons the student has studied:

{lessons_text}
    
Your role:
- Help students understand detergent making practically
- Explain clearly in natural Shona mixed with simple English
- Give safety tips when needed
- Expand on lessons when helpful
- Use examples

You teach these modules:
Dishwash, Thick Bleach, Foam Bath, Pine Gel, Toilet Cleaner, Engine Cleaner,
Laundry Bar, Fabric Softener, Petroleum Jelly, Floor Polish

Rules:
- Answer ONLY using the lesson content above
- Do not add new ingredients or steps
- Answer naturally like a real trainer (not a robot)
- If a student asks beyond modules, relate it back practically
- Avoid dangerous chemical advice
- Correct mistakes politely

Student question:
{question}
"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
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
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

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
            set_state(phone, "store")
            send_message(
                phone,
                "🛒 *ARACHIS ONLINE STORE*\n\n"
                "Machemicals aripo:\n"
                "- SLES\n"
                "- Caustic Soda\n"
                "- Hypochlorite\n"
                "- CDE\n"
                "- Perfumes\n\n"
                "🔍 Nyora chemical yauri kuda.\n"
                "Nyora *MENU* kudzokera."
            )
            return jsonify({"status": "ok"})
            
        elif incoming == "8":
            send_message(phone, "📝 Kana une dambudziko raungada rubatsiro — Taura nesu pa *+263714961448*")
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
            "Tichakuzivisa nekukurumidza ✅"
        )
        return jsonify({"status": "ok"})
        

    # =========================
    # ONLINE STORE
    # =========================
    elif user["state"] == "store":

        for key, item in STORE_ITEMS.items():
            if key in incoming:
                conn = get_db()
                c = conn.cursor()
                c.execute(
                  "UPDATE users SET state=%s WHERE phone=%s",
                  ("store_view_item", phone)
                )
                
                c.execute("""
                    INSERT INTO temp_orders (phone, item)
                    VALUES (%s, %s)
                    ON CONFLICT (phone) DO UPDATE SET item = EXCLUDED.item
                """, (phone, item["name"]))
                conn.commit()
                conn.close()

                send_message(
                    phone,
                    f"🧪 *{item['name']}*\n\n"
                    f"💵 Price: {item['price']}\n"
                    f"📦 Sizes: {item['sizes']}\n\n"
                    "✍🏽 Nyora *ORDER* kuti uende mberi"
                )
                return jsonify({"status": "ok"})

    elif user["state"] == "store_view_item":

        if incoming == "order":
            set_state(phone, "store_quantity")
            send_message(phone, "📦 Enter quantity (e.g. 5 litres):")
            return jsonify({"status": "ok"})

    elif user["state"] == "store_quantity":

        if incoming.isdigit():
            qty = int(incoming)

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE temp_orders SET quantity=%s WHERE phone=%s",
                (qty, phone)
            )

            conn.commit()
            conn.close()

            set_state(phone, "main")

            send_message(
                phone,
                f"✅ Order yako yatambirwa!\n\n"
                f"📦 Quantity: {qty}\n"
                f"📞 Order yako iri kugadzirwa.\n"
                f"💳 Payment: EcoCash / Cash\n"
                f"🚚 Delivery available countrywide."
            )
            return jsonify({"status": "ok"})

        else:
            send_message(phone, "❌ Tapota nyora number chete.")
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
            record_module_access(phone, module)
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

        allowed_modules = get_user_modules(phone)
        requested_module = detect_module_from_question(incoming)

        if requested_module and requested_module in allowed_modules:
            ai_answer = ai_trainer_reply(incoming, [requested_module])
            log_activity(phone, "ai_question", incoming)
            send_message(phone, ai_answer)
            return jsonify({"status": "ok"})

        else:
            send_message(
                phone,
                "❗ Mubvunzo wako hauna kuenderana ne module yawakavhura.\n"
                "Tapota bvunza nezve module yawadzidza."
            )
            log_activity(phone, "blocked_access", "ai_out_of_scope")
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
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(file.filename)))
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

@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))























































































































































































