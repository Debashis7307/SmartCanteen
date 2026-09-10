"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Reviews Blueprint (reviews_bp)             ║
║                                                              ║
║   Students rate dishes 1–5 stars and leave a comment. We      ║
║   store the review in its own collection (Day 16 referencing) ║
║   AND keep a denormalised avg_rating on the menu item so the  ║
║   menu page never has to join.                                ║
║                                                              ║
║   Day 16 course: embedding vs referencing (reviews referenced)║
║   Day 8  course: $inc / $set to maintain the running average  ║
║   plan.md     : ratings power the analytics & "top dishes"   ║
╚══════════════════════════════════════════════════════════════╝
"""

from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, request, jsonify

from auth import require_role, current_user
from db import (reviews_col, menu_col,
                serialize_doc, serialize_list, parse_object_id)
from extensions import socketio

reviews_bp = Blueprint("reviews", __name__, url_prefix="/api/reviews")


# ─────────────────────────────────────────────────────────────────
# ROUTE: ADD REVIEW  (POST /api/reviews)  — student only
# ─────────────────────────────────────────────────────────────────
@reviews_bp.route("", methods=["POST"])
@reviews_bp.route("/", methods=["POST"])
@require_role("student")
def add_review():
    """Body: { item_id, rating (1-5), comment? }"""
    user = request.current_user
    data = request.get_json(silent=True) or {}

    oid, err = parse_object_id(data.get("item_id"))
    if err:
        return jsonify({"success": False, "error": err}), 400

    try:
        rating = int(data.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        return jsonify({"success": False,
                        "error": "Rating must be an integer 1–5."}), 400

    comment = (data.get("comment") or "").strip()[:500]

    # XSS defence (Day 5): we store the raw text and escape on render.
    review = {
        "item_id": oid,
        "student_id": ObjectId(user["user_id"]),
        "student_name": user["name"],
        "rating": rating,
        "comment": comment,
        "created_at": datetime.now(timezone.utc),
    }
    reviews_col.insert_one(review)

    # Recompute & cache the running average on the menu item so the
    # menu page stays a single fast read (denormalisation, Day 16).
    pipeline = [
        {"$match": {"item_id": oid}},
        {"$group": {"_id": "$item_id",
                    "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}},
    ]
    row = next(reviews_col.aggregate(pipeline), None)
    if row:
        menu_col.update_one({"_id": oid},
                            {"$set": {"avg_rating": round(row["avg"], 1),
                                      "total_ratings": row["n"]}})
    socketio.emit("review_added", {"item_id": str(oid)})
    return jsonify({"success": True, "message": "Thanks for your review!"}), 201


# ─────────────────────────────────────────────────────────────────
# ROUTE: LIST REVIEWS FOR A DISH  (GET /api/reviews/<item_id>)
# ─────────────────────────────────────────────────────────────────
@reviews_bp.route("/<item_id>", methods=["GET"])
def get_reviews(item_id):
    oid, err = parse_object_id(item_id)
    if err:
        return jsonify({"success": False, "error": err}), 400
    cursor = (reviews_col.find({"item_id": oid})
              .sort("created_at", -1).limit(50))
    return jsonify({"success": True, "data": serialize_list(cursor)})
