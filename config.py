BASIC_PRICE = 5.0
PREMIUM_PRICE = 10.0
SPICES_PRICE = 10.0
ADVANCED_PRICE = 20.0
CUSTOM_PRICE_PER_MODULE = 2.0

UPGRADE_BASIC_TO_PREMIUM = 5.0
UPGRADE_BASIC_TO_SPICES = 5.0
UPGRADE_BASIC_TO_ADVANCED = 10.0
UPGRADE_PREMIUM_TO_SPICES = 5.0
UPGRADE_PREMIUM_TO_ADVANCED = 7.0    
PAYMENT_TOLERANCE = 1.5   # allows EcoCash charges
MIN_ACCEPTABLE = BASIC_PRICE
MAX_ACCEPTABLE = PREMIUM_PRICE + PAYMENT_TOLERANCE

ADMIN_NUMBERS = [
    "+263773208904",
    "+263719208904"   # backup admin
]
DEVICE_LOCK_DAYS = 30

DISABLE_WHATSAPP_MEDIA_FROM = "2026-06-15"
UPLOAD_FOLDER = "static/lessons"
APK_FOLDER = "static/apk"
MARKETPLACE_FOLDER = "static/marketplace"

APP_APK_FILENAME = "arachis.apk"
APKPURE_URL = "https://apkpure.com/p/com.arachis.training"

ALLOWED_EXTENSIONS = {"pdf", "apk"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

app.config["MARKETPLACE_FOLDER"] = MARKETPLACE_FOLDER
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["APK_FOLDER"] = APK_FOLDER

PACKAGES = {
    "basic": {
        "price": 5.0,
        "modules": [
            "dishwash",
            "liquid_laundry_soap",
            "fabric_softener",
            "thick_bleach",
            "washing_paste",
            "petroleum_jelly",
            "hair_shampoo",
            "universal_cordial",
            "low_cost_orange_drink",
            "low_cost_raspberry_drink",
            "freezits",
            "baobab_drink"
        ]
    },
    "premium": {
        "price": 10.0,
        "modules": "ALL"
    }
}

STORE_ITEMS = {
    "sles": {
        "name": "SLES (Sodium Lauryl Ether Sulfate)",
        "price": "$3.25 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "caustic": {
        "name": "Caustic Soda",
        "price": "$2.25 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "hypo": {
        "name": "Sodium Hypochlorite",
        "price": "$2 per litre",
        "sizes": "1L | 5L | 20L"
    },
    "cde": {
        "name": "CDE (Cocamide DEA)",
        "price": "$0.0 per litre",
        "sizes": "1L | 5L"
    },
    "perfume": {
        "name": "Detergent Perfumes",
        "price": "$1 per 30ml",
        "sizes": "30ml | 50ml | 100ml"
    },
     "soda": {
        "name": "Soda Ash",
        "price": "$2.25 per kg",
        "sizes": "500ml| 1L | 5L"
    },
    "bermacol": {
        "name": "Bermacol",
        "price": "$7 per 1kg",
        "sizes": "50g | 100g | 500g | 1kg"
    },
    "amido": {
        "name": "Amido",
        "price": "$3.5 per litre",
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
        "price": "$0.0 per 1kg",
        "sizes": "100g | 500g | 1kg"
    },
    "sulphonic": {
        "name": "Sulphonic Acid",
        "price": "$3.25 per kg",
        "sizes": "1ltr | 5ltr | 25ltr"
    },
    "glycerin": {
        "name": "Glycerin",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "np6": {
        "name": "Np6",
        "price": "$6 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "pineoil": {
        "name": "Pine Oil",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "tallow": {
        "name": "Tallow",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "dolomite": {
        "name": "Dolomite",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "soapdye": {
        "name": "Liquid Soap Dye",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "petroleumjelly": {
        "name": "Petroleum Jelly",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "dye": {
        "name": "Dye (Oil-based",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "whiteoil": {
        "name": "White Oil",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    }, 
     "wax": {
        "name": "Wax",
        "price": "$3 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "hardener": {
        "name": "Hardener",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    "oxide": {
        "name": "Oxide",
        "price": "$3.5 per kg",
        "sizes": "1kg | 5kg | 25kg"
    }, 
     "paraffin": {
        "name": "Paraffin",
        "price": "$0.0 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "savenix": {
        "name": "Savenix",
        "price": "$3.5 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "thickener": {
        "name": "Thickener",
        "price": "$5.5 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "colesents": {
        "name": "Colesents",
        "price": "$6.5 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
     "np9": {
        "name": "NP9",
        "price": "$6 per kg",
        "sizes": "1kg | 5kg | 25kg"
    },
    
}

MARKETPLACE_CATEGORIES = {
    "1": "Beverages",
    "2": "Detergents",
    "3": "Spices",
    "4": "Advanced Products",
    "5": "Packaging",
    "6": "Machinery and Tools",
    "7": "Branding and Labels"
}

DELIVERY_FEES = {
    "mataga": 7,
    "mberengwa": 7,
    "gweru": 5,
    "bulawayo": 7,
    "harare": 3
}

DEFAULT_DELIVERY_FEE = 7  # if town not listed

BUSINESS_MODULES = {
    "business_pricing_profit": ("business_pricing_profit.pdf", "💰 Pricing & Profit"),
    "business_packaging": ("business_packaging.pdf", "📦 Packaging & Branding"),
    "business_selling": ("business_selling.pdf", "📍 Where To Sell"),
    "business_scaling": ("business_scaling.pdf", "📈 Scaling Business"),
    "business_strategy": ("business_strategy.pdf", "🇿🇼 Zimbabwe Strategy")
}
DETERGENT_MODULES = [
    "dishwash",
    "liquid_laundry_soap",
    "fabric_softener",
    "thick_bleach",
    "washing_paste",
    "toilet_cleaner",
    "pine_gel",
    "foam_bath",
    "car_shampoo",
    "engine_cleaner",
    "perfume",
    "acidic_metal_degreaser",
    "tile_cleaner",
    "floor_polish",
    "tyre_polish",
    "paste_shoe_polish",
    "liquid_shoe_polish",
    "hair_shampoo",
    "hair_conditioner",
    "petroleum_jelly",
    "bath_soap",
    "laundry_bar",
    "floor_glaze",
    "washing_powder",
    "scouring_powder",
    "roll_on"
]
BEVERAGE_MODULES = sorted([
    "universal_cordial",
    "low_cost_raspberry_drink",
    "low_cost_orange_drink",
    "baobab_drink",
    "juice_cascade",
    "ice_cream",
    "cream_soda",
    "orange_drink",
    "raspberry_drink",
    "freezits"
])
ADVANCED_MODULES = [
    "paint",
    "gummies",
    "glue",
    "maheu",
    "lotion",
    "body_cream",
    "body_butter",
    "peanut_butter",
    "lollipop_sweets",
    "peanut_butter",
    "thinners",
    "yoghurt",
    "methylated_spirit",
    "battery_acid",
    "deo_blocks"
]
SPICE_MODULES = [
    "chicken_spice",
    "peri_peri_spice",
    "curry_powder",
    "curry_beef_spice",
    "curry_garlic_herb",
    "rice_spice",
    "tea_masala",
    "ginger_powder",
    "cinnamon_blend",
    "royco_style_soup",
    "sauce_spice_base"
]

def detect_module_from_question(question, allowed_modules):
    if not question:
        return None

    q = question.lower()

    keyword_map = {
        "dishwash": "dishwash",
        "dish wash": "dishwash",

        "bleach": "thick_bleach",
        "jik": "thick_bleach",

        "foam": "foam_bath",
        "pine": "pine_gel",
        "toilet": "toilet_cleaner",

        "engine": "engine_cleaner",
        "engine 2": "engine_cleaner2",

        "laundry": "laundry_bar",
        "bar soap": "laundry_bar",

        "fabric": "fabric_softener",
        "softener": "fabric_softener",

        "petroleum": "petroleum_jelly",
        "vaseline": "petroleum_jelly",

        "floor polish": "floor_polish",

        "car shampoo": "car_shampoo",
        "car wash": "car_shampoo",

        "degreaser": "acidic_metal_degreaser",
        "acid": "acidic_metal_degreaser",

        "tyre": "tyre_polish",

        "shoe polish": "paste_shoe_polish",
        "liquid polish": "liquid_shoe_polish",

        "tile": "tile_cleaner",

        "conditioner": "hair_conditioner",
        "hair shampoo": "hair_shampoo",

        "washing paste": "washing_paste",
        "bath soap": "bath_soap",

        "freezits": "freezits",
        "ice cream": "ice_cream",

        "baobab": "baobab_drink",
        "cascade": "juice_cascade",
        "orange drink": "orange_drink",
        "raspberry": "raspberry_drink",
        "cream soda": "cream_soda",

        "low cost orange": "low_cost_orange_drink",
        "orange drink": "orange_drink",

        "low cost raspberry": "low_cost_raspberry_drink",

        "universal cordial": "universal_cordial",
        "cordial": "universal_cordial" 
    }

    # 1️⃣ strict keyword match but only if user owns module
    for key, module in keyword_map.items():
        if key in q and module in allowed_modules:
            return module

    # if no keyword match → stay in last module
    if allowed_modules:
        return allowed_modules[-1]


    # 2️⃣ direct module name mention
    for module in allowed_modules:
        if module.replace("_", " ") in q:
            return module

    # 3️⃣ fallback = last opened module
    return allowed_modules[-1] if allowed_modules else None

 # =========================
    # QUICK LESSON SHORTCUTS
    # =========================
    lesson_shortcuts = {
        "detergents": "detergents_menu",
        "detergent": "detergents_menu",
        "ma detergents": "detergents_menu",
        "beverages": "beverages_menu",
        "drinks": "beverages_menu",
        "madrinks": "beverages_menu",
        "advanced": "advanced_menu",
        "advanced manufacturing": "advanced_menu",
        "manufacturing": "advanced_menu",
        "spices": "spices_menu",
        "spice": "spices_menu",
        "seasonings": "spices_menu",
        "spices and seasonings": "spices_menu",
    }

    if incoming in lesson_shortcuts:
        fresh_user = get_user(phone)

        if not fresh_user["is_paid"]:
            send_message(phone, "🔒 Lessons are for paid students only.\nNyora *PAY* kuti utange.")
            return jsonify({"status": "ok"})

        target_state = lesson_shortcuts[incoming]
        set_state(phone, target_state)

        if target_state == "detergents_menu":
            send_message(phone, build_detergent_menu(phone))

        elif target_state == "beverages_menu":
            send_message(phone, build_beverage_menu(phone))

        elif target_state == "advanced_menu":
            send_message(phone, build_advanced_menu(phone))

        elif target_state == "spices_menu":
            send_message(phone, build_spices_menu(phone))

        return jsonify({"status": "ok"})
