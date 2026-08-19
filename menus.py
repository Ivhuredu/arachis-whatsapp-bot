from config import *

from services import *

# ==========================================
# USER TYPE
# ==========================================

def get_menu_user_type(phone):
    """
    Determine the WhatsApp user's access level.

    ADMIN    = admin phone
    STUDENT  = registered + payment approved
    GUEST    = everyone else
    """

    try:

        phone = normalize_phone(phone)

        # ADMIN
        if is_admin_phone(phone):
            return "admin"

        # USER
        user = get_user(phone)

        # GUEST
        if not user:
            return "guest"

        # PAYMENT NOT APPROVED
        if not user.get("is_paid"):
            return "guest"

        # PAID STUDENT
        return "student"

    except Exception as e:

        print("MENU USER TYPE ERROR:", e)

        return "guest"

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
def main_menu(user=None, phone=None):
    """
    Main Arachis menu.

    Shows different navigation depending on:
    - Guest
    - Student
    - Admin
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

    # ==========================================
    # DETERMINE USER TYPE
    # ==========================================

    user_type = "guest"

    if phone:

        user_type = get_menu_user_type(phone)

    elif user:

        # Fallback if phone was not supplied.
        # Paid users are treated as students.
        if user.get("is_paid"):
            user_type = "student"

    # ==========================================
    # ADMIN
    # ==========================================

    if user_type == "admin":

        return (
            "👑 *ARACHIS ADMIN*\n\n"
            + greeting +
            "Welcome to the Arachis administration system.\n\n"

            "What would you like to do?\n\n"

            "1️⃣ Student Management\n"
            "2️⃣ Payments\n"
            "3️⃣ Training Management\n"
            "4️⃣ Marketplace\n"
            "5️⃣ AI / System\n"
            "6️⃣ Business Tools\n\n"

            "🤖 You can also ask me a question naturally.\n\n"

            "💡 Type *MENU* anytime to return here."
        )

    # ==========================================
    # STUDENT
    # ==========================================

    if user_type == "student":

        return (
            "🎓 *ARACHIS MANUFACTURING AI*\n\n"
            + greeting +

            "Welcome back to Arachis.\n\n"

            "You have access to your Arachis training.\n\n"

            "*How can I help you today?*\n\n"

            "1️⃣ *My Learning*\n"
            "2️⃣ *Make a Product*\n"
            "3️⃣ *Grow My Business*\n"
            "4️⃣ *Buy or Sell*\n"
            "5️⃣ *Business Tools*\n"
            "6️⃣ *My Account*\n\n"

            "🤖 Or simply ask me your question naturally.\n\n"

            "*For example:*\n"
            "• How do I make dishwash?\n"
            "• Explain SLES.\n"
            "• Calculate a 200L batch.\n"
            "• Find SLES suppliers in Harare.\n"
            "• Help me price my product.\n\n"

            "💡 Type *MENU* anytime to return here."
        )

    # ==========================================
    # GUEST
    # ==========================================

    return (
        "🏠 *ARACHIS MANUFACTURING AI*\n\n"
        + greeting +

        "Welcome to Arachis.\n\n"

        "I'm your virtual manufacturing and business assistant.\n\n"

        "*You can ask me about:*\n\n"

        "🏭 Manufacturing\n"
        "💼 Business\n"
        "🛒 Suppliers & Marketplace\n"
        "🎓 Training\n"
        "📢 Marketing\n\n"

        "*How can I help you today?*\n\n"

        "1️⃣ Training Packages\n"
        "2️⃣ Practical Training\n"
        "3️⃣ Ask AI\n"
        "4️⃣ Buy or Sell\n"
        "5️⃣ About Arachis\n\n"

        "🤖 You can also simply ask your question.\n\n"

        "*For example:*\n"
        "• How do I make dishwash?\n"
        "• What training packages do you have?\n"
        "• When is the next practical training?\n"
        "• Find SLES suppliers in Harare.\n"
        "• Help me start a business with $100.\n\n"

        "🎓 *Want access to Arachis lessons?*\n"
        "Ask me about our training packages.\n\n"

        "💡 Type *MENU* anytime to return here."
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

def build_open_lessons_menu(phone):

    user = get_user(phone)

    package = (
        user.get("package")
        or "Guest"
    ).title()

    return (

        "📱 *OPEN MY LESSONS*\n\n"

        "Your training is now delivered through the "
        "*Arachis Business App.*\n\n"

        f"📦 Package: *{package}*\n\n"

        "Choose an option:\n\n"

        "1️⃣ Open the App\n"
        "2️⃣ Download Latest App\n"
        "3️⃣ I Can't Access My Lessons\n"
        "4️⃣ Ask AI Trainer\n\n"

        "↩ Type *MENU* to return."
    )

# ==========================================
# CONTINUE MY LEARNING
# ==========================================

def build_student_dashboard(phone):

    user = get_user(phone)

    package = "Guest"

    if user:
        package = (user.get("package") or "Guest").title()

    lessons = get_unlocked_modules(phone)

    lesson_count = len(lessons)

    text = (
        "📚 *YOUR LEARNING*\n\n"

        f"🎓 Package: *{package}*\n"

        f"📖 Unlocked Lessons: *{lesson_count}*\n\n"

        "📱 Continue your learning inside the *Arachis Business App*.\n\n"

        "Need help understanding a lesson?\n\n"

        "You can ask me questions like:\n"

        "• Explain SLES.\n"
        "• Why is my Pine Gel separating?\n"
        "• Test me on Dishwash.\n"
        "• Calculate a 100L batch.\n\n"

        "📲 Type *APP* to open the app.\n"

        "↩ Type *MENU* to return."
    )

    return text

# ==========================================
# ALL COURSES
# ==========================================

def build_courses_menu():

    return (
        "📚 *ALL COURSES*\n\n"

        "Choose a department:\n\n"

        "1️⃣ Detergent Manufacturing\n"
        "2️⃣ Drinks Manufacturing\n"
        "3️⃣ Spices & Seasonings\n"
        "4️⃣ Advanced Manufacturing\n"
        "5️⃣ Business Training\n\n"

        "Reply with a number.\n\n"

        "↩ Type *BACK* to return."
    )

# ==========================================
# COURSE LISTS
# ==========================================

def build_course_list(choice):

    courses = {

        "1": [
            "Dishwash",
            "Foam Bath",
            "Liquid Laundry Soap",
            "Fabric Softener",
            "Thick Bleach",
            "Pine Gel",
            "Petroleum Jelly",
            "Car Shampoo",
            "Engine Cleaner",
            "Tyre Polish",
            "Tile Cleaner",
            "Perfume",
            "Metal Degreaser",
            "Floor Polish",
            "Paste Shoe Polish",
            "Liquid Shoe Polish",
            "Hair Shampoo",
            "Hair Conditioner",
            "Bath Soap",
            "Laundry Bar",
            "Floor Glaze",
            "Washing Powder",
            "Scouring Powder",
            "Roll On"
        ],

        "2": [
            "Orange Drink",
            "Freezits",
            "Baobab Drink",
            "Universal Cordial",
            "Ice Cream",
            "Cream Soda",
            "Juice Cascade",
            "Low Cost Orange Drink",
            "Low Cost Raspberry Drink",
            "Raspberry Drink"
            
        ],

        "3": [
            "Chicken Spice",
            "Beef Spice",
            "Mixed Spice",
            "Tea Masala",
            "Rice Spice"
        ],

        "4": [
            "Body Cream",
            "Lotion",
            "Paint",
            "Glue",
            "Peanut Butter",
            "Yoghurt",
            "Biscuits"
        ],

        "5": [
            "Business Startup",
            "Pricing",
            "Marketing",
            "Branding",
            "Record Keeping"
        ]

    }

    if choice not in courses:
        return "Invalid choice."

    text = "📚 *AVAILABLE LESSONS*\n\n"

    for lesson in courses[choice]:
        text += f"• {lesson}\n"

    text += (
        "\n📱 These lessons are available inside the "
        "*Arachis Business App*.\n\n"
        "Type *APP* to continue learning.\n"
        "↩ Type *BACK* to return."
    )

    return text

def build_business_courses():

    return (
        "💼 *BUSINESS COURSES*\n\n"

        "Available lessons:\n\n"

        "1️⃣ Starting a Manufacturing Business\n"
        "2️⃣ Product Pricing\n"
        "3️⃣ Marketing & Advertising\n"
        "4️⃣ Branding\n"
        "5️⃣ Customer Service\n"
        "6️⃣ Record Keeping\n\n"

        "📱 These lessons are available in the "
        "*Arachis Business App*.\n\n"

        "Type *APP* to continue learning.\n"
        "↩ Type *BACK* to return."
    )
# ==========================================
# ACCOUNT DASHBOARD
# ==========================================

def build_account_dashboard(phone):

    user_type = get_menu_user_type(phone)

    # ==========================================
    # GUEST
    # ==========================================

    if user_type == "guest":

        return (
            "👤 *ARACHIS GUEST*\n\n"

            "You currently do not have an active "
            "Arachis student package.\n\n"

            "You can still use the AI assistant and "
            "learn about our training.\n\n"

            "🎓 *TRAINING PACKAGES*\n"
            "Type *PACKAGES* to view available packages.\n\n"

            "🎓 *PRACTICAL TRAINING*\n"
            "Type *TRAINING* to see upcoming training.\n\n"

            "↩ Type *MENU* to return."
        )

    # ==========================================
    # ADMIN
    # ==========================================

    if user_type == "admin":

        return (
            "👑 *ARACHIS ADMIN ACCOUNT*\n\n"

            "You are logged in as an administrator.\n\n"

            "You have administrative access to the "
            "Arachis system.\n\n"

            "↩ Type *MENU* to return."
        )

    # ==========================================
    # STUDENT
    # ==========================================

    user = get_user(phone)

    package = (
        user.get("package")
        or "Unknown"
    ).title()

    lessons = len(
        get_unlocked_modules(phone)
    )

    return (
        "👤 *MY ARACHIS ACCOUNT*\n\n"

        f"🎓 Package: *{package}*\n\n"

        f"📚 Lessons Unlocked: *{lessons}*\n\n"

        "🤖 AI Assistant: *Available*\n\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        "1️⃣ My Subscription\n"
        "2️⃣ Upgrade My Plan\n"
        "3️⃣ Payment History\n"
        "4️⃣ My Certificates\n"
        "5️⃣ Open Arachis App\n"
        "6️⃣ Settings\n\n"

        "↩ Type *MENU* to return."
    )

def build_payment_menu():

    return (
        "💳 *ARACHIS TRAINING PACKAGES*\n\n"

        "1️⃣ Basic Training - $5\n"
        "   ✔ Starter manufacturing lessons\n\n"

        "2️⃣ Premium Training - $10\n"
        "   ✔ Complete manufacturing course\n"
        "   ✔ AI Assistant\n\n"

        "3️⃣ Custom Package\n"
        "   ✔ $2 per formula\n\n"

        "4️⃣ Advanced Manufacturing - $20\n\n"

        "5️⃣ Spices & Seasonings - $10\n\n"

        "Reply with 1, 2, 3, 4 or 5."
    )
# ==========================================
# PRACTICAL TRAINING MENU
# ==========================================

def build_training_menu():

    return (
        "🎓 *PRACTICAL TRAINING*\n\n"

        "1️⃣ View Upcoming Training\n"
        "2️⃣ Register for Training\n"
        "3️⃣ My Registration Status\n"
        "4️⃣ Training FAQs\n\n"

        "↩ Reply *MENU* to return."
    )


