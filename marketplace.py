from database import get_db, DATABASE_POOL

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
        pid,
        category,
        name,
        description,
        price,
        unit,
        seller_name,
        seller_phone,
        seller_location,
        image_url,
        image_media_id,
        status,
    ) = product

    save_marketplace_temp(phone, f"selected_product:{pid}")

    caption = f"{name} | {price} {unit}"

    if image_media_id:
        send_image_by_id(phone, image_media_id, caption)

    elif image_url:
        send_image(phone, image_url, caption)

    text = (
        f"🛒 *{name}*\n\n"
        f"📂 Category: {category}\n"
        f"💵 Price: {price} {unit}\n"
        f"📍 Location: {seller_location}\n"
        f"👤 Seller: {seller_name}\n\n"
        f"{description}\n\n"
        "Reply:\n"
        "➕ *ADD* - Add to cart\n"
        "🛒 *CART* - View cart\n"
        "↩ *MARKET* - Back to marketplace"
    )

    send_message(phone, text)


def add_to_marketplace_cart(phone, product_id, qty=1):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO marketplace_cart(phone, product_id, quantity)
        VALUES (%s,%s,%s)
        ON CONFLICT(phone, product_id)
        DO UPDATE SET quantity = marketplace_cart.quantity + EXCLUDED.quantity
    """, (phone, product_id, qty))

    conn.commit()
    DATABASE_POOL.putconn(conn)


def get_marketplace_cart(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            p.id,
            p.name,
            p.price,
            p.unit,
            p.seller_name,
            c.quantity
        FROM marketplace_cart c
        JOIN marketplace_products p
            ON c.product_id=p.id
        WHERE c.phone=%s
        ORDER BY p.name
    """, (phone,))

    rows = c.fetchall()

    DATABASE_POOL.putconn(conn)

    return rows


def clear_marketplace_cart(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute(
        "DELETE FROM marketplace_cart WHERE phone=%s",
        (phone,)
    )

    conn.commit()
    DATABASE_POOL.putconn(conn)


def build_cart_message(phone):
    cart = get_marketplace_cart(phone)

    if not cart:
        return (
            "🛒 *YOUR CART*\n\n"
            "Your cart is empty.\n\n"
            "Type *MARKET* to continue shopping."
        )

    text = "🛒 *YOUR CART*\n\n"

    for i, item in enumerate(cart, start=1):
        pid, name, price, unit, seller, qty = item

        text += (
            f"{i}. {name}\n"
            f"Qty: {qty}\n"
            f"Price: {price} {unit}\n"
            f"Seller: {seller}\n\n"
        )

    text += (
        "Reply:\n"
        "*ORDER* - Checkout\n"
        "*CLEAR* - Empty cart\n"
        "*MARKET* - Continue shopping"
    )

    return text
