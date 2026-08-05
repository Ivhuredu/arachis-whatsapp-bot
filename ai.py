from openai import OpenAI

def ai_questions_today(phone):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT COUNT(*) FROM activity_log
        WHERE phone = %s
        AND action = 'ai_question'
        AND DATE(created_at) = CURRENT_DATE
    """, (phone,))

    count = c.fetchone()[0]
    DATABASE_POOL.putconn(conn)
    return count

# =========================
# AI MEMORY SYSTEM
# =========================

MAX_MEMORY_MESSAGES = 4   # last 6 exchanges

def save_memory(phone, module, role, message):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO ai_memory (phone, module, role, message)
        VALUES (%s,%s,%s,%s)
    """, (phone, module, role, message))

    # Trim old memory (keep only last N)
    c.execute("""
        DELETE FROM ai_memory
        WHERE id NOT IN (
            SELECT id FROM ai_memory
            WHERE phone=%s AND module=%s
            ORDER BY created_at DESC
            LIMIT %s
        )
        AND phone=%s AND module=%s
    """, (phone, module, MAX_MEMORY_MESSAGES, phone, module))

    conn.commit()
    DATABASE_POOL.putconn(conn)


def get_memory(phone, module):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT role, message
        FROM ai_memory
        WHERE phone=%s AND module=%s
        ORDER BY created_at ASC
    """, (phone, module))

    rows = c.fetchall()
    DATABASE_POOL.putconn(conn)

    memory = []
    for r in rows:
        memory.append({"role": r[0], "content": r[1]})

    return memory

def get_customer_profile(phone):

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT

            full_name,
            location,
            language,

            business_stage,
            experience_level,

            business_type,
            capital,

            interests,
            goals,
            problems,
            equipment,

            preferred_department,

            ai_summary

        FROM customer_profiles
        WHERE phone=%s
    """, (phone,))

    row = c.fetchone()

    DATABASE_POOL.putconn(conn)

    if not row:
        return {
            "full_name":"",
            "location":"",
            "language":"english",

            "business_stage":"planning",
            "experience_level":"beginner",

            "business_type":"",
            "capital":None,

            "interests":"",
            "goals":"",
            "problems":"",
            "equipment":"",

            "preferred_department":"",

            "ai_summary":""
        }

    return {

        "full_name":row[0] or "",
        "location":row[1] or "",
        "language":row[2] or "english",

        "business_stage":row[3] or "planning",
        "experience_level":row[4] or "beginner",

        "business_type":row[5] or "",
        "capital":row[6],

        "interests":row[7] or "",
        "goals":row[8] or "",
        "problems":row[9] or "",
        "equipment":row[10] or "",

        "preferred_department":row[11] or "",

        "ai_summary":row[12] or ""

    }

def save_customer_profile(phone, profile):

    conn = get_db()
    c = conn.cursor()

    c.execute("""

    INSERT INTO customer_profiles(

        phone,

        full_name,
        location,
        language,

        business_stage,
        experience_level,

        business_type,
        capital,

        interests,
        goals,
        problems,
        equipment,

        preferred_department,

        ai_summary

    )

    VALUES(

        %s,

        %s,%s,%s,

        %s,%s,

        %s,%s,

        %s,%s,%s,%s,

        %s,

        %s

    )

    ON CONFLICT(phone)

    DO UPDATE SET

        full_name=EXCLUDED.full_name,
        location=EXCLUDED.location,
        language=EXCLUDED.language,

        business_stage=EXCLUDED.business_stage,
        experience_level=EXCLUDED.experience_level,

        business_type=EXCLUDED.business_type,
        capital=EXCLUDED.capital,

        interests=EXCLUDED.interests,
        goals=EXCLUDED.goals,
        problems=EXCLUDED.problems,
        equipment=EXCLUDED.equipment,

        preferred_department=EXCLUDED.preferred_department,

        ai_summary=EXCLUDED.ai_summary,

        updated_at=CURRENT_TIMESTAMP

    """,(

        phone,

        profile.get("full_name",""),
        profile.get("location",""),
        profile.get("language","english"),

        profile.get("business_stage","planning"),
        profile.get("experience_level","beginner"),

        profile.get("business_type",""),
        profile.get("capital"),

        profile.get("interests",""),
        profile.get("goals",""),
        profile.get("problems",""),
        profile.get("equipment",""),

        profile.get("preferred_department",""),

        profile.get("ai_summary","")

    ))

    conn.commit()
    DATABASE_POOL.putconn(conn)

def update_customer_profile_ai(phone, question, answer):

    profile = get_customer_profile(phone)

    prompt = f"""
You are an AI CRM assistant for Arachis.

Your job is to update a customer's profile.

Current Profile:

{json.dumps(profile, indent=2)}

Customer Question:

{question}

AI Reply:

{answer}

Extract ONLY new or updated customer information.

Do NOT include fields that have not changed.

Do NOT return empty strings.

Do NOT guess or invent information.

Return ONLY valid JSON.

Example:

{{
    "capital": 250,
    "goals": "Start a detergent business"
}}
"""

    try:

        response = openai_client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=prompt
        )

        new_profile = json.loads(response.output_text)

        if not isinstance(new_profile, dict):
            print("PROFILE UPDATE ERROR: Invalid JSON object")
            return

        merged_profile = profile.copy()

        for key, value in new_profile.items():

            if value is None:
                continue

            if isinstance(value, str) and value.strip() == "":
                continue

            if isinstance(value, list) and len(value) == 0:
                continue

            if key in merged_profile:
                merged_profile[key] = value

        save_customer_profile(phone, merged_profile)

    except Exception as e:

        print("PROFILE UPDATE ERROR:", e)

def get_next_training(city=None):

    conn = get_db()
    c = conn.cursor()

    if city:
        c.execute("""
            SELECT
                id,
                title,
                city,
                venue,
                event_date,
                start_time,
                fee,
                deposit,
                products_taught,
                registration_status,
                booked_seats,
                total_seats
            FROM training_events
            WHERE
                LOWER(city)=LOWER(%s)
                AND registration_status='open'
                AND event_date >= CURRENT_DATE
            ORDER BY event_date ASC
            LIMIT 1
        """, (city,))
    else:
        c.execute("""
            SELECT
                id,
                title,
                city,
                venue,
                event_date,
                start_time,
                fee,
                deposit,
                products_taught,
                registration_status,
                booked_seats,
                total_seats
            FROM training_events
            WHERE
                registration_status='open'
                AND event_date >= CURRENT_DATE
            ORDER BY event_date ASC
            LIMIT 1
        """)

    row = c.fetchone()

    DATABASE_POOL.putconn(conn)

    return row

def get_all_training_events():

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            id,
            title,
            city,
            venue,
            event_date,
            start_time,
            fee,
            deposit,
            registration_status,
            booked_seats,
            total_seats
        FROM training_events
        ORDER BY event_date ASC
    """)

    events = c.fetchall()

    DATABASE_POOL.putconn(conn)

    return events

# ✅ NEW (REQUIRED FOR AI RESTRICTION)
def get_user_modules(phone, message):

    conn = get_db()
    c = conn.cursor()

    # get modules user opened
    c.execute(
        "SELECT module FROM module_access WHERE phone=%s",
        (phone,)
    )

    rows = c.fetchall()
    user_modules = [r[0] for r in rows]

    # get active module
    c.execute(
        "SELECT active_module FROM users WHERE phone=%s",
        (phone,)
    )

    row = c.fetchone()

    DATABASE_POOL.putconn(conn)

    if row and row[0]:
        return [row[0]]

    # detect module from question
    detected = detect_module_from_question(message, user_modules)

    if detected:

        conn = get_db()
        c = conn.cursor()

        c.execute(
            "UPDATE users SET active_module=%s WHERE phone=%s",
            (detected, phone)
        )

        conn.commit()
        DATABASE_POOL.putconn(conn)

        return [detected]

    if user_modules:
        return [user_modules[-1]]

    return []

# ✅ MODIFIED (MODULE-AWARE AI)
def ai_trainer_reply(phone, question, allowed_modules=None):
    active_module = "general"

    if allowed_modules:
        active_module = allowed_modules[-1]

    memory_messages = get_memory(phone, active_module)

    memory_text = ""
    for m in memory_messages:
        memory_text += f"{m['role']}: {m['content']}\n"

    instructions = f"""
You are Arachis AI Trainer.

Help Zimbabwean students with:
- detergent production
- drink production
- business advice

Reply simply in English or Shona.

When replying in shona make sure it's grammatically correct and natural.

Use lesson files first before answering.

Keep the a short and precise.

Recent memory:
{memory_text}
"""

    try:
        response = openai_client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            instructions=instructions,
            input=question,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [
                        os.getenv("ARACHIS_VECTOR_STORE_ID")
                    ]
                }
        
            ]
        )

        answer = response.output_text.strip()

        save_memory(phone, active_module, "user", question)
        save_memory(phone, active_module, "assistant", answer)

        return answer

    except Exception as e:
        print("OPENAI AGENT ERROR:", e)
        return "Pane problem paAI trainer parizvino. Ndapota edzai zvakare kana taurai naAdmin."

# ==========================================
# AI DEPARTMENT PROMPTS
# ==========================================
# =====================================================
# ARACHIS AI DEPARTMENTS
# =====================================================

DEPARTMENTS = {

    "manufacturing": {

        "title": "Senior Manufacturing Engineer",

        "mission":
            "Help customers manufacture high-quality products safely and successfully.",

        "personality":
            "Precise, practical, patient, quality-focused and technically competent.",
        "communication_style": """
            Talk like a senior manufacturing engineer.

            Diagnose before giving solutions.

            Keep replies practical.

            Usually 100-180 words.

            Explain the cause first.

            Avoid unnecessary introductions.

            Ask diagnostic questions only when necessary.

            Use bullet points for troubleshooting.
            """,

        "responsibilities":[

            "Formulations",

            "Batch calculations",

            "Troubleshooting",

            "Ingredient functions",

            "Quality control",

            "Manufacturing safety"

        ],

        "knowledge":[

            "Manufacturing manuals",

            "Formula database",

            "Lesson PDFs",

            "Quality control",

            "Troubleshooting guide"

        ],

        "rules":[

            "Never invent formulations.",

            "Always explain why a problem happens.",

            "Recommend quality improvements."

        ]
    },

    "supplier":{

        "title":"Senior Procurement Officer",

        "mission":
            "Help customers find ingredients, packaging and equipment.",

        "personality":
            "Resourceful, practical and cost-conscious.",

        "responsibilities":[

            "Supplier search",

            "Packaging",

            "Equipment",

            "Ingredient alternatives"

        ],

        "knowledge":[

            "Supplier directory",

            "Packaging suppliers",

            "Ingredient database"

        ],

        "rules":[

            "Prefer Zimbabwe suppliers.",

            "Offer alternatives if unavailable."

        ]
    },

    "sales":{

        "title":"Senior Sales Consultant",

        "mission":
            "Recommend the most suitable Arachis package.",

        "personality":
            "Helpful, honest and consultative.",

        "responsibilities":[

            "Training packages",

            "Pricing",

            "Promotions",

            "App subscriptions"

        ],

        "knowledge":[

            "Package database",

            "Training calendar",

            "Current promotions"

        ],

        "rules":[

            "Recommend the best package, not the most expensive.",

            "Never pressure customers."

        ]
    },

    "advisor":{

        "title":"Senior Business Advisor",

        "mission":
            "Help customers build profitable manufacturing businesses.",

        "personality":
            "Experienced mentor with practical business knowledge.",

        "responsibilities":[

            "Business planning",

            "Pricing",

            "Profit",

            "Scaling",

            "Investment"

        ],

        "knowledge":[

            "Business guides",

            "Profit calculators",

            "Growth strategies"

        ],

        "rules":[

            "Think long-term.",

            "Focus on profitability."

        ]
    },

    "support":{

        "title":"Customer Support Officer",

        "mission":
            "Solve customer problems quickly.",

        "personality":
            "Friendly, calm and patient.",
        "communication_style": """
            Reply like a friendly WhatsApp customer support officer.

            Most replies should be under 80 words.

            Answer the customer's question first.

            Do not overload the customer.

            Ask only one question at a time.

            Avoid long explanations.

            Guide the customer step by step.
            """,

        "responsibilities":[

            "Payments",

            "Lesson access",

            "App support",

            "Login issues"

        ],

        "knowledge":[

            "App documentation",

            "Payment procedures",

            "Lesson management"

        ],

        "rules":[

            "Solve the customer's problem step by step."

        ]
    },
    
    "training_events": {

        "title": "Training & Events Department",

        "mission": "Help customers with training schedules, venues, registrations, deposits, bookings and all practical or online training enquiries.",

        "personality": """
    Friendly.
    Professional.
    Helpful.
    Organised.
    Always uses the latest approved training schedule.
    """,
        "communication_style": """
            Reply like an event coordinator.

            Be enthusiastic.

            Highlight:

            Date

            • Venue

            • Fee

            • Deposit

            • Registration

            Keep replies under 100 words.

            Finish by inviting the customer to book.
            """,

        "responsibilities": [

            "Training schedules",
            "Training venues",
            "Practical training",
            "Online training",
            "Training registration",
            "Training bookings",
            "Deposits",
            "Training fees",
            "Seat availability",
            "Training preparation"

        ],

        "knowledge":[

            "TRN-001",
            "TRN-002",
            "TRN-003"

        ],

        "rules":[

            "Never invent dates.",
            "Always retrieve current training information from the database.",
            "Never confirm bookings without verification.",
            "Use the database for live events instead of the Vector Store."

        ]

    },

    "marketing":{

        "title":"Marketing Consultant",

        "mission":
            "Help customers grow sales through effective marketing.",

        "personality":
            "Creative, energetic and business-focused.",

        "responsibilities":[

            "Advertising",

            "Branding",

            "WhatsApp marketing",

            "Facebook marketing"

        ],

        "knowledge":[

            "Marketing templates",

            "Sales copy",

            "Branding guides"

        ],

        "rules":[

            "Create simple, persuasive marketing."

        ]
    },

    "marketplace":{

        "title":"Marketplace Officer",

        "mission":
            "Help buyers and sellers trade successfully.",

        "personality":
            "Fair, organised and professional.",

        "responsibilities":[

            "Listings",

            "Orders",

            "Marketplace rules"

        ],

        "knowledge":[

            "Marketplace database"

        ],

        "rules":[

            "Protect both buyer and seller."

        ]
    },

    "general":{

        "title":"Arachis Virtual Employee",

        "mission":
            "Provide helpful assistance.",

        "personality":
            "Professional and knowledgeable.",

        "responsibilities":[

            "General assistance"

        ],

        "knowledge":[

            "Company information"

        ],

        "rules":[

            "Always be helpful."

        ]
    }

}

# =====================================================
# BUILD DEPARTMENT PROMPT
# =====================================================

def build_department_prompt(department):

    dept = DEPARTMENTS.get(
        department,
        DEPARTMENTS["general"]
    )

    responsibilities = "\n".join(
        f"- {item}" for item in dept["responsibilities"]
    )

    knowledge = "\n".join(
        f"- {item}" for item in dept["knowledge"]
    )

    rules = "\n".join(
        f"- {item}" for item in dept["rules"]
    )

    prompt = f"""
You are {dept['title']} at Arachis Manufacturing.

MISSION

{dept['mission']}

PERSONALITY

{dept['personality']}

COMMUNICATION STYLE

{dept.get('communication_style','')}

YOUR RESPONSIBILITIES

{responsibilities}

YOUR KNOWLEDGE

{knowledge}

YOUR RULES

{rules}

GENERAL COMPANY RULES
GENERAL COMPANY RULES

- Reply naturally as if chatting on WhatsApp.

- Don't sound like ChatGPT.

- Don't write essays.

- Don't repeat yourself.

- Answer the customer's exact question first.

- Give additional information only if it helps.

- Most replies should be under 120 words.

- Use short paragraphs.

- Avoid unnecessary numbered lists.

- Ask only one follow-up question at a time.

- Be warm, confident and practical.

- Never overwhelm the customer.

- If live database information is available, use it before general knowledge.
"""

    return prompt

# =====================================================
# DEPARTMENT KNOWLEDGE MANAGER
# =====================================================

def get_department_knowledge(department):

    knowledge = {

        "manufacturing": {

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "tables":[

                "lesson_content",

                "manufacturing_guides",

                "quality_control"

            ],

            "description":
                "Manufacturing formulas, troubleshooting and production knowledge."

        },

        "supplier":{

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "tables":[

                "suppliers",

                "ingredients",

                "packaging"

            ],

            "description":
                "Supplier directory and sourcing information."

        },

        "sales":{

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "tables":[

                "packages",

                "promotions"

            ],

            "description":
                "Training packages and promotions."

        },
        "training_events": {

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "tables": [

                "training_events"

            ],

            "description":
                "Training schedules, events, registrations and bookings."

        },

        "advisor":{

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "tables":[

                "business_guides",

                "profit_calculators"

            ],

            "description":
                "Business growth and startup advice."

        },

        "marketing":{

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "tables":[

                "marketing_templates",

                "branding"

            ],

            "description":
                "Marketing and branding."

        },

        "support":{

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "tables":[

                "payments",

                "lessons",

                "users"

            ],

            "description":
                "Customer support."

        },

        "marketplace":{

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "tables":[

                "marketplace"

            ],

            "description":
                "Marketplace."

        }

    }

    return knowledge.get(
        department,
        {
            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),
            "tables":[],
            "description":"General company knowledge."
        }
    )

def detect_department(question):

    q = question.lower()

    training_keywords = [
        "training", "practical", "offline", "online",
        "venue", "schedule", "date", "book", "booking",
        "seat", "deposit", "event",
        "bulawayo", "harare", "gweru",
        "mutare", "masvingo", "kwekwe",
        "victoria falls"
    ]

    manufacturing_keywords = [
        "dishwash", "foam bath", "pine gel",
        "bleach", "soap", "detergent",
        "formula", "ingredient",
        "batch", "cmc", "sles",
        "np9", "np6", "salt",
        "thick", "viscosity"
    ]

    supplier_keywords = [
        "supplier",
        "ingredient",
        "where can i buy",
        "packaging",
        "chemical supplier"
    ]

    sales_keywords = [
        "price",
        "package",
        "premium",
        "basic",
        "upgrade",
        "promotion"
    ]

    support_keywords = [
        "payment",
        "paid",
        "login",
        "lesson",
        "download",
        "app",
        "password",
        "access"
    ]

    business_keywords = [
        "business",
        "profit",
        "pricing",
        "marketing",
        "customer",
        "startup"
    ]

    if any(k in q for k in training_keywords):
        return "training_events"

    if any(k in q for k in manufacturing_keywords):
        return "manufacturing"

    if any(k in q for k in supplier_keywords):
        return "supplier"

    if any(k in q for k in sales_keywords):
        return "sales"

    if any(k in q for k in support_keywords):
        return "support"

    if any(k in q for k in business_keywords):
        return "advisor"

    return "general"

def ai_department_router(question):
    
    print(f"Department selected: {department}")

    prompt = f"""
You are the Arachis Department Router.

Your ONLY job is to choose which department should answer the customer's question.

Available departments:

manufacturing
- Product formulas
- Manufacturing
- Quality control
- Troubleshooting
- Ingredients
- Batch calculations

supplier
- Suppliers
- Ingredients
- Packaging
- Equipment

sales
- Training packages
- Promotions
- Pricing
- Upgrades

advisor
- Business advice
- Profit
- Marketing
- Pricing
- Business growth

support
- Payments
- Lesson access
- Login
- Mobile App
- Downloads
- Account problems

training_events
- Training dates
- Practical training
- Online training
- Venues
- Registration
- Bookings
- Deposits
- Seat availability

marketing
- Advertising
- Branding
- WhatsApp marketing
- Facebook marketing

marketplace
- Buying
- Selling
- Marketplace

general
- Anything else

Return ONLY one department name.

Customer Question:

""" + question

    try:

        response = openai_client.responses.create(

            model=os.getenv("OPENAI_MODEL","gpt-4.1-mini"),

            input=prompt

        )

        dept = response.output_text.strip().lower()

        if dept not in DEPARTMENTS:
            dept = "general"

        return dept

    except Exception as e:

        print("ROUTER ERROR:", e)

        return "general"

# ==========================================
# ARACHIS AI VIRTUAL EMPLOYEE
# ==========================================

def ai_virtual_employee(phone, question, department=None):

    if department is None:
        department = ai_department_router(question)
        
    user = get_user(phone)

    profile = get_customer_profile(phone)

    department_prompt = build_department_prompt(department)

    department_knowledge = get_department_knowledge(department)

    live_training_info = ""

    if department == "training_events":

        city = None

        # Find city...

        event = get_next_training(city)

        if event:

            (
                event_id,
                title,
                city,
                venue,
                event_date,
                start_time,
                fee,
                deposit,
                products,
                status,
                booked,
                seats
            ) = event

            live_training_info = f"""
    Title: {title}
    City: {city}
    Venue: {venue}
    Date: {event_date}
    Time: {start_time}
    Fee: ${fee}
    Deposit: ${deposit}
    Products: {products}
    """

        else:

            live_training_info = "There are currently no upcoming training events."

    instructions = f"""
{department_prompt}

Department Knowledge

{department_knowledge["description"]}

Customer Information

Phone:
{phone}

Package:
{user.get("package","none")}

Department:
{department}

Customer Profile

Name:
{profile.get("full_name","Unknown")}

Location:
{profile.get("location","Unknown")}

Language:
{profile.get("language","english")}

Business Stage:
{profile.get("business_stage","planning")}

Experience:
{profile.get("experience_level","beginner")}

Business Type:
{profile.get("business_type","")}

Capital:
{profile.get("capital","Unknown")}

Interests:
{profile.get("interests","")}

Goals:
{profile.get("goals","")}

Problems:
{profile.get("problems","")}

Equipment:
{profile.get("equipment","")}

AI Summary:
{profile.get("ai_summary","")}

Live Training Information

{live_training_info}

General Company Rules

- Always personalise your replies using the customer's profile.
- If the profile contains useful information, use it naturally.
- Never invent profile information.
- If information is missing, continue helping normally.
- Be professional.
- Keep answers concise.
- Use English or Shona naturally.
- Promote Arachis where appropriate.
"""

    try:

        response = openai_client.responses.create(

            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),

            instructions=instructions,

            input=question,

            tools=[
                {
                    "type":"file_search",
                    "vector_store_ids":[
                        department_knowledge["vector_store"]
                    ]
                }
            ]
        )
        answer = response.output_text.strip()

        update_customer_profile_ai(
            phone,
            question,
            answer
        )

        return answer

    except Exception as e:

        print("VIRTUAL EMPLOYEE ERROR:", e)

        return f"DEBUG: {str(e)}"

def ai_analyze_product(image_path, student_details):

    import base64

    with open(image_path, "rb") as img:
        image_bytes = img.read()

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = f"""
You are a PROFESSIONAL detergent production trainer.

You must diagnose the product failure or appraise the good done and give EXACT rescue steps.

STUDENT DESCRIPTION:
{student_details}

RULES:

1. Use ONLY chemicals from the lesson formula but do not just retain the original formula, do further research.
2. Diagnose the MOST LIKELY cause and tell which stage was misdone or which product was misapplied.
3. Give STEP-BY-STEP rescue instructions.
4. Use exact measurements (grams, ml).
5. Include mixing time and waiting time.
6. Explain briefly WHY the failure happened  but do not just generalize the response even it means doing further research.
7. Then give prevention advice for next batch.
8. Use correct grammatical shona where applicable.
"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this product."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        max_completion_tokens=180,
        temperature=0.3
    )

    return response.choices[0].message.content

# =========================
# AI ROUTER
# =========================

from dataclasses import dataclass
import re


@dataclass
class RouteResult:
    department: str
    confidence: float
    reason: str


class AIRouter:

    def __init__(self):

        self.departments = {

            "training_events": [

                "training",
                "practical",
                "offline",
                "online",

                "bulawayo",
                "harare",
                "gweru",
                "mutare",
                "masvingo",

                "venue",
                "schedule",
                "date",
                "event",

                "seat",
                "booking",
                "book",

                "deposit",

                "next training"

            ],

            "sales":[

                "price",

                "cost",

                "package",

                "premium",

                "basic",

                "upgrade",

                "promotion",

                "discount"

            ],
            

            "manufacturing": [
                "formula","recipe","manufacture","make",
                "problem","batch","foam","bleach",
                "soap","detergent","drink","paint",
                "polish","quality"
            ],

            "supplier": [
                "supplier","ingredients","chemical",
                "where can i buy","where do i buy",
                "sles","caustic","perfume",
                "citric acid","cmc","wax"
            ],

            "support": [
                "app","login","password",
                "download","payment failed",
                "approved","unlock","cannot open"
            ],

            "advisor": [
                "business","capital","profit",
                "pricing","investment","start business"
            ],

            "marketing": [
                "advert","poster","branding",
                "facebook","whatsapp marketing"
            ],

            "marketplace": [
                "marketplace","order","shopping",
                "cart","buy ingredients"
            ]
        }

    def clean(self, text):

        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        return text

    def route(self, message):

        message = self.clean(message)

        scores = {}

        for department, keywords in self.departments.items():

            score = 0

            for keyword in keywords:

                if keyword in message:
                    score += 1

            scores[department] = score

        best = max(scores, key=scores.get)

        if scores[best] == 0:

            return RouteResult(
                department="general",
                confidence=0,
                reason="No keyword matched"
            )

        return RouteResult(
            department=best,
            confidence=scores[best],
            reason=f"{scores[best]} keywords matched"
        )


router = AIRouter()

# =====================================
    # AI ROUTER (NEW)
    # =====================================

    route = router.route(incoming)

    if incoming.startswith("ai "):

        question = incoming[3:]

        answer = ai_virtual_employee(

            phone,

            question,

            route.department

        )

        send_message(phone, answer)

        return jsonify({"status":"ok"})

    print("=" * 50)
    print("AI ROUTER")
    print("Message:", incoming)
    print("Department:", route.department)
    print("Confidence:", route.confidence)
    print("=" * 50)
