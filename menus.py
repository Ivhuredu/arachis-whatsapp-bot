from config import *

from services import (
    get_user,
    get_custom_modules,
    get_allowed_modules_for_user,
    save_marketplace_temp,
    get_featured_products,
)

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
