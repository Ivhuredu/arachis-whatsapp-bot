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

ADMIN_NUMBER = "+263773208904"

UPLOAD_FOLDER = "static/lessons"
ALLOWED_EXTENSIONS = {"pdf"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

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

init_db()

# =========================
# HELPERS
# =========================
def normalize_phone(phone):
    phone = phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

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
        "6️⃣ Taura na Trainer"
    )

# =========================
# WEBHOOK (UNCHANGED LOGIC)
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    phone = normalize_phone(
        request.form.get("From", "").replace("whatsapp:", "")
    )
    incoming = request.form.get("Body", "").strip().lower()

    if not phone or not incoming:
        return jsonify({"status": "ignored"}), 200

    create_user(phone)
    user = get_user(phone)

    if incoming == "admin" and phone == ADMIN_NUMBER:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_paid=1")
        paid = c.fetchone()[0]
        conn.close()

        send_message(phone, f"📊 USERS: {total}\n💰 PAID: {paid}")
        return jsonify({"status": "ok"})

    if incoming.startswith("approve ") and phone == ADMIN_NUMBER:
        target = normalize_phone(incoming.replace("approve ", ""))
        mark_paid(target)
        send_message(target, "🎉 Approved. Full access granted.")
        return jsonify({"status": "ok"})

    if incoming in ["menu", "start"]:
        set_state(phone, "main")
        send_message(phone, main_menu())
        return jsonify({"status": "ok"})

    if user["state"] == "main" and incoming == "1":
        set_state(phone, "detergent_menu")
        send_message(phone, "1️⃣ Dishwash\n2️⃣ Thick Bleach")
        return jsonify({"status": "ok"})

    if user["state"] == "detergent_menu":

        if not user["is_paid"]:
            send_message(phone, "🔒 Paid only. Send PAY.")
            return jsonify({"status": "ok"})

        if incoming == "1":
            send_pdf(
                phone,
                f"{request.url_root}static/lessons/dishwash.pdf",
                "🧼 DISHWASH MODULE"
            )
            return jsonify({"status": "ok"})

        if incoming == "2":
            send_pdf(
                phone,
                f"{request.url_root}static/lessons/thick_bleach.pdf",
                "🧴 THICK BLEACH MODULE"
            )
            return jsonify({"status": "ok"})

    send_message(phone, "Nyora MENU")
    return jsonify({"status": "ok"})

# =========================
# ADMIN DASHBOARD + PDF UPLOAD
# =========================
@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():

    if request.method == "POST":
        if "file" not in request.files:
            return "No file selected"

        file = request.files["file"]

        if file.filename == "":
            return "No filename"

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            return redirect(url_for("admin_dashboard"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone, is_paid FROM users")
    users = c.fetchall()
    conn.close()

    html = """
    <h2>Arachis Admin Dashboard</h2>

    <h3>Upload Lesson PDF</h3>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file" accept="application/pdf" required>
        <button type="submit">Upload PDF</button>
    </form>

    <h3>Students</h3>
    <table border="1" cellpadding="6">
    <tr><th>Phone</th><th>Paid</th><th>Action</th></tr>
    """

    for u in users:
        html += f"""
        <tr>
            <td>{u['phone']}</td>
            <td>{u['is_paid']}</td>
            <td><a href="/admin/approve/{u['phone']}">Approve</a></td>
        </tr>
        """

    html += "</table>"
    return html

@app.route("/admin/approve/<phone>")
def admin_approve(phone):
    mark_paid(phone)
    return redirect(url_for("admin_dashboard"))

# =========================
# HEALTH CHECK
# =========================
@app.route("/")
def home():
    return "Arachis WhatsApp Bot Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

















































