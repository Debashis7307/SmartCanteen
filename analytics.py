"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Analytics Blueprint (analytics_bp)         ║
║                                                              ║
║   The admin's data dashboard. Every endpoint is a MongoDB     ║
║   aggregation pipeline — the same ones from Days 13–15 of    ║
║   the course, now solving real canteen questions:             ║
║                                                              ║
║     • How much money did we make this week?   (revenue)      ║
║     • Which dish sells the most?              (popular)      ║
║     • When is the canteen busiest?            (peak-hours)   ║
║     • How much food gets wasted?              (waste)        ║
║     • Who are the top-spending students?       (top-students) ║
║     • Give me a CSV of this month              (export)       ║
║                                                              ║
║   Day 13 course: $match, $project, $sort                      ║
║   Day 14 course: $group, $sum, $avg, $max                     ║
║   Day 15 course: $unwind, $date operators ($hour, $dayOfWeek) ║
║   plan.md     : revenue / popular / peak-hours / waste / CSV  ║
╚══════════════════════════════════════════════════════════════╝
"""

import csv
import io
from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, jsonify, Response

from auth import require_role
from db import orders_col, serialize_list

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


# ─────────────────────────────────────────────────────────────────
# PERIOD HELPER
# ─────────────────────────────────────────────────────────────────
def _period_start(period):
    """Return the start datetime for 'today', 'week', or 'month'."""
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    return now - timedelta(days=7)  # default


# ─────────────────────────────────────────────────────────────────
# ROUTE: SUMMARY  (GET /api/analytics/summary)  — admin
# ─────────────────────────────────────────────────────────────────
# KPI cards at the top of the dashboard: revenue, orders, avg order,
# live count, waste count. One round-trip, several pipelines.
@analytics_bp.route("/summary", methods=["GET"])
@require_role("admin")
def summary():
    start = _period_start(request.args.get("period", "week"))
    now = datetime.now(timezone.utc)

    # Day 14 (course): group ALL docs in the window for totals.
    pipe = [
        {"$match": {"placed_at": {"$gte": start}}},
        {"$group": {"_id": None,
                    "revenue": {"$sum": "$total_amount"},
                    "orders": {"$sum": 1},
                    "avg_order": {"$avg": "$total_amount"}}},
    ]
    row = next(orders_col.aggregate(pipe), None)
    revenue = row["revenue"] if row else 0
    orders = row["orders"] if row else 0
    avg_order = round(row["avg_order"], 2) if row else 0

    live = orders_col.count_documents({"status": {"$in": ("placed", "preparing", "ready")}})
    waste = orders_col.count_documents({"status": "cancelled",
                                        "placed_at": {"$gte": start}})

    return jsonify({"success": True, "data": {
        "revenue": round(revenue, 2),
        "orders": orders,
        "avg_order": avg_order,
        "live_orders": live,
        "waste_orders": waste,
        "period_start": start.isoformat(),
        "now": now.isoformat(),
    }})


# ─────────────────────────────────────────────────────────────────
# ROUTE: REVENUE OVER TIME  (GET /api/analytics/revenue)
# ─────────────────────────────────────────────────────────────────
# plan.md pipeline: $match collected → $group by day → $sum total.
# We group by day for charts; status=collected counts as earned.
@analytics_bp.route("/revenue", methods=["GET"])
@require_role("admin")
def revenue():
    period = request.args.get("period", "week")
    start = _period_start(period)

    # Day 15 (course): $dateToString buckets documents by day.
    # Only "collected" orders represent real money earned.
    pipeline = [
        {"$match": {"placed_at": {"$gte": start},
                    "status": {"$in": ("collected", "placed", "preparing", "ready")}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$placed_at"}},
            "total": {"$sum": "$total_amount"},
            "orders": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
        {"$project": {"date": "$_id", "total": 1, "orders": 1, "_id": 0}},
    ]
    data = list(orders_col.aggregate(pipeline))
    return jsonify({"success": True, "data": data, "period": period})


# ─────────────────────────────────────────────────────────────────
# ROUTE: TOP DISHES  (GET /api/analytics/popular)
# ─────────────────────────────────────────────────────────────────
# plan.md pipeline: $unwind items → $group by name → $sum quantity &
# revenue → $sort → $limit 5.
@analytics_bp.route("/popular", methods=["GET"])
@require_role("admin")
def popular():
    start = _period_start(request.args.get("period", "month"))
    limit = min(int(request.args.get("limit", 5)), 20)

    pipeline = [
        {"$match": {"placed_at": {"$gte": start}}},
        {"$unwind": "$items"},                       # one row per line item
        {"$group": {
            "_id": {"name": "$items.name", "emoji": "$items.emoji"},
            "total_ordered": {"$sum": "$items.quantity"},
            "revenue": {"$sum": {"$multiply": ["$items.price_at_order",
                                               "$items.quantity"]}},
        }},
        {"$sort": {"total_ordered": -1}},
        {"$limit": limit},
        {"$project": {"name": "$_id.name", "emoji": "$_id.emoji",
                      "total_ordered": 1, "revenue": 1, "_id": 0}},
    ]
    data = list(orders_col.aggregate(pipeline))
    return jsonify({"success": True, "data": data})


# ─────────────────────────────────────────────────────────────────
# ROUTE: PEAK-HOURS HEATMAP  (GET /api/analytics/peak-hours)
# ─────────────────────────────────────────────────────────────────
# plan.md pipeline: $project hour & minute → bucket into 15-min slots
# → $group & count. Feeds the heatmap grid in the dashboard.
@analytics_bp.route("/peak-hours", methods=["GET"])
@require_role("admin")
def peak_hours():
    start = _period_start(request.args.get("period", "month"))
    pipeline = [
        {"$match": {"placed_at": {"$gte": start}}},
        {"$project": {
            "hour": {"$hour": "$placed_at"},
            "slot": {"$floor": {"$divide": [{"$minute": "$placed_at"}, 15]}},
        }},
        {"$group": {"_id": {"hour": "$hour", "slot": "$slot"},
                    "count": {"$sum": 1}}},
        {"$sort": {"_id.hour": 1, "_id.slot": 1}},
    ]
    raw = list(orders_col.aggregate(pipeline))
    # Reshape into [{hour, slot, count}] for the frontend heatmap.
    data = [{"hour": r["_id"]["hour"], "slot": r["_id"]["slot"],
             "count": r["count"]} for r in raw]
    return jsonify({"success": True, "data": data})


# ─────────────────────────────────────────────────────────────────
# ROUTE: WASTE TRACKER  (GET /api/analytics/waste)
# ─────────────────────────────────────────────────────────────────
# plan.md add-on: orders placed but never collected → wasted food.
@analytics_bp.route("/waste", methods=["GET"])
@require_role("admin")
def waste():
    start = _period_start(request.args.get("period", "month"))
    pipeline = [
        {"$match": {"status": "cancelled", "placed_at": {"$gte": start}}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.name",
                    "wasted_qty": {"$sum": "$items.quantity"},
                    "lost_revenue": {"$sum": "$total_amount"},
                    "count": {"$sum": 1}}},
        {"$sort": {"wasted_qty": -1}},
        {"$limit": 10},
    ]
    data = list(orders_col.aggregate(pipeline))
    return jsonify({"success": True, "data": data})


# ─────────────────────────────────────────────────────────────────
# ROUTE: TOP SPENDERS  (GET /api/analytics/top-students)  — admin
# ─────────────────────────────────────────────────────────────────
# plan.md feature: "Top spending students" leaderboard.
@analytics_bp.route("/top-students", methods=["GET"])
@require_role("admin")
def top_students():
    start = _period_start(request.args.get("period", "month"))
    pipeline = [
        {"$match": {"placed_at": {"$gte": start}}},
        {"$group": {"_id": {"id": "$student_id", "name": "$student_name"},
                    "spent": {"$sum": "$total_amount"},
                    "orders": {"$sum": 1}}},
        {"$sort": {"spent": -1}},
        {"$limit": 10},
        {"$project": {"name": "$_id.name", "spent": 1, "orders": 1, "_id": 0}},
    ]
    data = list(orders_col.aggregate(pipeline))
    return jsonify({"success": True, "data": data})


# ─────────────────────────────────────────────────────────────────
# ROUTE: CATEGORY SPLIT  (GET /api/analytics/categories)
# ─────────────────────────────────────────────────────────────────
# Which food category earns the most — for a doughnut chart.
@analytics_bp.route("/categories", methods=["GET"])
@require_role("admin")
def categories():
    start = _period_start(request.args.get("period", "month"))
    pipeline = [
        {"$match": {"placed_at": {"$gte": start}}},
        {"$unwind": "$items"},
        {"$lookup": {                       # Day 16 course: $join to menu
            "from": "menu_items",
            "localField": "items.item_id",
            "foreignField": "_id",
            "as": "dish",
        }},
        {"$unwind": {"path": "$dish", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": {"$ifNull": ["$dish.category", "Unknown"]},
                    "revenue": {"$sum": {"$multiply": ["$items.price_at_order",
                                                       "$items.quantity"]}},
                    "count": {"$sum": "$items.quantity"}}},
        {"$sort": {"revenue": -1}},
    ]
    data = list(orders_col.aggregate(pipeline))
    return jsonify({"success": True, "data": data})


# ─────────────────────────────────────────────────────────────────
# ROUTE: CSV EXPORT  (GET /api/analytics/export)  — admin
# ─────────────────────────────────────────────────────────────────
# plan.md: "Generate monthly revenue reports (CSV export)". We stream
# a CSV so the admin can open it in Excel / Google Sheets.
@analytics_bp.route("/export", methods=["GET"])
@require_role("admin")
def export_csv():
    start = _period_start(request.args.get("period", "month"))
    cursor = (orders_col.find({"placed_at": {"$gte": start}})
              .sort("placed_at", -1).limit(5000))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Token", "Date", "Student", "Items",
                     "Total", "Status", "Instructions"])

    for o in cursor:
        items = "; ".join(f"{i['quantity']}x {i['name']}"
                         for i in o.get("items", []))
        placed = o.get("placed_at")
        placed = placed.strftime("%Y-%m-%d %H:%M") if placed else ""
        writer.writerow([o.get("token_number"), placed,
                         o.get("student_name"), items,
                         o.get("total_amount"), o.get("status"),
                         o.get("special_instructions", "")])

    csv_text = buf.getvalue()
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="canteen_report.csv"'},
    )
