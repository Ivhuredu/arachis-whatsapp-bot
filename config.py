"""
=========================================================
Arachis Bot V2
config.py

Central configuration for the entire application.
Nothing in this file should contain business logic.
=========================================================
"""

import os
from dotenv import load_dotenv

# --------------------------------------------------------
# Load Environment Variables
# --------------------------------------------------------

load_dotenv()

# --------------------------------------------------------
# Application
# --------------------------------------------------------

APP_NAME = "Arachis Bot V2"
APP_VERSION = "2.0.0"

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))

TIMEZONE = "Africa/Harare"

# --------------------------------------------------------
# WhatsApp Cloud API
# --------------------------------------------------------

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")

PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GRAPH_API_VERSION = "v23.0"

GRAPH_API_URL = (
    f"https://graph.facebook.com/"
    f"{GRAPH_API_VERSION}/"
    f"{PHONE_NUMBER_ID}"
)

MESSAGES_URL = f"{GRAPH_API_URL}/messages"

MEDIA_URL = f"{GRAPH_API_URL}/media"

# --------------------------------------------------------
# OpenAI
# --------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")

VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID")

AI_MAX_HISTORY = 12

AI_TIMEOUT = 60

AI_TEMPERATURE = 0.2

# --------------------------------------------------------
# PostgreSQL
# --------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

DB_POOL_MIN = 1

DB_POOL_MAX = 10

# --------------------------------------------------------
# Business Information
# --------------------------------------------------------

BUSINESS_NAME = "Arachis Training"

BUSINESS_EMAIL = os.getenv("BUSINESS_EMAIL", "")

SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "")

WEBSITE = os.getenv("WEBSITE", "")

FACEBOOK = os.getenv("FACEBOOK", "")

YOUTUBE = os.getenv("YOUTUBE", "")

# --------------------------------------------------------
# Pricing
# --------------------------------------------------------

BASIC_PRICE = 5

PREMIUM_PRICE = 10

ADVANCED_PRICE = 10

CUSTOM_PRICE = 3

# --------------------------------------------------------
# Package IDs
# --------------------------------------------------------

PACKAGE_BASIC = "basic"

PACKAGE_PREMIUM = "premium"

PACKAGE_ADVANCED = "advanced"

PACKAGE_CUSTOM = "custom"

# --------------------------------------------------------
# Lesson Folders
# --------------------------------------------------------

LESSONS_FOLDER = "lessons"

AUDIO_FOLDER = "audio"

IMAGE_FOLDER = "images"

STATIC_FOLDER = "static"

UPLOAD_FOLDER = "uploads"

# --------------------------------------------------------
# Marketplace
# --------------------------------------------------------

PRODUCT_IMAGES = "static/products"

DEFAULT_PRODUCT_IMAGE = "static/products/default.jpg"

# --------------------------------------------------------
# Logging
# --------------------------------------------------------

LOG_LEVEL = "INFO"

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"

# --------------------------------------------------------
# Security
# --------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY")

SESSION_TIMEOUT = 3600

# --------------------------------------------------------
# Media Limits
# --------------------------------------------------------

MAX_UPLOAD_SIZE = 20 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

ALLOWED_DOCUMENT_TYPES = {
    "pdf",
    "docx",
    "xlsx",
    "pptx"
}

# --------------------------------------------------------
# HTTP Requests
# --------------------------------------------------------

REQUEST_TIMEOUT = 60

MAX_RETRIES = 3

# --------------------------------------------------------
# Admin
# --------------------------------------------------------

ADMIN_NUMBERS = {
    "+26377xxxxxxx",
}

# --------------------------------------------------------
# Default Messages
# --------------------------------------------------------

WELCOME_MESSAGE = (
    "👋 Welcome to Arachis Practical Training.\n"
    "How can I help you today?"
)

FALLBACK_MESSAGE = (
    "I'm sorry, I didn't understand that. "
    "Please try again."
)
# =========================
# PRICING
# =========================

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

PAYMENT_TOLERANCE = 1.5

MIN_ACCEPTABLE = BASIC_PRICE
MAX_ACCEPTABLE = PREMIUM_PRICE + PAYMENT_TOLERANCE

# =========================
# PACKAGES
# =========================

PACKAGES = {
    "basic": {
        "price": BASIC_PRICE,
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
        "price": PREMIUM_PRICE,
        "modules": "ALL"
    }
}
