"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Database Layer                                ║
║                                                              ║
║   ONE MongoDB connection is created here and reused by every  ║
║   blueprint. Opening a connection per request would be slow;   ║
║   PyMongo maintains a connection pool under the hood.         ║
║                                                              ║
║   Day 4  (course): MongoClient, connection pooling             ║
║   Day 5  (course): ObjectId, datetime, BSON types             ║
║   Day 12 (course): create_index() for fast queries             ║
║   Day 16 (course): embedding vs referencing (snapshotting)     ║
║   Day 26 (course): compound & text indexes for query speed     ║
║   Day 6  (theory) : TTL indexes, replica sets, CAP consistency  ║
╚══════════════════════════════════════════════════════════════╝
"""

from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.errors import ServerSelectionTimeoutError

from config import Config


# ─────────────────────────────────────────────────────────────────
# CONNECTION  (Day 4: MongoClient)
# ─────────────────────────────────────────────────────────────────
# A single client per process. PyMongo pools connections internally,
# so concurrent Flask workers can all share this safely.
_client = MongoClient(Config.MONGO_URI)
db = _client[Config.MONGO_DB_NAME]

# ─────────────────────────────────────────────────────────────────
# COLLECTION REFERENCES
# ─────────────────────────────────────────────────────────────────
# Named like the plan.md schema: users, menu_items, orders, reviews,
# daily_tokens. GridFS handles binary image uploads separately.
users_col = db["users"]
menu_col = db["menu_items"]
orders_col = db["orders"]
reviews_col = db["reviews"]
tokens_col = db["daily_tokens"]

# GridFS stores menu item photos as binary chunks inside MongoDB
# (plan.md: "Images | GridFS (pymongo)"). Two collections are created
# automatically: fs.files + fs.chunks.
try:
    import gridfs
    fs = gridfs.GridFS(db)
except Exception:  # pragma: no cover - gridfs is part of pymongo
    fs = None


# ─────────────────────────────────────────────────────────────────
# INDEXES  (Day 12 & 26: indexes make queries fast — IXSCAN vs COLLSCAN)
# ─────────────────────────────────────────────────────────────────
def create_indexes():
    """Create all indexes the app relies on.

    Idempotent: calling it again does nothing — MongoDB skips indexes
    that already exist. Safe to run on every startup.
    """
    # Wait for MongoDB to be reachable before creating indexes. PyMongo's
    # connection is lazy, so the first command is what actually opens the
    # socket — this retry keeps the app from crashing when Mongo is still
    # starting up (e.g. a slow container in docker-compose).
    import time as _time
    for attempt in range(1, 6):
        try:
            _client.admin.command("ping")
            break
        except ServerSelectionTimeoutError:
            if attempt == 5:
                raise
            print(f"⏳  Waiting for MongoDB (attempt {attempt}/5)…")
            _time.sleep(2)

    # --- users: unique email so two accounts can't share one email ---
    users_col.create_index("email", unique=True)
    users_col.create_index("roll_number")

    # --- menu_items: filter by category / availability, full-text search ---
    menu_col.create_index("category")
    menu_col.create_index("is_available")
    # Day 12 (course): a TEXT index powers /api/menu/search?q=
    menu_col.create_index([("name", TEXT), ("description", TEXT)],
                          name="menu_text_search")

    # --- orders: the most-queried collection in the whole app ---
    orders_col.create_index("student_id")
    orders_col.create_index("status")
    orders_col.create_index("placed_at")
    # Day 26 (course): COMPOUND index — the live-orders dashboard
    # always filters by status and sorts by newest-first. One index
    # that serves BOTH the filter and the sort = fastest possible.
    orders_col.create_index([("status", ASCENDING), ("placed_at", DESCENDING)],
                            name="orders_live_compound")
    orders_col.create_index("token_number")

    # Day 6 (theory): TTL INDEX — the document auto-deletes itself when
    # `expires_at` is reached. We use this to reset the token counter
    # automatically at the end of each day. expireAfterSeconds=0 means
    # "expire exactly when expires_at arrives" (not a fixed offset).
    tokens_col.create_index("expires_at", expireAfterSeconds=0)

    # --- reviews: list a dish's newest reviews first ---
    reviews_col.create_index([("item_id", ASCENDING), ("created_at", DESCENDING)])


# ─────────────────────────────────────────────────────────────────
# SERIALIZATION HELPERS  (Day 5: ObjectId & datetime → JSON strings)
# ─────────────────────────────────────────────────────────────────
# Flask's jsonify() cannot turn ObjectId / datetime into JSON. Every
# document leaving the API must be "serialized" to plain Python types.
def serialize_doc(doc):
    """Convert ONE MongoDB document into a JSON-safe dict.

    Recursively handles nested dicts and lists so embedded order items
    (Day 16: snapshotting) serialize correctly too.
    """
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        return doc.isoformat()

    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            # Never leak the password hash to the frontend.
            if k == "password_hash":
                continue
            out[k] = serialize_doc(v)
        return out
    return doc


def serialize_list(cursor):
    """Serialize a list / PyMongo cursor of documents."""
    return [serialize_doc(doc) for doc in cursor]


def parse_object_id(_id):
    """Safely turn a string into an ObjectId.

    Returns (ObjectId, None) on success, (None, error_message) on
    failure — keeping route code free of repeated try/except blocks.
    """
    try:
        return ObjectId(_id), None
    except (InvalidId, TypeError):
        return None, f"Invalid id '{_id}' — expected a 24-char hex string."
