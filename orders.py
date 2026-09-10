"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Orders Blueprint (orders_bp)               ║
║                                                              ║
║   The transactional heart of the app. Placing an order must  ║
║   be SAFE even when 100 students click "Order" in the same   ║
║   millisecond and there's only one Samosa left.               ║
║                                                              ║
║   Day 3  theory: ATOMIC find_one_and_update (stock > 0 +     ║
║                 $inc -1 in one step → no race condition)       ║
║   Day 6  theory: CAP — we favour Consistency for stock so    ║
║                 two students never buy the last item          ║
║   Day 16 course: SNAPSHOT price & name INTO the order doc    ║
║                 (a receipt is immutable history)              ║
║   Day 28 course: multi-doc transactions (noted as the         ║
║                 replica-set upgrade path for true all-or-     ║
║                 nothing atomicity)                           ║
║   plan.md     : daily token counter via findOneAndUpdate +    ║
║                 TTL index that auto-resets at midnight         ║
╚══════════════════════════════════════════════════════════════╝
"""

from datetime import datetime, timezone, timedelta

from bson import ObjectId
from flask import Blueprint, request, jsonify

from auth import require_role, current_user
from db import (orders_col, menu_col, tokens_col, users_col,
                serialize_doc, serialize_list, parse_object_id)
from extensions import socketio

orders_bp = Blueprint("orders", __name__, url_prefix="/api/orders")

# IST = UTC+5:30. The canteen's "day" resets at LOCAL midnight, not UTC
# midnight (which would be 5:30 AM here and let yesterday's late orders
# collide with today's token numbers). A fixed offset avoids needing
# the tzdata package on Windows / slim Docker images.
IST = timezone(timedelta(hours=5, minutes=30))

# The ordered lifecycle an order walks through (plan.md schema).
STATUSES = ("placed", "preparing", "ready", "collected", "cancelled")
LIVE_STATUSES = ("placed", "preparing", "ready")  # still being worked on


# ─────────────────────────────────────────────────────────────────
# DAILY TOKEN COUNTER  (plan.md: findOneAndUpdate + upsert + TTL)
# ─────────────────────────────────────────────────────────────────
# One document per day holds `last_token`. Each new order atomically
# increments it. The TTL index (Day 6 theory) auto-deletes the row at
# midnight, so the next day starts fresh from token #1 again.
def _next_token():
    """Atomically reserve the next token number for today.

    find_one_and_update + upsert=True is the classic MongoDB counter
    pattern: read-and-increment happen as ONE atomic operation, so two
    students ordering simultaneously can NEVER receive the same token.
    """
    # Use IST so the counter resets at local midnight, not 5:30 AM.
    now_ist = datetime.now(IST)
    today = now_ist.strftime("%Y-%m-%d")
    # expires_at = start of tomorrow IST → the TTL index removes it then,
    # so the next day starts fresh from token #1.
    expires_at = (now_ist + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    doc = tokens_col.find_one_and_update(
        {"date": today},
        {"$inc": {"last_token": 1},
         "$setOnInsert": {"date": today, "expires_at": expires_at}},
        upsert=True,
        return_document=True,          # return the UPDATED document
    )
    return doc["last_token"], today


# ─────────────────────────────────────────────────────────────────
# ROUTE: PLACE ORDER  (POST /api/orders)  — student only
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("", methods=["POST"])
@orders_bp.route("/", methods=["POST"])
@require_role("student")
def place_order():
    """Create a new pre-order.

    Body: { items: [{item_id, quantity}], special_instructions? }
    """
    user = request.current_user
    data = request.get_json(silent=True) or {}

    cart = data.get("items")
    if not isinstance(cart, list) or not cart:
        return jsonify({"success": False,
                        "error": "Your cart is empty."}), 400

    # Guard against absurd carts (also caps the work one request can do).
    if len(cart) > 20:
        return jsonify({"success": False,
                        "error": "Too many distinct items (max 20)."}), 400

    instructions = (data.get("special_instructions") or "").strip()[:300]
    # Demo payment flow: the QR + "I've Paid" button sets paid=true.
    # We record it so the kitchen dashboard shows a Paid badge. (No real
    # money moves — this is the course-project stand-in for a gateway.)
    paid = bool(data.get("paid", False))

    # ── 1. Validate & snapshot every item ─────────────────────────
    # Day 16 (course): we COPY the current name & price INTO the order
    # so a future price hike never rewrites history. The order is a
    # frozen receipt.
    snapshot = []
    decremented = []   # (item_id, qty) we've already taken stock for
    total = 0.0
    total_prep = 0

    for line in cart:
        # Sanitize against NoSQL injection (Day 5): coerce to safe types.
        item_id = line.get("item_id")
        oid, err = parse_object_id(item_id)
        if err:
            _rollback_stock(decremented)
            return jsonify({"success": False, "error": f"Bad item id: {item_id}"}), 400
        qty = line.get("quantity", 1)
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            _rollback_stock(decremented)
            return jsonify({"success": False, "error": "Quantity must be a number."}), 400
        if qty < 1 or qty > 20:
            _rollback_stock(decremented)
            return jsonify({"success": False,
                            "error": "Quantity must be 1–20."}), 400

        # Day 3 theory: ATOMIC stock decrement. The filter `stock > 0`
        # AND the `$inc: -qty` run as ONE indivisible step. If two
        # students grab the last item, only ONE update matches — the
        # other gets None and we reject it. No race condition.
        updated = menu_col.find_one_and_update(
            {"_id": oid, "is_available": True, "stock": {"$gte": qty}},
            {"$inc": {"stock": -qty}},
            return_document=True,
        )
        if not updated:
            _rollback_stock(decremented)
            name = menu_col.find_one({"_id": oid}, {"name": 1})
            label = name["name"] if name else str(item_id)
            return jsonify({"success": False,
                            "error": f"'{label}' is out of stock or unavailable."}), 409

        decremented.append((oid, qty))
        snapshot.append({
            "item_id": str(oid),
            "name": updated["name"],            # frozen snapshot
            "price_at_order": updated["price"], # frozen snapshot
            "quantity": qty,
            "emoji": updated.get("emoji", "🍽️"),
        })
        total += updated["price"] * qty
        total_prep += updated.get("prep_time_mins", 5) * qty

    # ── 2. Reserve a token & estimate the wait ────────────────────
    token_number, token_date = _next_token()

    # Rough wait: how many orders are already in the kitchen queue, plus
    # prep time of this order. (A live countdown is shown on the UI.)
    ahead = orders_col.count_documents({"status": {"$in": LIVE_STATUSES},
                                         "placed_at": {"$lt": datetime.now(timezone.utc)}})
    estimated_wait = max(total_prep // max(len(snapshot), 1), 3) + (ahead // 3)

    now = datetime.now(timezone.utc)
    order_doc = {
        "token_number": token_number,
        "token_date": token_date,
        "student_id": ObjectId(user["user_id"]),
        "student_name": user["name"],
        "items": snapshot,
        "total_amount": round(total, 2),
        "status": "placed",
        "payment_status": "paid" if paid else "pending",
        "placed_at": now,
        "ready_at": None,
        "collected_at": None,
        "estimated_wait_mins": estimated_wait,
        "special_instructions": instructions,
    }
    result = orders_col.insert_one(order_doc)

    # ── 3. Notify the kitchen in real time ─────────────────────────
    # Day 4/7 theory: push the new order to the staff dashboard room
    # instantly — no refresh needed. The Change Stream thread also
    # broadcasts this, but emitting directly gives instant feedback.
    order_doc["_id"] = result.inserted_id
    payload = serialize_doc(order_doc)
    socketio.emit("new_order", payload, room="staff_dashboard")
    socketio.emit("order_status_update",
                  {"token": token_number, "status": "placed",
                   "order": payload},
                  room=f"order_{token_number}")

    return jsonify({"success": True,
                    "message": f"Order placed! Your token is #{token_number}.",
                    "data": payload}), 201


def _rollback_stock(decremented):
    """Compensate for stock we already subtracted before a failure.

    This is the 'compensating transaction' idea (Day 28 notes a true
    multi-document transaction as the cleaner replica-set alternative).
    We re-add what we took so the menu is left consistent.
    """
    for oid, qty in decremented:
        menu_col.update_one({"_id": oid}, {"$inc": {"stock": qty}})


# ─────────────────────────────────────────────────────────────────
# ROUTE: MY ORDERS  (GET /api/orders/my)  — student only
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("/my", methods=["GET"])
def my_orders():
    """Return the logged-in student's order history (newest first)."""
    user = current_user()
    if not user:
        return jsonify({"success": False, "error": "Login required."}), 401
    cursor = (orders_col.find({"student_id": ObjectId(user["user_id"])})
              .sort("placed_at", -1).limit(50))
    return jsonify({"success": True, "data": serialize_list(cursor)})


# ─────────────────────────────────────────────────────────────────
# ROUTE: ONE-TAP REORDER  (POST /api/orders/reorder/<id>)  — student
# ─────────────────────────────────────────────────────────────────
# plan.md add-on: re-buy yesterday's lunch in one click. We rebuild the
# cart from the stored snapshot so the student doesn't have to.
@orders_bp.route("/reorder/<order_id>", methods=["POST"])
@require_role("student")
def reorder(order_id):
    oid, err = parse_object_id(order_id)
    if err:
        return jsonify({"success": False, "error": err}), 400
    old = orders_col.find_one({"_id": oid,
                               "student_id": ObjectId(request.current_user["user_id"])})
    if not old:
        return jsonify({"success": False, "error": "Order not found."}), 404
    cart = [{"item_id": i["item_id"], "quantity": i["quantity"]}
            for i in old["items"]]
    return jsonify({"success": True,
                    "message": "Cart loaded — confirm to reorder.",
                    "data": {"items": cart}})


# ─────────────────────────────────────────────────────────────────
# ROUTE: LIVE ORDERS  (GET /api/orders/live)  — staff / admin
# ─────────────────────────────────────────────────────────────────
# Day 26 (course): the COMPOUND index (status, placed_at) serves this
# exact query at top speed — it's the staff's most-opened endpoint.
@orders_bp.route("/live", methods=["GET"])
@require_role("staff", "admin")
def live_orders():
    """Return all orders still being worked on, oldest-first."""
    cursor = (orders_col.find({"status": {"$in": list(LIVE_STATUSES)}})
              .sort([("status", 1), ("placed_at", 1)]))
    return jsonify({"success": True, "data": serialize_list(cursor)})


# ─────────────────────────────────────────────────────────────────
# ROUTE: ALL ORDERS (admin)  (GET /api/orders/all)  — admin
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("/all", methods=["GET"])
@require_role("admin")
def all_orders():
    """Return every order (paginated) for the admin table."""
    try:
        page = max(int(request.args.get("page", 1)), 1)
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        page, limit = 1, 50
    skip = (page - 1) * limit
    total = orders_col.count_documents({})
    cursor = (orders_col.find({}).sort("placed_at", -1)
             .skip(skip).limit(limit))
    return jsonify({"success": True, "data": serialize_list(cursor),
                    "pagination": {"page": page, "limit": limit,
                                   "total": total,
                                   "pages": (total + limit - 1) // limit}})


# ─────────────────────────────────────────────────────────────────
# ROUTE: SINGLE ORDER  (GET /api/orders/<id>)
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("/<order_id>", methods=["GET"])
def get_order(order_id):
    """Return one order. A student may only see their own; staff/admin
    may see any."""
    oid, err = parse_object_id(order_id)
    if err:
        return jsonify({"success": False, "error": err}), 400
    order = orders_col.find_one({"_id": oid})
    if not order:
        return jsonify({"success": False, "error": "Order not found."}), 404

    user = current_user()
    if not user:
        return jsonify({"success": False, "error": "Login required."}), 401
    if (user["role"] == "student"
            and str(order["student_id"]) != user["user_id"]):
        return jsonify({"success": False, "error": "Not your order."}), 403
    return jsonify({"success": True, "data": serialize_doc(order)})


# ─────────────────────────────────────────────────────────────────
# ROUTE: TRACK BY TOKEN  (GET /api/orders/token/<number>)
# ─────────────────────────────────────────────────────────────────
# plan.md: students track their order by token number without needing
# to log in (great for a shared canteen display screen).
@orders_bp.route("/token/<int:token_number>", methods=["GET"])
def track_by_token(token_number):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    order = orders_col.find_one({"token_number": token_number,
                                 "token_date": today})
    if not order:
        return jsonify({"success": False,
                        "error": f"No order #{token_number} today."}), 404
    # How many orders are ahead of this one in the queue?
    ahead = orders_col.count_documents({
        "token_date": today,
        "token_number": {"$lt": token_number},
        "status": {"$in": ("placed", "preparing")},
    })
    data = serialize_doc(order)
    data["orders_ahead"] = ahead
    return jsonify({"success": True, "data": data})


# ─────────────────────────────────────────────────────────────────
# ROUTE: UPDATE STATUS  (PATCH /api/orders/<id>/status)  — staff/admin
# ─────────────────────────────────────────────────────────────────
# The kitchen moves an order placed → preparing → ready → collected.
@orders_bp.route("/<order_id>/status", methods=["PATCH"])
@require_role("staff", "admin")
def update_status(order_id):
    oid, err = parse_object_id(order_id)
    if err:
        return jsonify({"success": False, "error": err}), 400

    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip()
    if new_status not in STATUSES:
        return jsonify({"success": False,
                        "error": f"Status must be one of {STATUSES}."}), 400

    now = datetime.now(timezone.utc)
    update = {"status": new_status}
    if new_status == "ready":
        update["ready_at"] = now
    elif new_status == "collected":
        update["collected_at"] = now

    updated = orders_col.find_one_and_update(
        {"_id": oid}, {"$set": update}, return_document=True)
    if not updated:
        return jsonify({"success": False, "error": "Order not found."}), 404

    token = updated["token_number"]
    payload = serialize_doc(updated)

    # Day 4/7: broadcast the status change in real time.
    socketio.emit("order_status_update",
                  {"token": token, "status": new_status, "order": payload},
                  room=f"order_{token}")
    socketio.emit("order_updated", payload, room="staff_dashboard")

    return jsonify({"success": True, "message": f"Order #{token} → {new_status}.",
                    "data": payload})


# ─────────────────────────────────────────────────────────────────
# ROUTE: SMART SUGGESTIONS  (GET /api/orders/suggestions)  — student
# ─────────────────────────────────────────────────────────────────
# plan.md add-on: "You usually order Masala Dosa on Tuesdays". Built
# from the student's own order history with an aggregation pipeline.
@orders_bp.route("/suggestions", methods=["GET"])
@require_role("student")
def suggestions():
    uid = ObjectId(request.current_user["user_id"])
    # Day 14 (course): $group to find this student's most-bought dishes.
    pipeline = [
        {"$match": {"student_id": uid}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.item_id",
                    "name": {"$first": "$items.name"},
                    "emoji": {"$first": "$items.emoji"},
                    "count": {"$sum": "$items.quantity"}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top = list(orders_col.aggregate(pipeline))
    # Make sure suggested items still exist & are available today.
    ids = [ObjectId(t["_id"]) for t in top if ObjectId.is_valid(t["_id"])]
    available = {str(i["_id"]): i for i in menu_col.find(
        {"_id": {"$in": ids}, "is_available": True})}
    picks = []
    for t in top:
        if t["_id"] in available:
            d = available[t["_id"]]
            picks.append({"item_id": str(d["_id"]), "name": d["name"],
                          "emoji": d.get("emoji", "🍽️"), "price": d["price"],
                          "times_ordered": t["count"]})
    return jsonify({"success": True, "data": picks})
