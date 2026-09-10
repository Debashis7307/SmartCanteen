"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Database Seed Script                         ║
║                                                              ║
║   Loads a realistic Indian college-canteen menu, three demo   ║
║   accounts (student / staff / admin), and a WEEK of demo       ║
║   orders so the analytics dashboard looks alive on first run.  ║
║                                                              ║
║   Day 5 theory : bcrypt password hashing                      ║
║   Day 6 course: insert_many / insert_one                      ║
║   Day 16 course: snapshotting price into each order           ║
║   Day 15 course: realistic timestamps for the heatmap          ║
║                                                              ║
║   Usage:  python seed.py   (run once, before `python app.py`)  ║
╚══════════════════════════════════════════════════════════════╝
"""

import random
from datetime import datetime, timezone, timedelta

import bcrypt
from bson import ObjectId
from pymongo import MongoClient

from config import Config

# Windows console defaults to cp1252 which can't print emojis — force UTF-8.
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────
# CONNECT
# ─────────────────────────────────────────────────────────────────
client = MongoClient(Config.MONGO_URI)
db = client[Config.MONGO_DB_NAME]


# ─────────────────────────────────────────────────────────────────
# THE MENU — a real Indian college canteen (28 dishes, 6 categories)
# ─────────────────────────────────────────────────────────────────
# (name, category, price, emoji, prep_mins, stock, tags, description)
MENU = [
    # --- South Indian ---
    ("Masala Dosa", "South Indian", 45, "🥞", 6, 60, ["vegetarian", "breakfast", "popular"],
     "Crispy rice crepe with spiced potato filling & coconut chutney."),
    ("Idli Sambar", "South Indian", 35, "🍥", 5, 40, ["vegetarian", "breakfast", "steamed"],
     "Soft steamed rice cakes dunked in lentil sambar."),
    ("Medu Vada", "South Indian", 30, "🍩", 6, 30, ["vegetarian", "breakfast"],
     "Crispy fried lentil donuts with chutney."),
    ("Rava Dosa", "South Indian", 50, "🥞", 7, 25, ["vegetarian", "breakfast"],
     "Lacy semolina dosa with onion & curry leaves."),
    ("Mysore Masala Dosa", "South Indian", 55, "🥞", 8, 20, ["vegetarian", "spicy", "popular"],
     "Dosa smeared with fiery red chutney & potato masala."),

    # --- North Indian ---
    ("Chole Bhature", "North Indian", 70, "🫓", 10, 35, ["vegetarian", "lunch", "popular"],
     "Spicy chickpea curry with fluffy fried bhature."),
    ("Aloo Paratha", "North Indian", 40, "🫓", 7, 45, ["vegetarian", "breakfast"],
     "Stuffed wheat flatbread with butter & curd."),
    ("Paneer Butter Masala", "North Indian", 90, "🍲", 12, 25, ["vegetarian", "lunch", "premium"],
     "Cottage cheese in a rich creamy tomato gravy."),
    ("Rajma Chawal", "North Indian", 65, "🍚", 10, 30, ["vegetarian", "lunch"],
     "Kidney bean curry over steamed basmati rice."),
    ("Dal Makhani", "North Indian", 75, "🍲", 12, 25, ["vegetarian", "lunch"],
     "Slow-cooked black lentils in a buttery gravy."),

    # --- Snacks ---
    ("Samosa", "Snacks", 15, "🥟", 4, 80, ["vegetarian", "snack", "popular"],
     "Golden pastry pocket stuffed with spiced potato & peas."),
    ("Veg Burger", "Snacks", 50, "🍔", 6, 40, ["vegetarian", "snack"],
     "Crispy veg patty with lettuce, cheese & mayo."),
    ("Veg Sandwich", "Snacks", 40, "🥪", 5, 35, ["vegetarian", "snack"],
     "Grilled triple-layer sandwich with mint chutney."),
    ("French Fries", "Snacks", 45, "🍟", 5, 50, ["vegetarian", "snack"],
     "Golden crispy fries sprinkled with peri-peri masala."),
    ("Bread Pakora", "Snacks", 25, "🍞", 5, 30, ["vegetarian", "snack"],
     "Bread slices stuffed with potato, deep-fried crisp."),
    ("Veg Spring Roll", "Snacks", 35, "🥡", 6, 25, ["vegetarian", "snack"],
     "Crunchy rolls stuffed with shredded veggies."),

    # --- Beverages ---
    ("Masala Chai", "Beverages", 12, "🍵", 3, 100, ["vegetarian", "hot", "popular"],
     "Indian spiced milk tea brewed strong."),
    ("Cold Coffee", "Beverages", 45, "🥤", 3, 40, ["vegetarian", "cold"],
     "Frothy iced coffee blended with milk & sugar."),
    ("Mango Lassi", "Beverages", 40, "🥭", 3, 35, ["vegetarian", "cold", "seasonal"],
     "Thick yogurt smoothie with sweet Alphonso mango."),
    ("Fresh Lime Soda", "Beverages", 25, "🍋", 2, 50, ["vegetarian", "cold"],
     "Zesty lime soda — sweet, salty, or mixed."),
    ("Filter Coffee", "Beverages", 20, "☕", 3, 60, ["vegetarian", "hot"],
     "South Indian decoction frothed with hot milk."),

    # --- Chinese ---
    ("Veg Hakka Noodles", "Chinese", 60, "🍜", 8, 35, ["vegetarian", "lunch"],
     "Wok-tossed noodles with veggies & soy."),
    ("Schezwan Fried Rice", "Chinese", 65, "🍚", 8, 30, ["vegetarian", "spicy", "lunch"],
     "Fiery Schezwan rice with crunchy veggies."),
    ("Veg Manchurian", "Chinese", 70, "🥡", 10, 25, ["vegetarian", "spicy"],
     "Fried veg balls tossed in a tangy garlic sauce."),

    # --- Desserts ---
    ("Gulab Jamun (2 pc)", "Desserts", 30, "🍮", 2, 40, ["vegetarian", "sweet"],
     "Warm milk dumplings soaked in rose syrup."),
    ("Vanilla Ice Cream", "Desserts", 35, "🍦", 1, 45, ["vegetarian", "cold", "sweet"],
     "Creamy vanilla scoop with a chocolate flake."),

    # --- Combos ---
    ("Mini Meals Thali", "Combos", 110, "🍛", 12, 30, ["vegetarian", "lunch", "value"],
     "Roti, rice, dal, sabzi, curd & salad — a full plate."),
    ("Breakfast Combo", "Combos", 80, "🍱", 8, 25, ["vegetarian", "breakfast", "value"],
     "2 idli + vada + masala dosa + filter coffee."),
]

# The dish we spotlight as "Dish of the Day" on day one.
DAILY_SPECIAL = "Chole Bhature"


# ─────────────────────────────────────────────────────────────────
# DEMO USERS
# ─────────────────────────────────────────────────────────────────
# (name, email, password, role, roll_number)
USERS = [
    ("Aarav Sharma", "aarav@college.edu", "student123", "student", "CS21001"),
    ("Priya Patel",  "priya@college.edu", "student123", "student", "CS21002"),
    ("Rahul Verma",  "rahul@college.edu", "student123", "student", "EC21015"),
    ("Sneha Reddy",  "sneha@college.edu", "student123", "student", "ME21008"),
    ("Karan Mehta",  "karan@college.edu", "student123", "student", "IT21021"),
    ("Ananya Iyer",  "ananya@college.edu", "student123", "student", "CS21033"),
    ("Canteen Staff", "staff@college.edu", "staff123", "staff", ""),
    ("Canteen Admin", "admin@college.edu", "admin123", "admin", ""),
]


# ─────────────────────────────────────────────────────────────────
# DEMO STUDENT NAMES (extra, for top-spenders variety)
# ─────────────────────────────────────────────────────────────────
EXTRA_STUDENTS = [
    "Vikram Nair", "Divya Gupta", "Arjun Rao", "Ishaan Khanna",
    "Meera Joshi", "Rohan Das", "Tara Singh", "Kabir Malhotra",
    "Nisha Pillai", "Aditya Bose",
]


# ─────────────────────────────────────────────────────────────────
# SAMPLE REVIEWS
# ─────────────────────────────────────────────────────────────────
REVIEW_TEMPLATES = [
    (5, "Absolutely loved it! Crispy and fresh."),
    (4, "Tasty, but a little extra salt today."),
    (5, "Best dosa on campus, hands down."),
    (3, "Decent. Took a while to come though."),
    (5, "Hot, fresh and worth every rupee."),
    (4, "Good portion size. Would order again."),
    (2, "Was a bit cold by the time I collected it."),
    (5, "Perfect with the morning chai!"),
]


# ─────────────────────────────────────────────────────────────────
# MAIN SEED
# ─────────────────────────────────────────────────────────────────
def main():
    print("🌱  Seeding SmartCanteen database...")

    # Wipe & reload (idempotent — safe to run repeatedly).
    db.users.delete_many({})
    db.menu_items.delete_many({})
    db.orders.delete_many({})
    db.reviews.delete_many({})
    db.daily_tokens.delete_many({})
    print("🗑️  Cleared existing collections.")

    # ── 1. Menu ──────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    menu_docs = []
    for name, cat, price, emoji, prep, stock, tags, desc in MENU:
        menu_docs.append({
            "name": name,
            "category": cat,
            "price": float(price),
            "description": desc,
            "image_id": None,
            "emoji": emoji,
            "is_available": True,
            "stock": stock,
            "prep_time_mins": prep,
            "avg_rating": round(random.uniform(3.8, 4.9), 1),
            "total_ratings": random.randint(20, 180),
            "is_daily_special": name == DAILY_SPECIAL,
            "tags": tags,
            "created_at": now,
        })
    menu_result = db.menu_items.insert_many(menu_docs)
    menu_ids = list(menu_result.inserted_ids)
    name_by_id = {d["name"]: d_id for d, d_id in zip(menu_docs, menu_ids)}
    print(f"🍽️  Inserted {len(menu_docs)} menu items across "
          f"{len({d['category'] for d in menu_docs})} categories.")

    # ── 2. Users (Day 5: bcrypt) ────────────────────────────────
    user_ids = {}
    for name, email, pw, role, roll in USERS:
        hashed = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())
        doc = {
            "name": name,
            "email": email,
            "password_hash": hashed.decode("utf-8"),
            "role": role,
            "roll_number": roll,
            "created_at": now - timedelta(days=30),
            "last_login": now - timedelta(hours=random.randint(1, 48)),
        }
        user_ids[email] = db.users.insert_one(doc).inserted_id
    # Extra students (for the top-spenders leaderboard).
    for nm in EXTRA_STUDENTS:
        email = nm.lower().replace(" ", ".") + "@college.edu"
        hashed = bcrypt.hashpw(b"student123", bcrypt.gensalt())
        doc = {
            "name": nm,
            "email": email,
            "password_hash": hashed.decode("utf-8"),
            "role": "student",
            "roll_number": "XX" + str(random.randint(10000, 99999)),
            "created_at": now - timedelta(days=random.randint(5, 60)),
            "last_login": now - timedelta(hours=random.randint(1, 200)),
        }
        user_ids[email] = db.users.insert_one(doc).inserted_id
    print(f"👤 Inserted {len(user_ids)} users "
          f"(student / staff / admin).")

    # ── 3. A week of demo orders ────────────────────────────────
    # Spread orders across the last 7 days, clustered around real
    # canteen rush hours so the peak-hours heatmap & revenue chart
    # look believable: breakfast ~9am, lunch ~1-2pm, snacks ~4-5pm.
    # Collect every student user email (the 6 named + 10 extras).
    student_emails = [u[1] for u in USERS if u[3] == "student"]
    student_emails += [nm.lower().replace(" ", ".") + "@college.edu"
                       for nm in EXTRA_STUDENTS]

    RUSH_WINDOWS = [
        (8, 30, 10, 30),    # breakfast 8:30–10:30
        (12, 15, 14, 30),   # lunch 12:15–14:30 (the big one)
        (16, 0, 17, 45),    # evening snacks 16:00–17:45
    ]

    order_docs = []
    token = 0
    total_revenue = 0.0
    for day_offset in range(6, -1, -1):          # 6 days ago → today
        day = now - timedelta(days=day_offset)
        # Lunch is the busiest → more orders then.
        day_count = random.randint(14, 26)
        for _ in range(day_count):
            sh, sm, eh, em = random.choice(RUSH_WINDOWS)
            hour = random.randint(sh, eh)
            minute = random.randint(0, 59)
            placed = day.replace(hour=hour, minute=minute, second=0,
                                 microsecond=0)
            # Pick 1–3 items for this order.
            n_items = random.choices([1, 2, 3], weights=[5, 4, 2])[0]
            chosen = random.sample(menu_docs, k=n_items)
            items = []
            total = 0.0
            for d in chosen:
                qty = random.randint(1, 2)
                items.append({
                    "item_id": str(name_by_id[d["name"]]),
                    "name": d["name"],
                    "price_at_order": d["price"],
                    "quantity": qty,
                    "emoji": d["emoji"],
                })
                total += d["price"] * qty

            token += 1
            # Older orders are mostly collected; today's are live.
            if day_offset >= 2:
                status = random.choices(
                    ["collected", "cancelled"],
                    weights=[9, 1])[0]
            elif day_offset == 1:
                status = random.choices(
                    ["collected", "preparing", "ready"], weights=[6, 2, 2])[0]
            else:  # today
                status = random.choices(
                    ["collected", "placed", "preparing", "ready"],
                    weights=[3, 3, 2, 2])[0]

            ready_at = placed + timedelta(minutes=random.randint(5, 12)) \
                if status in ("ready", "collected") else None
            collected_at = ready_at + timedelta(minutes=random.randint(1, 8)) \
                if status == "collected" else None

            student_name = random.choice(student_emails)
            order_docs.append({
                "token_number": token,
                "token_date": placed.strftime("%Y-%m-%d"),
                "student_id": user_ids[student_name],
                "student_name": student_emails_to_name(student_name),
                "items": items,
                "total_amount": round(total, 2),
                "status": status,
                "payment_status": "paid",   # demo model: pay upfront via QR
                "placed_at": placed,
                "ready_at": ready_at,
                "collected_at": collected_at,
                "estimated_wait_mins": random.randint(4, 12),
                "special_instructions": random.choice([
                    "", "", "", "Less spicy please",
                    "Extra chutney", "Pack separately", "No onion",
                ]),
            })
            if status in ("collected", "placed", "preparing", "ready"):
                total_revenue += total

    db.orders.insert_many(order_docs)
    print(f"🧾  Inserted {len(order_docs)} orders over 7 days "
          f"(≈₹{total_revenue:,.0f} revenue).")

    # ── 4. Reviews ──────────────────────────────────────────────
    review_docs = []
    student_pool = [e for e in user_ids if "@" in e]
    for d in menu_docs[:12]:                         # top 12 dishes
        for _ in range(random.randint(3, 6)):
            r, c = random.choice(REVIEW_TEMPLATES)
            email = random.choice(student_pool)
            review_docs.append({
                "item_id": name_by_id[d["name"]],
                "student_id": user_ids[email],
                "student_name": email.split("@")[0].replace(".", " ").title(),
                "rating": r,
                "comment": c,
                "created_at": now - timedelta(days=random.randint(0, 20)),
            })
    if review_docs:
        db.reviews.insert_many(review_docs)
    print(f"⭐  Inserted {len(review_docs)} dish reviews.")

    print("""
╔══════════════════════════════════════════════════════════════╗
║  ✅  SEED COMPLETE!                                          ║
║                                                              ║
║  Demo logins:                                                ║
║    Student : aarav@college.edu  /  student123                 ║
║    Staff   : staff@college.edu  /  staff123                  ║
║    Admin   : admin@college.edu  /  admin123                   ║
║                                                              ║
║  Now run:  python app.py   →  open http://localhost:5000      ║
╚══════════════════════════════════════════════════════════════╝""")


def student_emails_to_name(email):
    return email.split("@")[0].replace(".", " ").title()


if __name__ == "__main__":
    main()
