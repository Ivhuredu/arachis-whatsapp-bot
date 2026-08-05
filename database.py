import os
import psycopg2
from psycopg2 import pool
from urllib.parse import urlparse

DATABASE_POOL = None

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
    c.execute("""
    CREATE TABLE IF NOT EXISTS training_events (
        id SERIAL PRIMARY KEY,

        title TEXT NOT NULL,
        event_type TEXT DEFAULT 'practical',

        city TEXT NOT NULL,
        venue TEXT NOT NULL,
        venue_address TEXT,

        event_date DATE NOT NULL,
        start_time TEXT,
        end_time TEXT,

        fee REAL DEFAULT 0,
        deposit REAL DEFAULT 0,

        products_taught TEXT,

        registration_status TEXT DEFAULT 'open',

        total_seats INTEGER DEFAULT 0,
        booked_seats INTEGER DEFAULT 0,

        registration_deadline DATE,

        notes TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("SELECT COUNT(*) FROM training_events")

    if c.fetchone()[0] == 0:

        c.execute("""
        INSERT INTO training_events
        (
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

        VALUES

        (
            'Bulawayo Practical Training',

            'Bulawayo',

            'Cillas Conference Centre',

            '2026-08-22',

            '09:00',

            '14:00',

            20,

            5,

            'Dishwash, Pine Gel, Foam Bath, Perfumes, Spices',

            80
        ),

        (
            'Harare Practical Training',

            'Harare',

            'Karigamombe Centre',

            '2026-09-05',

            '09:00',

            '14:00',

            20,

            5,

            'Metal Degreaser, Pine Gel, Foam Bath, Perfumes, Spices',

            80
        )
        """)
        
    c.execute("""
    CREATE TABLE IF NOT EXISTS customer_profiles (

        phone TEXT PRIMARY KEY,

        full_name TEXT,
        location TEXT,
        language TEXT DEFAULT 'english',

        business_stage TEXT DEFAULT 'planning',
        experience_level TEXT DEFAULT 'beginner',

        business_type TEXT,
        capital REAL,

        interests TEXT,
        goals TEXT,
        problems TEXT,
        equipment TEXT,

        preferred_department TEXT,

        ai_summary TEXT,

        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # ===============================
    # Upgrade customer_profiles table
    # ===============================

    try:
        c.execute("ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS full_name TEXT")
    except Exception:
        pass

    try:
        c.execute("ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS location TEXT")
    except Exception:
        pass

    try:
        c.execute("ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'english'")
    except Exception:
        pass

    try:
        c.execute("ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS business_stage TEXT DEFAULT 'planning'")
    except Exception:
        pass

    try:
        c.execute("ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS experience_level TEXT DEFAULT 'beginner'")
    except Exception:
        pass

    try:
        c.execute("ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS business_type TEXT")
    except Exception:
        pass

    try:
        c.execute("ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS capital REAL")
    except Exception:
        pass
    
    
    conn.commit()
    DATABASE_POOL.putconn(conn)
