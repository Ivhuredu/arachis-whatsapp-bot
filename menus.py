from config import *

from services import *

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
def main_menu(user=None):
    """
    Main conversational dashboard.
    AI-first, task-oriented navigation.
    """

    name = ""

    if user:
        name = (
            user.get("full_name")
            or user.get("name")
            or ""
        )

    greeting = (
        f"👋 Hello *{name}*!\n\n"
        if name
        else
        "👋 Hello!\n\n"
    )

    return (
        "🏠 *ARACHIS MANUFACTURING AI*\n\n"

        + greeting +

        "I'm your virtual manufacturing and business assistant.\n\n"

        "*How can I help you today?*\n\n"

        "1️⃣ I want to *learn manufacturing*\n"
        "2️⃣ I want to *make a product*\n"
        "3️⃣ I want to *grow my business*\n"
        "4️⃣ I want to *buy or sell*\n"
        "5️⃣ I need *business tools*\n"
        "6️⃣ *My account*\n\n"

        "🤖 *Or simply ask me your question naturally.*\n\n"

        "*For example:*\n"
        "• How do I make dishwash?\n"
        "• Calculate a 200L batch.\n"
        "• Find SLES suppliers in Harare.\n"
        "• When is the next practical training?\n"
        "• Help me start a business with $100.\n\n"

        "💡 You can type *MENU* anytime to return here."
    )

def build_learn_menu():
    return (
        "📚 *MY LEARNING*\n\n"

        "Welcome to your Arachis learning centre.\n\n"

        "Choose an option:\n\n"

        "1️⃣ Open My Lessons\n"
        "2️⃣ Ask AI Trainer\n"
        "3️⃣ Practical Training\n"
        "4️⃣ Download Arachis App\n"
        "5️⃣ Upgrade My Training\n\n"

        "💬 You can also ask naturally:\n"
        "• Continue my Pine Gel lesson.\n"
        "• Explain CMC.\n"
        "• Test my knowledge.\n"
        "• When is the next practical training?\n\n"

        "↩ Type *MENU* to return."
    )

def build_manufacture_menu():
    return (
        "🏭 *MAKE A PRODUCT*\n\n"

        "What would you like to do?\n\n"

        "1️⃣ Product Formulas\n"
        "2️⃣ Batch Calculator\n"
        "3️⃣ Troubleshoot a Product\n"
        "4️⃣ Quality Control\n"
        "5️⃣ Analyse a Product Photo\n"
        "6️⃣ Ingredients Guide\n\n"

        "💬 Or ask:\n"
        "• My bleach is separating.\n"
        "• Calculate a 250L batch.\n"
        "• Analyse this product.\n\n"

        "↩ Type *MENU* to return."
    )

def build_business_menu():
    return (
        "💼 *GROW MY BUSINESS*\n\n"

        "How can I help your business?\n\n"

        "1️⃣ Start a Manufacturing Business\n"
        "2️⃣ Pricing & Profit\n"
        "3️⃣ Marketing & Advertising\n"
        "4️⃣ Branding\n"
        "5️⃣ Business Advisor\n"
        "6️⃣ Funding & Growth\n\n"

        "💬 Or ask:\n"
        "• Help me start with $100.\n"
        "• Price my dishwash.\n"
        "• Create a Facebook advert.\n\n"

        "↩ Type *MENU* to return."
    )

def build_marketplace_menu():
    return (
        "🛒 *BUY OR SELL*\n\n"

        "Choose an option:\n\n"

        "1️⃣ Buy Ingredients\n"
        "2️⃣ Find Suppliers\n"
        "3️⃣ Sell My Products\n"
        "4️⃣ Packaging\n"
        "5️⃣ Machinery & Equipment\n"
        "6️⃣ My Marketplace\n\n"

        "💬 Or ask:\n"
        "• Find SLES in Harare.\n"
        "• I want to sell Pine Gel.\n"
        "• Where can I buy bottles?\n\n"

        "↩ Type *MENU* to return."
    )

def build_tools_menu():
    return (
        "🧰 *BUSINESS TOOLS*\n\n"

        "Choose a tool:\n\n"

        "1️⃣ Profit Calculator\n"
        "2️⃣ Batch Calculator\n"
        "3️⃣ Unit Converter\n"
        "4️⃣ Product Costing\n"
        "5️⃣ AI Assistant\n"
        "6️⃣ Downloads\n\n"

        "💬 Or ask:\n"
        "• Calculate my profit.\n"
        "• Convert litres to kilograms.\n\n"

        "↩ Type *MENU* to return."
    )

def build_account_menu():
    return (
        "👤 *MY ACCOUNT*\n\n"

        "Manage your account:\n\n"

        "1️⃣ My Dashboard\n"
        "2️⃣ My Subscription\n"
        "3️⃣ Upgrade My Plan\n"
        "4️⃣ Payment History\n"
        "5️⃣ Downloads\n"
        "6️⃣ Settings\n\n"

        "💬 Or ask:\n"
        "• What package do I have?\n"
        "• Upgrade my account.\n\n"

        "↩ Type *MENU* to return."
    )




