"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Menu Blueprint (menu_bp)                   ║
║                                                              ║
║   Everything about the food: listing, search, CRUD, photos, ║
║   and the all-important Out-of-Stock toggle.                 ║
║                                                              ║
║   Day 3  theory: ATOMIC operations (find_one_and_update)     ║
║                 — the stock toggle is one indivisible step    ║
║   Day 6  theory: Caching the menu (cache-aside + TTL)         ║
║   Day 12 course: Text index for full-text search              ║
║   Day 16 course: embedding the image_id reference             ║
║   plan.md     : GridFS for menu item photos                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import threading
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, send_file, Response

from auth import require_role
from config import Config
from db import (menu_col, reviews_col, fs,
                serialize_doc, serialize_list, parse_object_id)
from extensions import socketio

menu_bp = Blueprint("menu", __name__, url_prefix="/api/menu")


# ─────────────────────────────────────────────────────────────────
# IN-MEMORY MENU CACHE  (Day 6 theory: cache-aside pattern)
# ─────────────────────────────────────────────────────────────────
# The menu is read HEAVILY (every student opens it) but changes
# rarely → textbook cache candidate. On a real scaled deployment this
# key would live in Redis; here we mimic it with a dict + TTL so the
# concept is visible in the code. Writes invalidate the cache.
_menu_cache = {"data": None, "expires_at": 0}
_menu_cache_lock = threading.Lock()


def _invalidate_menu_cache():
    """Drop the cached menu so the next read fetches fresh data."""
    with _menu_cache_lock:
        _menu_cache["data"] = None
        _menu_cache["expires_at"] = 0


def _get_cached_menu(force=False):
    """Return the available menu, serving from cache if fresh."""
    # Fast path: a lock-free peek is fine for a HIT (the dict read is
    # atomic in CPython). Only the MISS path needs the lock so two cold
    # starts don't both hammer MongoDB.
    if not force and _menu_cache["data"] is not None and time.time() < _menu_cache["expires_at"]:
        # CACHE HIT — no database round-trip at all (Day 6).
        return _menu_cache["data"]

    # CACHE MISS — query MongoDB, then store for next time (thread-safe).
    with _menu_cache_lock:
        # Re-check inside the lock: another thread may have just filled it.
        if (not force and _menu_cache["data"] is not None
                and time.time() < _menu_cache["expires_at"]):
            return _menu_cache["data"]
        items = list(menu_col.find({"is_available": True}).sort("category", 1))
        items = serialize_list(items)
        _menu_cache["data"] = items
        _menu_cache["expires_at"] = time.time() + Config.MENU_CACHE_TTL
        return items


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────
def _avg_rating(item_id):
    """Compute the average rating for a dish (or 0 if none yet)."""
    pipeline = [
        {"$match": {"item_id": item_id}},
        {"$group": {"_id": "$item_id", "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}},
    ]
    row = next(reviews_col.aggregate(pipeline), None)
    if not row:
        return 0.0, 0
    return round(row["avg"], 1), row["n"]


# ─────────────────────────────────────────────────────────────────
# ROUTE: LIST / ACTIVE MENU  (GET /api/menu)
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("", methods=["GET"])
@menu_bp.route("/", methods=["GET"])
def get_menu():
    """Return all currently-available dishes (cached).

    Optional query params:
      ?category=South Indian   — filter by category
      ?search=dosa             — full-text search (Day 12)
    """
    category = request.args.get("category")
    search = (request.args.get("search") or "").strip()

    # Full-text search takes a different code path (uses the text index).
    if search:
        cursor = menu_col.find(
            {"$text": {"$search": search}, "is_available": True},
            {"score": {"$meta": "textScore"}},
        ).sort([("score", {"$meta": "textScore"})])
        items = serialize_list(cursor)
        return jsonify({"success": True, "data": items, "query": search})

    # Cached path (the hot path — every student hits this).
    items = _get_cached_menu()
    if category:
        items = [i for i in items if i.get("category") == category]
    return jsonify({"success": True, "data": items})


# ─────────────────────────────────────────────────────────────────
# ROUTE: SINGLE DISH + ITS REVIEWS  (GET /api/menu/<id>)
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/<item_id>", methods=["GET"])
def get_item(item_id):
    oid, err = parse_object_id(item_id)
    if err:
        return jsonify({"success": False, "error": err}), 400

    item = menu_col.find_one({"_id": oid})
    if not item:
        return jsonify({"success": False, "error": "Dish not found."}), 404

    # Attach recent reviews (Day 16: referencing — separate collection).
    revs = list(reviews_col.find({"item_id": oid})
                .sort("created_at", -1).limit(20))
    item = serialize_doc(item)
    item["reviews"] = serialize_list(revs)
    avg, n = _avg_rating(oid)
    item["avg_rating"] = avg
    item["total_ratings"] = n
    return jsonify({"success": True, "data": item})


# ─────────────────────────────────────────────────────────────────
# ROUTE: CATEGORIES  (GET /api/menu/categories/list)
# ─────────────────────────────────────────────────────────────────
# NOTE: this more-specific route is declared BEFORE /<item_id> so
# Flask doesn't treat "categories" as an item_id (Day 24 course).
@menu_bp.route("/categories/list", methods=["GET"])
def list_categories():
    """Return the distinct list of dish categories."""
    cats = menu_col.distinct("category")
    return jsonify({"success": True, "data": sorted(cats)})


# ─────────────────────────────────────────────────────────────────
# ROUTE: DISH OF THE DAY  (GET /api/menu/dish-of-the-day)
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/dish-of-the-day", methods=["GET"])
def dish_of_the_day():
    """Return the dish flagged as the daily special (plan.md add-on)."""
    item = menu_col.find_one({"is_daily_special": True, "is_available": True})
    if not item:
        # Fallback: pick the highest-rated available dish.
        item = menu_col.find_one({"is_available": True, "avg_rating": {"$gte": 4}})
    return jsonify({"success": True, "data": serialize_doc(item)})


# ─────────────────────────────────────────────────────────────────
# ROUTE: CREATE DISH  (POST /api/menu)  — admin only
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("", methods=["POST"])
@menu_bp.route("/", methods=["POST"])
@require_role("admin")
def create_item():
    """Add a new dish to the menu (Day 6 course: insert_one)."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "Dish name is required."}), 400

    price = float(data.get("price", 0))
    if price < 0:
        return jsonify({"success": False, "error": "Price cannot be negative."}), 400

    doc = {
        "name": name,
        "category": (data.get("category") or "Snacks").strip(),
        "price": round(price, 2),
        "description": (data.get("description") or "").strip(),
        "image_id": None,                 # set later via image upload
        "emoji": data.get("emoji", "🍽️"),  # shown until a photo is uploaded
        "is_available": True,
        "stock": int(data.get("stock", 50)),   # inventory count
        "prep_time_mins": int(data.get("prep_time_mins", 5)),
        "avg_rating": 0.0,
        "total_ratings": 0,
        "is_daily_special": bool(data.get("is_daily_special", False)),
        "tags": data.get("tags", []),
        "created_at": datetime.now(timezone.utc),
    }
    result = menu_col.insert_one(doc)
    _invalidate_menu_cache()
    return jsonify({"success": True, "message": "Dish added to the menu!",
                    "data": {"_id": str(result.inserted_id)}}), 201


# ─────────────────────────────────────────────────────────────────
# ROUTE: UPDATE DISH  (PUT /api/menu/<id>)  — admin only
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/<item_id>", methods=["PUT"])
@require_role("admin")
def update_item(item_id):
    """Partially update a dish (Day 8 course: $set)."""
    oid, err = parse_object_id(item_id)
    if err:
        return jsonify({"success": False, "error": err}), 400

    data = request.get_json(silent=True) or {}
    allowed = {"name", "category", "price", "description", "is_available",
               "stock", "prep_time_mins", "is_daily_special", "emoji", "tags"}
    update = {}
    for k, v in data.items():
        if k in allowed:
            if k == "price":
                v = round(float(v), 2)
            if k in ("stock", "prep_time_mins"):
                v = int(v)
            if k in ("is_available", "is_daily_special"):
                v = bool(v)
            update[k] = v
    if not update:
        return jsonify({"success": False, "error": "No updatable fields sent."}), 400

    update["updated_at"] = datetime.now(timezone.utc)
    result = menu_col.update_one({"_id": oid}, {"$set": update})
    if result.matched_count == 0:
        return jsonify({"success": False, "error": "Dish not found."}), 404

    _invalidate_menu_cache()
    socketio.emit("menu_changed", {"item_id": item_id})
    return jsonify({"success": True, "message": "Dish updated."})


# ─────────────────────────────────────────────────────────────────
# ROUTE: DELETE DISH  (DELETE /api/menu/<id>)  — admin only
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/<item_id>", methods=["DELETE"])
@require_role("admin")
def delete_item(item_id):
    oid, err = parse_object_id(item_id)
    if err:
        return jsonify({"success": False, "error": err}), 400
    result = menu_col.delete_one({"_id": oid})
    if result.deleted_count == 0:
        return jsonify({"success": False, "error": "Dish not found."}), 404
    _invalidate_menu_cache()
    socketio.emit("menu_changed", {"item_id": item_id})
    return jsonify({"success": True, "message": "Dish removed from menu."})


# ─────────────────────────────────────────────────────────────────
# ROUTE: TOGGLE AVAILABILITY  (PATCH /api/menu/<id>/availability)
#   — staff OR admin. This is the ATOMIC Out-of-Stock button.
# ─────────────────────────────────────────────────────────────────
# Day 3 theory: find_one_and_update is ATOMIC. If two staff members
# tap "Out of Stock" at the same instant, MongoDB serializes the
# updates — no race condition, no lost update. The whole canteen sees
# the new state instantly via the menu_changed WebSocket event.
@menu_bp.route("/<item_id>/availability", methods=["PATCH"])
@require_role("staff", "admin")
def toggle_availability(item_id):
    oid, err = parse_object_id(item_id)
    if err:
        return jsonify({"success": False, "error": err}), 400

    data = request.get_json(silent=True) or {}
    available = data.get("is_available")
    if available is None:
        # Flip whatever the current state is.
        item = menu_col.find_one({"_id": oid}, {"is_available": 1})
        if not item:
            return jsonify({"success": False, "error": "Dish not found."}), 404
        available = not item["is_available"]

    updated = menu_col.find_one_and_update(
        {"_id": oid},
        {"$set": {"is_available": bool(available)}},
        return_document=True,            # return the NEW document
    )
    if not updated:
        return jsonify({"success": False, "error": "Dish not found."}), 404

    _invalidate_menu_cache()
    # Broadcast to every connected student: this dish just went in/out
    # of stock — gray the card out instantly (plan.md real-time add-on).
    socketio.emit("menu_changed", {"item_id": item_id,
                                   "is_available": bool(available)})
    return jsonify({"success": True,
                    "message": f"{'Available' if available else 'Out of stock'} now!",
                    "data": {"is_available": bool(available)}})


# ─────────────────────────────────────────────────────────────────
# ROUTE: UPLOAD PHOTO  (POST /api/menu/<id>/image)  — admin/staff
# ─────────────────────────────────────────────────────────────────
# plan.md: images stored in MongoDB via GridFS (pymongo).
@menu_bp.route("/<item_id>/image", methods=["POST"])
@require_role("staff", "admin")
def upload_image(item_id):
    oid, err = parse_object_id(item_id)
    if err:
        return jsonify({"success": False, "error": err}), 400
    if fs is None:
        return jsonify({"success": False, "error": "GridFS unavailable."}), 500
    if "image" not in request.files:
        return jsonify({"success": False, "error": "No 'image' file in request."}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"success": False, "error": "Empty filename."}), 400

    # Store the binary in GridFS, then save the new file id on the dish.
    image_id = fs.put(file.read(), filename=file.filename,
                      content_type=file.mimetype or "image/jpeg")
    # Remove any previous photo to avoid orphaned files piling up.
    old = menu_col.find_one({"_id": oid}, {"image_id": 1})
    if old and old.get("image_id"):
        try:
            fs.delete(old["image_id"])
        except Exception:
            pass
    menu_col.update_one({"_id": oid}, {"$set": {"image_id": image_id}})
    _invalidate_menu_cache()
    socketio.emit("menu_changed", {"item_id": item_id})
    return jsonify({"success": True, "message": "Photo uploaded.",
                    "data": {"image_id": str(image_id)}}), 201


# ─────────────────────────────────────────────────────────────────
# ROUTE: SERVE PHOTO  (GET /api/menu/<id>/image)  — public
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/<item_id>/image", methods=["GET"])
def get_image(item_id):
    oid, err = parse_object_id(item_id)
    if err:
        return jsonify({"success": False, "error": err}), 400
    item = menu_col.find_one({"_id": oid}, {"image_id": 1})
    if not item or not item.get("image_id") or fs is None:
        return Response(status=404)
    try:
        out = fs.get(item["image_id"])
        return send_file(out, mimetype=out.content_type or "image/jpeg")
    except Exception:
        return Response(status=404)
