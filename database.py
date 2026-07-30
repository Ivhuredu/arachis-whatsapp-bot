import psycopg2
from psycopg2 import pool
from urllib.parse import urlparse

from config import DATABASE_URL

DATABASE_POOL = None


# ==========================================
# CONNECTION POOL
# ==========================================

def get_db():
    global DATABASE_POOL

    if DATABASE_POOL is None:

        url = urlparse(DATABASE_URL)

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


def release_db(conn):
    DATABASE_POOL.putconn(conn)


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():

    conn = get_db()
    c = conn.cursor()

    # ---------------- USERS ----------------

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        phone TEXT UNIQUE,
        state TEXT DEFAULT 'main',
        payment_status TEXT DEFAULT 'none',
        is_paid INTEGER DEFAULT 0
    )
    """)

    # ------------- MODULE ACCESS -------------

    c.execute("""
    CREATE TABLE IF NOT EXISTS module_access (
        id SERIAL PRIMARY KEY,
        phone TEXT,
        module TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(phone,module)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS custom_module_access (
        id SERIAL PRIMARY KEY,
        phone TEXT,
        module TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(phone,module)
    )
    """)

    # ---------------- TEMP ORDERS ----------------

    c.execute("""
    CREATE TABLE IF NOT EXISTS temp_orders (
        phone TEXT PRIMARY KEY,
        item TEXT,
        quantity INTEGER DEFAULT 1
    )
    """)

    # ---------------- OFFLINE REGISTRATION ----------------

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

    # ---------------- ACTIVITY LOG ----------------

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

    # ---------------- LESSON CONTENT ----------------

    c.execute("""
    CREATE TABLE IF NOT EXISTS lesson_content (
        id SERIAL PRIMARY KEY,
        module TEXT UNIQUE,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ---------------- STUDENT METRICS ----------------

    c.execute("""
    CREATE TABLE IF NOT EXISTS student_metrics (
        phone TEXT PRIMARY KEY,
        total_messages INTEGER DEFAULT 0,
        ai_questions INTEGER DEFAULT 0,
        completed_lessons INTEGER DEFAULT 0,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    release_db(conn)
# ==========================================
# USER HELPERS
# ==========================================

def create_user(phone):
    conn = get_db()
    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO users (phone)
            VALUES (%s)
            ON CONFLICT (phone) DO NOTHING
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


def get_user(phone):
    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT phone,
                   state,
                   payment_status,
                   is_paid,
                   package
            FROM users
            WHERE phone=%s
        """, (phone,))

        row = c.fetchone()

        if not row:
            return None

        return {
            "phone": row[0],
            "state": row[1],
            "payment_status": row[2],
            "is_paid": row[3],
            "package": row[4]
        }

    finally:
        release_db(conn)


def set_state(phone, state):
    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET state=%s
            WHERE phone=%s
        """, (state, phone))

        conn.commit()

    finally:
        release_db(conn)

    log_activity(phone, "state_change", state)


def get_unpaid_active_users():

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT u.phone
            FROM users u
            LEFT JOIN student_metrics s
                ON u.phone=s.phone
            WHERE u.is_paid=0
            AND (
                s.total_messages > 2
                OR s.modules_opened > 0
            )
            AND (
                u.last_followup IS NULL
                OR u.last_followup < NOW() - INTERVAL '24 HOURS'
            )
        """)

        rows = c.fetchall()

        return [r[0] for r in rows]

    finally:
        release_db(conn)


def update_metrics(phone, event):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO student_metrics(phone)
            VALUES(%s)
            ON CONFLICT(phone) DO NOTHING
        """, (phone,))

        if event == "message":
            c.execute("""
                UPDATE student_metrics
                SET total_messages=total_messages+1,
                    last_active=CURRENT_TIMESTAMP
                WHERE phone=%s
            """, (phone,))

        elif event == "module":
            c.execute("""
                UPDATE student_metrics
                SET modules_opened=modules_opened+1,
                    last_active=CURRENT_TIMESTAMP
                WHERE phone=%s
            """, (phone,))

        elif event == "ai":
            c.execute("""
                UPDATE student_metrics
                SET ai_questions=ai_questions+1,
                    last_active=CURRENT_TIMESTAMP
                WHERE phone=%s
            """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


def log_activity(phone, action, details=""):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO activity_log(
                phone,
                action,
                details
            )
            VALUES(%s,%s,%s)
        """, (phone, action, details))

        conn.commit()

    finally:
        release_db(conn)

# ==========================================
# PAYMENT / ACCESS HELPERS
# ==========================================

def set_payment_status(phone, status):
    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET payment_status=%s
            WHERE phone=%s
        """, (status, phone))

        conn.commit()

    finally:
        release_db(conn)


def mark_paid(phone):
    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET is_paid=1,
                payment_status='approved'
            WHERE phone=%s
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


def revoke_access(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET is_paid=0,
                payment_status='revoked',
                package='none',
                active_module=NULL
            WHERE phone=%s
        """, (phone,))

        c.execute("""
            DELETE FROM module_access
            WHERE phone=%s
        """, (phone,))

        c.execute("""
            DELETE FROM custom_module_access
            WHERE phone=%s
        """, (phone,))

        c.execute("""
            DELETE FROM ai_memory
            WHERE phone=%s
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)

    log_activity(phone, "access_revoked", "admin")


# ==========================================
# MODULE ACCESS
# ==========================================

def record_module_access(phone, module):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO module_access(phone,module)
            VALUES(%s,%s)
            ON CONFLICT(phone,module) DO NOTHING
        """, (phone, module))

        conn.commit()

    finally:
        release_db(conn)


def add_custom_module(phone, module):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO custom_module_access(phone,module)
            VALUES(%s,%s)
            ON CONFLICT(phone,module) DO NOTHING
        """, (phone, module))

        conn.commit()

    finally:
        release_db(conn)


def get_custom_modules(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT module
            FROM custom_module_access
            WHERE phone=%s
            ORDER BY created_at ASC
        """, (phone,))

        return [r[0] for r in c.fetchall()]

    finally:
        release_db(conn)


def clear_custom_modules(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            DELETE FROM custom_module_access
            WHERE phone=%s
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


# ==========================================
# AI LIMITS
# ==========================================

def ai_questions_today(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT COUNT(*)
            FROM activity_log
            WHERE phone=%s
            AND action='ai_question'
            AND DATE(created_at)=CURRENT_DATE
        """, (phone,))

        return c.fetchone()[0]

    finally:
        release_db(conn)


# ==========================================
# MESSAGE DEDUPLICATION
# ==========================================

def already_processed_message(message_id, phone, incoming):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO processed_messages
            (
                whatsapp_message_id,
                phone,
                incoming
            )
            VALUES(%s,%s,%s)
            ON CONFLICT(whatsapp_message_id)
            DO NOTHING
            RETURNING whatsapp_message_id
        """, (message_id, phone, incoming))

        inserted = c.fetchone()

        conn.commit()

        return inserted is None

    except Exception as e:

        print("DEDUP ERROR:", e)

        conn.rollback()

        return False

    finally:
        release_db(conn)

# ==========================================
# PAYMENT / ACCESS HELPERS
# ==========================================

def set_payment_status(phone, status):
    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET payment_status=%s
            WHERE phone=%s
        """, (status, phone))

        conn.commit()

    finally:
        release_db(conn)


def mark_paid(phone):
    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET is_paid=1,
                payment_status='approved'
            WHERE phone=%s
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


def revoke_access(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET is_paid=0,
                payment_status='revoked',
                package='none',
                active_module=NULL
            WHERE phone=%s
        """, (phone,))

        c.execute("""
            DELETE FROM module_access
            WHERE phone=%s
        """, (phone,))

        c.execute("""
            DELETE FROM custom_module_access
            WHERE phone=%s
        """, (phone,))

        c.execute("""
            DELETE FROM ai_memory
            WHERE phone=%s
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)

    log_activity(phone, "access_revoked", "admin")


# ==========================================
# MODULE ACCESS
# ==========================================

def record_module_access(phone, module):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO module_access(phone,module)
            VALUES(%s,%s)
            ON CONFLICT(phone,module) DO NOTHING
        """, (phone, module))

        conn.commit()

    finally:
        release_db(conn)


def add_custom_module(phone, module):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO custom_module_access(phone,module)
            VALUES(%s,%s)
            ON CONFLICT(phone,module) DO NOTHING
        """, (phone, module))

        conn.commit()

    finally:
        release_db(conn)


def get_custom_modules(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT module
            FROM custom_module_access
            WHERE phone=%s
            ORDER BY created_at ASC
        """, (phone,))

        return [r[0] for r in c.fetchall()]

    finally:
        release_db(conn)


def clear_custom_modules(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            DELETE FROM custom_module_access
            WHERE phone=%s
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


# ==========================================
# AI LIMITS
# ==========================================

def ai_questions_today(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT COUNT(*)
            FROM activity_log
            WHERE phone=%s
            AND action='ai_question'
            AND DATE(created_at)=CURRENT_DATE
        """, (phone,))

        return c.fetchone()[0]

    finally:
        release_db(conn)


# ==========================================
# MESSAGE DEDUPLICATION
# ==========================================

def already_processed_message(message_id, phone, incoming):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO processed_messages
            (
                whatsapp_message_id,
                phone,
                incoming
            )
            VALUES(%s,%s,%s)
            ON CONFLICT(whatsapp_message_id)
            DO NOTHING
            RETURNING whatsapp_message_id
        """, (message_id, phone, incoming))

        inserted = c.fetchone()

        conn.commit()

        return inserted is None

    except Exception as e:

        print("DEDUP ERROR:", e)

        conn.rollback()

        return False

    finally:
        release_db(conn)

# ==========================================
# AI MEMORY
# ==========================================

MAX_MEMORY_MESSAGES = 4


def save_memory(phone, module, role, message):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO ai_memory
            (
                phone,
                module,
                role,
                message
            )
            VALUES(%s,%s,%s,%s)
        """, (phone, module, role, message))

        c.execute("""
            DELETE FROM ai_memory
            WHERE id NOT IN
            (
                SELECT id
                FROM ai_memory
                WHERE phone=%s
                AND module=%s
                ORDER BY created_at DESC
                LIMIT %s
            )
            AND phone=%s
            AND module=%s
        """, (
            phone,
            module,
            MAX_MEMORY_MESSAGES,
            phone,
            module
        ))

        conn.commit()

    finally:
        release_db(conn)


def get_memory(phone, module):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT role,
                   message
            FROM ai_memory
            WHERE phone=%s
            AND module=%s
            ORDER BY created_at ASC
        """, (phone, module))

        rows = c.fetchall()

        memory = []

        for role, message in rows:
            memory.append({
                "role": role,
                "content": message
            })

        return memory

    finally:
        release_db(conn)


def clear_memory(phone, module=None):

    conn = get_db()

    try:
        c = conn.cursor()

        if module:

            c.execute("""
                DELETE FROM ai_memory
                WHERE phone=%s
                AND module=%s
            """, (phone, module))

        else:

            c.execute("""
                DELETE FROM ai_memory
                WHERE phone=%s
            """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


# ==========================================
# LESSON DATABASE
# ==========================================

def save_lesson_content(module, content):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO lesson_content
            (
                module,
                content
            )
            VALUES(%s,%s)
            ON CONFLICT(module)
            DO UPDATE
            SET content=EXCLUDED.content
        """, (module, content))

        conn.commit()

    finally:
        release_db(conn)


def get_lesson_content(module):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT content
            FROM lesson_content
            WHERE module=%s
        """, (module,))

        row = c.fetchone()

        if row:
            return row[0]

        return ""

    finally:
        release_db(conn)


def delete_lesson(module):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            DELETE FROM lesson_content
            WHERE module=%s
        """, (module,))

        conn.commit()

    finally:
        release_db(conn)


def list_lessons():

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT module
            FROM lesson_content
            ORDER BY module
        """)

        return [r[0] for r in c.fetchall()]

    finally:
        release_db(conn)

# ==========================================
# PDF / LESSON CONTENT HELPERS
# ==========================================

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

    # remove invisible control characters except newline/tab
    text = "".join(
        ch for ch in text
        if ord(ch) >= 32 or ch in "\n\t"
    )

    # compress whitespace
    text = " ".join(text.split())

    return text


def save_pdf_to_db(module_name, pdf_filename):

    raw_text = extract_pdf_text(pdf_filename)
    text = clean_pdf_text(raw_text)

    if not text:
        print("No text extracted")
        return

    conn = get_db()

    try:
        c = conn.cursor()

        text = text[:15000]

        c.execute("""
            INSERT INTO lesson_content
            (module, content)
            VALUES (%s, %s)
            ON CONFLICT (module)
            DO UPDATE
            SET content = EXCLUDED.content
        """, (module_name, text))

        conn.commit()

        print(f"Saved {module_name} to database")

    finally:
        release_db(conn)


def auto_sync_lessons():

    folder = "static/lessons"

    if not os.path.exists(folder):
        return

    conn = get_db()

    try:
        c = conn.cursor()

        for file in os.listdir(folder):

            if not file.endswith(".pdf"):
                continue

            module = file.replace(".pdf", "")

            c.execute("""
                SELECT 1
                FROM lesson_content
                WHERE module=%s
            """, (module,))

            exists = c.fetchone()

            if not exists:
                print("Auto learning lesson:", module)
                save_pdf_to_db(module, file)

    finally:
        release_db(conn)


def get_relevant_lesson_chunk(module, question):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT content
            FROM lesson_content
            WHERE module=%s
        """, (module,))

        row = c.fetchone()

        if not row:
            return ""

        return row[0]

    finally:
        release_db(conn)

# ==========================================
# APP INSTALLS / DEVICE HELPERS
# ==========================================

def register_app_install(
    device_id,
    phone,
    app_version,
    device_model
):

    if not device_id:
        return

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO app_installs
            (
                device_id,
                phone,
                app_version,
                device_model
            )
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (device_id)
            DO UPDATE SET
                phone = COALESCE(
                    NULLIF(EXCLUDED.phone,''),
                    app_installs.phone
                ),
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

    finally:
        release_db(conn)


def get_app_install_stats():

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT COUNT(*)
            FROM app_installs
        """)
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
            SELECT
                device_id,
                phone,
                app_version,
                device_model,
                first_opened_at,
                last_opened_at,
                open_count
            FROM app_installs
            ORDER BY last_opened_at DESC
            LIMIT 50
        """)

        recent_installs = c.fetchall()

        return {
            "total_installs": total_installs,
            "active_today": active_today,
            "logged_in_devices": logged_in_devices,
            "recent_installs": recent_installs
        }

    finally:
        release_db(conn)


def get_device_lock(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT
                device_id,
                device_model,
                device_locked_at
            FROM users
            WHERE phone=%s
        """, (phone,))

        return c.fetchone()

    finally:
        release_db(conn)


def update_device_lock(phone, device_id, device_model):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET
                device_id=%s,
                device_model=%s,
                device_locked_at=CURRENT_TIMESTAMP
            WHERE phone=%s
        """, (
            device_id,
            device_model,
            phone
        ))

        conn.commit()

    finally:
        release_db(conn)


def can_change_device(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT
            CASE
                WHEN device_locked_at IS NULL THEN TRUE
                WHEN device_locked_at < NOW() - INTERVAL '30 DAYS'
                    THEN TRUE
                ELSE FALSE
            END
            FROM users
            WHERE phone=%s
        """, (phone,))

        row = c.fetchone()

        if not row:
            return False

        return row[0]

    finally:
        release_db(conn)

# ==========================================
# MARKETPLACE TEMP DATA
# ==========================================

def save_marketplace_temp(phone, data):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO marketplace_temp
            (phone, data)
            VALUES (%s, %s)
            ON CONFLICT (phone)
            DO UPDATE SET
                data = EXCLUDED.data,
                created_at = CURRENT_TIMESTAMP
        """, (phone, data))

        conn.commit()

    finally:
        release_db(conn)


def get_marketplace_temp(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT data
            FROM marketplace_temp
            WHERE phone=%s
        """, (phone,))

        row = c.fetchone()

        if row:
            return row[0]

        return None

    finally:
        release_db(conn)


def clear_marketplace_temp(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            DELETE FROM marketplace_temp
            WHERE phone=%s
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


# ==========================================
# MARKETPLACE CART
# ==========================================

def save_cart(phone, cart):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO marketplace_carts
            (phone, cart)
            VALUES (%s, %s)
            ON CONFLICT (phone)
            DO UPDATE SET
                cart = EXCLUDED.cart,
                updated_at = CURRENT_TIMESTAMP
        """, (phone, cart))

        conn.commit()

    finally:
        release_db(conn)


def get_cart(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT cart
            FROM marketplace_carts
            WHERE phone=%s
        """, (phone,))

        row = c.fetchone()

        if row:
            return row[0]

        return None

    finally:
        release_db(conn)


def clear_cart(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            DELETE FROM marketplace_carts
            WHERE phone=%s
        """, (phone,))

        conn.commit()

    finally:
        release_db(conn)


# ==========================================
# INGREDIENT PRICES
# ==========================================

def save_ingredient_price(name, price_per_unit, unit):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO ingredient_prices
            (name, price_per_unit, unit)
            VALUES (%s, %s, %s)
            ON CONFLICT (name)
            DO UPDATE SET
                price_per_unit = EXCLUDED.price_per_unit,
                unit = EXCLUDED.unit
        """, (name, price_per_unit, unit))

        conn.commit()

    finally:
        release_db(conn)


def get_all_prices():

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT
                name,
                price_per_unit,
                unit
            FROM ingredient_prices
            ORDER BY name
        """)

        rows = c.fetchall()

        return "\n".join(
            f"{name}: ${price}/{unit}"
            for name, price, unit in rows
        )

    finally:
        release_db(conn)

# ==========================================
# ACTIVITY LOG
# ==========================================

def log_activity(phone, action, details=""):

    details = safe_text(details)[:1000]

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO activity_log
            (phone, action, details)
            VALUES (%s, %s, %s)
        """, (phone, action, details))

        conn.commit()

    finally:
        release_db(conn)


# ==========================================
# STUDENT METRICS
# ==========================================

def update_metrics(phone, event):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            INSERT INTO student_metrics (phone)
            VALUES (%s)
            ON CONFLICT (phone)
            DO NOTHING
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

    finally:
        release_db(conn)


def get_student_metrics(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT
                total_messages,
                ai_questions,
                modules_opened,
                last_active
            FROM student_metrics
            WHERE phone=%s
        """, (phone,))

        return c.fetchone()

    finally:
        release_db(conn)


def get_top_students(limit=20):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT
                phone,
                total_messages,
                ai_questions,
                modules_opened,
                last_active
            FROM student_metrics
            ORDER BY
                ai_questions DESC,
                total_messages DESC
            LIMIT %s
        """, (limit,))

        return c.fetchall()

    finally:
        release_db(conn)


# ==========================================
# USER HELPERS
# ==========================================

def set_active_module(phone, module):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET active_module=%s
            WHERE phone=%s
        """, (module, phone))

        conn.commit()

    finally:
        release_db(conn)


def get_active_module(phone):

    conn = get_db()

    try:
        c = conn.cursor()

        c.execute("""
            SELECT active_module
            FROM users
            WHERE phone=%s
        """, (phone,))

        row = c.fetchone()

        if row:
            return row[0]

        return None

    finally:
        release_db(conn)

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
        "blocked_attempts": blocked_attempts,
    }

   
