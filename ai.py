import os
import json
import base64
import re
from dataclasses import dataclass

from openai import OpenAI

from database import get_db, release_db
from services import *
from config import *
from utils import safe_text

openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

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
    release_db(conn)
    return count

# =========================
# AI MEMORY SYSTEM
# =========================

MAX_MEMORY_MESSAGES = 12   # last 6 exchanges

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
    release_db(conn)


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
    release_db(conn)

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

    release_db(conn)

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
    release_db(conn)

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

    release_db(conn)

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

    release_db(conn)

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

    release_db(conn)

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
        release_db(conn)

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

def get_department_knowledge(department):

    departments = {

        # ==========================================
        # MANUFACTURING
        # ==========================================
        "manufacturing": {

            "title": "Manufacturing Department",

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "database_tables": [

                "lesson_content",
                "manufacturing_guides",
                "quality_control"

            ],

            "can_search_vector": True,
            "can_query_database": True,
            "can_update_profile": True,
            "live_data": False

        },

        # ==========================================
        # TRAINING
        # ==========================================
        "training_events": {

            "title": "Training Department",

            "vector_store": None,

            "database_tables": [

                "training_events",
                "training_registrations"

            ],

            "can_search_vector": False,
            "can_query_database": True,
            "can_update_profile": False,
            "live_data": True

        },

        # ==========================================
        # SUPPLIERS
        # ==========================================
        "supplier": {

            "title": "Supplier Department",

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "database_tables": [

                "suppliers",
                "ingredients",
                "packaging"

            ],

            "can_search_vector": True,
            "can_query_database": True,
            "can_update_profile": False,
            "live_data": True

        },

        # ==========================================
        # SALES
        # ==========================================
        "sales": {

            "title": "Sales Department",

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "database_tables": [

                "packages",
                "promotions"

            ],

            "can_search_vector": True,
            "can_query_database": True,
            "can_update_profile": False,
            "live_data": True

        },

        # ==========================================
        # BUSINESS
        # ==========================================
        "advisor": {

            "title": "Business Advisor",

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "database_tables": [

                "business_guides",
                "profit_calculators"

            ],

            "can_search_vector": True,
            "can_query_database": False,
            "can_update_profile": True,
            "live_data": False

        },

        # ==========================================
        # SUPPORT
        # ==========================================
        "support": {

            "title": "Customer Support",

            "vector_store": None,

            "database_tables": [

                "users",
                "payments"

            ],

            "can_search_vector": False,
            "can_query_database": True,
            "can_update_profile": True,
            "live_data": True

        },

        # ==========================================
        # MARKETPLACE
        # ==========================================
        "marketplace": {

            "title": "Marketplace",

            "vector_store": None,

            "database_tables": [

                "marketplace"

            ],

            "can_search_vector": False,
            "can_query_database": True,
            "can_update_profile": False,
            "live_data": True

        },

        # ==========================================
        # MARKETING
        # ==========================================
        "marketing": {

            "title": "Marketing Department",

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "database_tables": [

                "marketing_templates",
                "branding"

            ],

            "can_search_vector": True,
            "can_query_database": False,
            "can_update_profile": False,
            "live_data": False

        },

        # ==========================================
        # GENERAL
        # ==========================================
        "general": {

            "title": "General Assistant",

            "vector_store": os.getenv("ARACHIS_VECTOR_STORE_ID"),

            "database_tables": [],

            "can_search_vector": True,
            "can_query_database": False,
            "can_update_profile": True,
            "live_data": False

        }

    }

    return departments.get(
        department,
        departments["general"]
    )

def ai_department_router(phone, question):
    """
    AI-powered department router.

    No keyword matching.
    GPT decides which Arachis department should handle
    the customer's question based on the current question,
    recent conversation and customer context.
    """

    profile = get_customer_profile(phone)

    # Use a single conversation memory for the virtual employee.
    memory = get_memory(phone, "virtual_employee")

    memory_text = ""

    for message in memory[-10:]:
        role = message.get("role", "")
        content = message.get("content", "")

        memory_text += f"{role}: {content}\n"

    prompt = f"""
You are the CENTRAL AI ROUTER for Arachis Manufacturing.

Your job is NOT to answer the customer.

Your job is to understand the customer's CURRENT INTENT and
send the conversation to the correct Arachis department.

IMPORTANT:

DO NOT use keywords or simple word matching.

Understand the meaning of the customer's question using:
1. The current message
2. Previous conversation
3. The customer's context
4. The customer's current topic

AVAILABLE DEPARTMENTS:

manufacturing
- Product formulas
- Manufacturing procedures
- Ingredients and chemical functions
- Production problems
- Batch calculations
- Product troubleshooting
- Quality control
- Manufacturing lessons

supplier
- Where to buy ingredients
- Raw material suppliers
- Packaging suppliers
- Equipment suppliers
- Supplier availability

sales
- Arachis packages
- Training packages
- Prices
- Promotions
- Upgrades
- What is included in a package

advisor
- Business planning
- Profit
- Pricing products
- Investment
- Starting or growing a business
- Business strategy

support
- App problems
- Login problems
- Lesson access
- Payment problems
- Account problems
- Downloads
- Technical problems

training_events
- Practical training
- Training dates
- Venues
- Registration
- Deposits
- Training seats
- Training schedules
- Online training information

marketing
- Advertising
- WhatsApp marketing
- Facebook marketing
- Branding
- Posters
- Customer acquisition

marketplace
- Marketplace listings
- Marketplace orders
- Buying or selling through the marketplace

general
- Questions that do not clearly belong to another department
- General Arachis information

IMPORTANT CONVERSATION RULE:

The customer's latest message may be a follow-up.

Example:

Customer:
"How do I make dishwash?"

Assistant:
[answers]

Customer:
"Give me the formula."

The second message means the customer wants the dishwash formula.
Do NOT treat it as a new unrelated conversation.

Another example:

Customer:
"Where can I buy SLES?"

Assistant:
[answers]

Customer:
"What about in Bulawayo?"

This is still a SUPPLIER conversation.

Another example:

Customer:
"I paid for Premium."

Assistant:
[answers]

Customer:
"It is still locked."

This is still a SUPPORT conversation.

CURRENT CUSTOMER PROFILE:

{json.dumps(profile, indent=2)}

RECENT CONVERSATION:

{memory_text}

CURRENT CUSTOMER MESSAGE:

{question}

Return ONLY valid JSON in this exact format:

{{
    "department": "manufacturing",
    "reason": "The customer is asking for a product formulation."
}}

The department MUST be one of:

manufacturing
supplier
sales
advisor
support
training_events
marketing
marketplace
general
"""

    try:

        response = openai_client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=prompt
        )

        result = json.loads(response.output_text)

        department = result.get("department", "general")

        allowed_departments = {
            "manufacturing",
            "supplier",
            "sales",
            "advisor",
            "support",
            "training_events",
            "marketing",
            "marketplace",
            "general"
        }

        if department not in allowed_departments:
            department = "general"

        print("=" * 60)
        print("AI DEPARTMENT ROUTER")
        print("Department:", department)
        print("Reason:", result.get("reason", ""))
        print("=" * 60)

        return department

    except Exception as e:

        print("AI DEPARTMENT ROUTER ERROR:", e)

        return "general"

# ==========================================
# ARACHIS AI VIRTUAL EMPLOYEE
# ==========================================

def ai_virtual_employee(phone, question, department=None):

    if department is None:
        department = ai_department_router(phone, question)

    print("=" * 60)
    print("ARACHIS VIRTUAL EMPLOYEE")
    print("Phone:", phone)
    print("Department:", department)
    print("Question:", question)
    print("=" * 60)
        
    user = get_user(phone)

    profile = get_customer_profile(phone)

    # ==========================================
    # VIRTUAL EMPLOYEE MEMORY
    # ==========================================

    memory_messages = get_memory(phone, "virtual_employee")

    memory_text = ""

    for m in memory_messages:
        memory_text += f"{m['role']}: {m['content']}\n"

    print("=" * 60)
    print("VIRTUAL EMPLOYEE MEMORY")
    print(memory_text)
    print("=" * 60)

    department_prompt = build_department_prompt(department)

    department_knowledge = get_department_knowledge(department)

    # ==========================================
    # LIVE DEPARTMENT DATA
    # ==========================================

    live_context = ""

    # ------------------------------------------
    # TRAINING
    # ------------------------------------------

    if department == "training_events":

        event = get_next_training()

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

            available = seats - booked

            live_context = f"""

    CURRENT TRAINING EVENT

    Title:
    {title}

    City:
    {city}

    Venue:
    {venue}

    Date:
    {event_date}

    Time:
    {start_time}

    Course Fee:
    ${fee}

    Booking Deposit:
    ${deposit}

    Products:
    {products}

    Booked Seats:
    {booked}

    Remaining Seats:
    {available}

    Registration Status:
    {status}

    Always use this information instead of guessing.

    """

        else:

            live_context = """

    There are currently no upcoming training events.

    Never invent training dates.

    """


    instructions = f"""
{department_prompt}

Department

{department_knowledge["title"]}

Database Tables

{", ".join(department_knowledge["database_tables"])}

Capabilities

Vector Search: {department_knowledge["can_search_vector"]}

Database Access: {department_knowledge["can_query_database"]}

Live Data: {department_knowledge["live_data"]}

Conversation Memory

Recent conversation with this customer:

{memory_text}

Use this conversation history to understand the customer's current question.

IMPORTANT CONVERSATION RULES:

- Remember what the customer was discussing.
- Treat short follow-up questions as part of the current conversation.
- Do not ask the customer to repeat information that is already clear.
- If the customer says "give me the formula", determine which product they were discussing.
- If the customer says "what about in Bulawayo?", determine what they are referring to from the previous conversation.
- If the customer changes topic, follow the new topic naturally.
- Do not mix unrelated information from previous conversations into the current answer.

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

Live Department Data

{live_context}

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
    # ==========================================
    # BUILD AI TOOLS
    # ==========================================

    tools = []

    if department_knowledge.get("can_search_vector"):

        vector_store = department_knowledge.get("vector_store")

        if vector_store:

            tools.append({

                "type": "file_search",

                "vector_store_ids": [

                    vector_store

                ]

            })

    print("=" * 60)
    print("AI TOOLS")
    print(tools)
    print("=" * 60)

    try:

        response = openai_client.responses.create(

            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),

            instructions=instructions,

            input=question,

            tools=tools
        )
        answer = response.output_text.strip()

        # ==========================================
        # SAVE VIRTUAL EMPLOYEE MEMORY
        # ==========================================

        save_memory(
            phone,
            "virtual_employee",
            "user",
            question
        )

        save_memory(
            phone,
            "virtual_employee",
            "assistant",
            answer
        )

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


