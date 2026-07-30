"""
=====================================================
Arachis Bot Constants
Values that rarely change and do NOT belong in .env
=====================================================
"""

import os

# =====================================================
# FILE & FOLDER PATHS
# =====================================================

UPLOAD_FOLDER = "uploads"
APK_FOLDER = "apk"
MARKETPLACE_FOLDER = "marketplace"
LESSONS_FOLDER = "lessons"
PROFILE_FOLDER = "profiles"
TEMP_FOLDER = "temp"

# Create folders automatically if missing
for folder in [
    UPLOAD_FOLDER,
    APK_FOLDER,
    MARKETPLACE_FOLDER,
    LESSONS_FOLDER,
    PROFILE_FOLDER,
    TEMP_FOLDER,
]:
    os.makedirs(folder, exist_ok=True)


# =====================================================
# FILE TYPES
# =====================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "mp4",
    "mp3",
    "wav",
    "zip",
    "apk"
}

ALLOWED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp"
}

ALLOWED_DOCUMENT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx"
}

ALLOWED_VIDEO_EXTENSIONS = {
    "mp4",
    "mov",
    "avi"
}

ALLOWED_AUDIO_EXTENSIONS = {
    "mp3",
    "wav",
    "ogg"
}


# =====================================================
# LIMITS
# =====================================================

MAX_UPLOAD_SIZE = 20 * 1024 * 1024      # 20MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024       # 10MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024      # 100MB

DEVICE_LOCK_DAYS = 7


# =====================================================
# APP DEFAULTS
# =====================================================

DEFAULT_LANGUAGE = "en"
DEFAULT_CURRENCY = "USD"

DEFAULT_COUNTRY = "Zimbabwe"


# =====================================================
# USER STATES
# =====================================================

STATE_NONE = "none"

STATE_MARKETPLACE = "marketplace"

STATE_MARKETPLACE_CART = "marketplace_cart"

STATE_MARKETPLACE_SELL = "marketplace_sell"

STATE_PAYMENT = "payment"

STATE_ADMIN = "admin"


# =====================================================
# ADMIN
# =====================================================

ADMIN_NUMBERS = {
    "263773208904",
}

SUPER_ADMIN = "263773208904"


# =====================================================
# LESSONS
# =====================================================

LESSON_LOCKED = "locked"
LESSON_UNLOCKED = "unlocked"


# =====================================================
# MARKETPLACE
# =====================================================

MARKETPLACE_CATEGORIES = [
    "Detergents",
    "Beverages",
    "Spices",
    "Advanced Products",
    "Packaging",
    "Equipment",
    "Raw Materials",
    "Other"
]


# =====================================================
# LOGGING
# =====================================================

LOG_RETENTION_DAYS = 30
