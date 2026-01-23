from openai import OpenAI
from flask import Flask, request, jsonify, redirect, url_for
from twilio.rest import Client
import sqlite3, os
from werkzeug.utils import secure_filename


app = Flask(__name__)

# =========================
# CONFIG
# =========================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

ADMIN_NUMBER = "+263773208904"  # MUST include +

UPLOAD_FOLDER = "static/lessons"
ALLOWED_EXTENSIONS = {"pdf"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# DATABASE
# =========================
def get_db():
    conn = sqlite3.connect("users.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        state TEXT DEFAULT 'main',
        payment_status TEXT DEFAULT 'none',
        is_paid INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def init_module_access_table():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS module_access (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT,
        module TEXT,
        UNIQUE(phone, module)
    )
    """)
    conn.commit()
    conn.close()


def init_offline_table():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS offline_registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        full_name TEXT,
        location TEXT,
        detergent_choice TEXT,
        payment_status TEXT DEFAULT 'pending'
    )
    """)
    conn.commit()
    conn.close()

def init_activity_log_table():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT,
        action TEXT,
        details TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

    
init_offline_table()

init_db()
init_module_access_table()

init_activity_log_table()

def normalize_phone(phone):
    phone = phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone

def mark_paid(phone):
    phone = normalize_phone(phone)
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET is_paid=1, payment_status='approved'
        WHERE phone=?
    """, (phone,))
    conn.commit()
    conn.close()

# =========================
# HELPERS
# =========================
def send_message(phone, text):
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{phone}",
        body=text
    )

def send_pdf(phone, pdf_url, caption):
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{phone}",
        body=caption,
        media_url=[pdf_url]
    )

def get_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE phone=?", (phone,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (phone) VALUES (?)", (phone,))
    conn.commit()
    conn.close()

def set_state(phone, state):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET state=? WHERE phone=?", (state, phone))
    conn.commit()
    conn.close()

def set_payment_status(phone, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET payment_status=? WHERE phone=?", (status, phone))
    conn.commit()
    conn.close()

def record_module_access(phone, module_name):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO module_access (phone, module) VALUES (?, ?)",
        (phone, module_name)
    )
    conn.commit()
    conn.close()

def log_activity(phone, action, details=""):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO activity_log (phone, action, details) VALUES (?, ?, ?)",
        (phone, action, details)
    )
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
        "SELECT module FROM module_access WHERE phone=?",
        (phone,)
    )
    rows = c.fetchall()
    conn.close()
    return [r["module"] for r in rows]

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
        "5️⃣ Join Full Training\n"
        "6️⃣ Register for Offline Classes\n"
        "7️⃣ Online Store (Chemicals)"
    )

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
    return None

# ✅ MODIFIED (MODULE-AWARE AI)
def ai_trainer_reply(question, allowed_modules):
    if not allowed_modules:
        return "❌ Hausati wavhura module ripi zvaro. Tanga wavhura lesson rauri kudzidza."

    modules_text = ", ".join(allowed_modules)

    prompt = f"""
You are an Arachis Online Training instructor.

Allowed modules for this student:
{modules_text}

Rules:
- ONLY answer using the allowed modules above
- If question is outside these modules, say:
  "Hazvina kufundiswa mu module dzawakavhura"
- Use simple Shona mixed with English
- Be practical
- Emphasize safety
- Do NOT invent chemicals

Question:
{question}
"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=350
    )
    return response.choices[0].message.content.strip()

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    phone = normalize_phone(request.form.get("From", "").replace("whatsapp:", ""))
    incoming = request.form.get("Body", "").strip().lower()

    if not phone or not incoming:
        return jsonify({"status": "ignored"}), 200

    create_user(phone)
    user = get_user(phone)

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

    if incoming in ["menu", "start"]:
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
                "6️⃣ Engine Cleaner\n\n"
                "Nyora *MENU* kudzokera kumusoro"
            )
            return jsonify({"status": "ok"})

        if incoming == "2":
            send_message(phone, "🥤 Concentrate Drinks module coming soon.")
            return jsonify({"status": "ok"})

        if incoming == "3":
            send_message(phone, "💵 Full training: $10 once-off\nNyora *PAY*")
            return jsonify({"status": "ok"})

        if incoming == "4":
            send_message(phone, free_lesson())
            return jsonify({"status": "ok"})

        if incoming == "5":
            send_message(phone, "📝 Join full training — Nyora *PAY*")
            return jsonify({"status": "ok"})

        if incoming == "6":
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

        if incoming == "7":
            set_state(phone, "store")
            send_message(
                phone,
                "🛒 *ARACHIS ONLINE STORE*\n\n"
                "Available chemicals:\n"
                "- SLES\n"
                "- Caustic Soda\n"
                "- Hypochlorite\n"
                "- CDE\n"
                "- Perfumes\n\n"
                "🔍 Type the chemical name to search.\n"
                "Nyora *MENU* kudzokera."
            )
            return jsonify({"status": "ok"})

    if user["state"] == "pay_menu":

        if incoming == "1":
            set_state(phone, "awaiting_payment")
            send_message(
               phone,
               "📲 *EcoCash Payment*\n\n"
               "Dial this on your phone 👇\n\n"
               "*153*1*1*0773208904*10#\n\n"
               "👤 Recipient: *Beloved Nkomo*\n"
               "💵 Amount: *$10*\n\n"
               "✔ Enter your EcoCash PIN\n"
               "✔ After payment, reply with: *DONE*"
            )
            return jsonify({"status": "ok"})

        if incoming == "2":
           set_state(phone, "main")
           send_message(phone, main_menu())
           return jsonify({"status": "ok"})

    if user["state"] == "awaiting_payment" and incoming == "done":
        set_payment_status(phone, "awaiting_approval")
        send_message(
            phone,
            "⏳ Payment noted.\n"
            "Please wait while we verify your payment.\n\n"
            "You will be notified once approved ✅"
        )
        return jsonify({"status": "ok"})


    

    # =========================
    # ONLINE STORE
    # =========================
    if user["state"] == "store":

        for key, item in STORE_ITEMS.items():
            if key in incoming:
                send_message(
                    phone,
                    f"🧪 *{item['name']}*\n\n"
                    f"💵 Price: {item['price']}\n"
                    f"📦 Sizes: {item['sizes']}\n\n"
                    "📞 To order, reply:\n"
                    f"*ORDER {item['name']}*"
                )
                return jsonify({"status": "ok"})

        if incoming.startswith("order"):
            send_message(
                phone,
                "✅ Order received!\n\n"
                "📞 Our team will contact you shortly.\n"
                "💳 Payment: EcoCash / Cash\n"
                "🚚 Delivery available."
            )
            set_state(phone, "main")
            return jsonify({"status": "ok"})
 

    
# =========================
# OFFLINE REGISTRATION FLOW
# =========================
    if user["state"] == "offline_intro":

         if incoming == "yes":
            set_state(phone, "offline_name")
            send_message(phone, "✍🏽 Please enter your *FULL NAME*")
            return jsonify({"status": "ok"})

    if user["state"] == "offline_name":
         conn = get_db()
         c = conn.cursor()
         c.execute(
            "INSERT OR IGNORE INTO offline_registrations (phone, full_name) VALUES (?, ?)",
            (phone, incoming.title())
        )
         conn.commit()
         conn.close()

         set_state(phone, "offline_location")
         send_message(phone, "📍 Enter your *Town / Area*")
         return jsonify({"status": "ok"})

    if user["state"] == "offline_location":
         conn = get_db()
         c = conn.cursor()
         c.execute(
             "UPDATE offline_registrations SET location=? WHERE phone=?",
             (incoming.title(), phone)
         )
         conn.commit()
         conn.close()

         set_state(phone, "offline_choice")
         send_message(
             phone,
             "🧪 Choose detergent for your *FREE 10L ingredients*:\n"
             "Dishwash / Thick Bleach / Foam Bath / Pine Gel"
         )
         return jsonify({"status": "ok"})

    if user["state"] == "offline_choice":
         conn = get_db()
         c = conn.cursor()
         c.execute(
             "UPDATE offline_registrations SET detergent_choice=? WHERE phone=?",
             (incoming.title(), phone)
         )
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

    if user["state"] == "detergent_menu":

        if not user["is_paid"]:
            send_message(phone, "🔒 *Paid Members Only*\nNyora *PAY*")
            return jsonify({"status": "ok"})

        modules = {
            "1": ("dishwash", "dishwash.pdf", "🧼 DISHWASH"),
            "2": ("thick_bleach", "thick_bleach.pdf", "🧴 THICK BLEACH"),
            "3": ("foam_bath", "foam_bath.pdf", "📘 FOAM BATH"),
            "4": ("pine_gel", "pine_gel.pdf", "🌲 PINE GEL"),
            "5": ("toilet_cleaner", "toilet_cleaner.pdf", "🚽 TOILET CLEANER"),
            "6": ("engine_cleaner", "engine_cleaner.pdf", "🛠 ENGINE CLEANER")
        }

        if incoming in modules:
            module, pdf, label = modules[incoming]
            record_module_access(phone, module)
            send_pdf(phone,
                f"https://arachis-whatsapp-bot-2.onrender.com/static/lessons/{pdf}",
                label
            )
            return jsonify({"status": "ok"})
            

    # =========================
    # AI TRAINER (MODULE RESTRICTED)
    # =========================
    blocked_commands = ["1","2","3","4","5","6","menu","start","pay","admin"]

    if incoming not in blocked_commands and user["is_paid"]:
        allowed_modules = get_user_modules(phone)
        ai_answer = ai_trainer_reply(incoming, allowed_modules)
        log_activity(phone, "ai_question", incoming)
        send_message(phone, ai_answer)
        return jsonify({"status": "ok"})

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
        SELECT phone, action, details, timestamp
        FROM activity_log
        ORDER BY timestamp DESC
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
        html += f"""
        {u['phone']} | Paid: {u['is_paid']}
        | <a href='/admin/approve/{u['phone']}'>Approve</a><br>
        """

    html += "<hr><h3>📜 Activity Feed (Latest 100)</h3>"

    # ===== ACTIVITY FEED =====
    for a in activities:
        html += f"""
        <small>
        [{a['timestamp']}] <b>{a['phone']}</b> → {a['action']} ({a['details']})
        </small><br>
        """

    return html

@app.route("/paynow/callback", methods=["POST"])
def paynow_callback():
    reference = request.form.get("reference")
    status = request.form.get("status")
    phone = request.form.get("phone")

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
    mark_paid(phone)
    return redirect(url_for("admin_dashboard"))

@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))











































































































