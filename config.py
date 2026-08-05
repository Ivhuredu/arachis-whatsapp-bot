from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# =========================
# CONVERSATION STATES
# =========================

STATE_MAIN = "main"

STATE_LEARN = "learn_menu"
STATE_MANUFACTURE = "manufacture_menu"
STATE_BUSINESS = "business_menu"
STATE_STUDENT_DASHBOARD = "student_dashboard"
STATE_MARKETPLACE = "marketplace_menu"
STATE_TOOLS = "tools_menu"
STATE_ACCOUNT = "account_menu"

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


