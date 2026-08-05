from database import get_db, release_db
from config import (
    PACKAGES,
    DETERGENT_MODULES,
    BEVERAGE_MODULES,
    SPICE_MODULES,
    ADVANCED_MODULES,
)
from utils import safe_text

def create_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (phone)
        VALUES (%s)
        ON CONFLICT (phone) DO NOTHING
    """, (phone,))
    conn.commit()
    release_db(conn)
  
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
    release_db(conn)

def record_module_access(phone, module):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO module_access (phone, module)
        VALUES (%s, %s)
        ON CONFLICT (phone, module) DO NOTHING
    """, (phone, module))
    conn.commit()
    release_db(conn)

def add_custom_module(phone, module):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO custom_module_access (phone, module)
        VALUES (%s, %s)
        ON CONFLICT (phone, module) DO NOTHING
    """, (phone, module))

    conn.commit()
    release_db(conn)

def get_custom_modules(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT module FROM custom_module_access
        WHERE phone=%s
        ORDER BY created_at ASC
    """, (phone,))

    rows = c.fetchall()
    release_db(conn)

    return [r[0] for r in rows]

def clear_custom_modules(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM custom_module_access WHERE phone=%s", (phone,))

    conn.commit()
    release_db(conn)

def log_activity(phone, action, details=""):
    details = safe_text(details)[:1000]
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO activity_log (phone, action, details)
        VALUES (%s, %s, %s)
    """, (phone, action, details))
    conn.commit()
    release_db(conn)
    
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

    release_db(conn)

    return {
        "total_installs": total_installs,
        "active_today": active_today,
        "logged_in_devices": logged_in_devices,
        "recent_installs": recent_installs
    }

def get_user(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone, state, payment_status, is_paid, package FROM users WHERE phone=%s", (phone,))
    row = c.fetchone()
    release_db(conn)

    if not row:
        return None

    return {
        "phone": row[0],
        "state": row[1],
        "payment_status": row[2],
        "is_paid": row[3],
        "package": row[4]
    }

    return [r[0] for r in rows]

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
    release_db(conn)

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
    release_db(conn)

    log_activity(phone, "state_change", state)

def set_payment_status(phone, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET payment_status=%s WHERE phone=%s", (status, phone))
    conn.commit()
    release_db(conn)

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

    release_db(conn)
    
    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "module_opens": module_opens,
        "ai_questions": ai_questions,
        "blocked_attempts": blocked_attempts
    }

def get_detergent_modules():

    modules = load_lessons()

    drinks = get_drink_modules()

    return [k for k in modules if k not in drinks]

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
    release_db(conn)

def get_marketplace_temp(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT data FROM marketplace_temp WHERE phone=%s", (phone,))
    row = c.fetchone()

    release_db(conn)

    return row[0] if row else ""

def clear_marketplace_temp(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM marketplace_temp WHERE phone=%s", (phone,))

    conn.commit()
    release_db(conn)


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
        release_db(conn)
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
    release_db(conn)


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
    release_db(conn)

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
    release_db(conn)

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
    release_db(conn)

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
    release_db(conn)

    return row

    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "module_opens": module_opens,
        "ai_questions": ai_questions,
        "blocked_attempts": blocked_attempts
    }

def get_user_role(phone):

    user = get_user(phone)

    if user.get("is_admin"):
        return "admin"

    if user.get("is_agent"):
        return "agent"

    if user.get("package"):
        return "student"

    return "guest"

def get_unlocked_lesson_count(phone):

    conn = get_db()
    c = conn.cursor()

    c.execute(
        """
        SELECT COUNT(*)
        FROM module_access
        WHERE phone=%s
        """,
        (phone,)
    )

    count = c.fetchone()[0]

    release_db(conn)

    return count
