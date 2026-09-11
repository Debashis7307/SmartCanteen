"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — College Canteen Pre-Order System            ║
║   Main Application Entry Point                                ║
║                                                              ║
║   The final capstone of the MongoDB + Python course.          ║
║   Wires together every blueprint, the real-time engine, and   ║
║   serves the frontend.                                        ║
║                                                              ║
║   Day 2  theory: 0.0.0.0 binding so the LAN can reach us      ║
║   Day 3  theory: gunicorn spawns OS workers in production    ║
║   Day 4  theory: CORS + WebSocket handshake                   ║
║   Day 5  theory: secret-key signs JWTs                        ║
║   Day 7  theory: background daemon thread for change streams  ║
║   Day 9  theory: gunicorn app:app on Render; `python app.py`  ║
║                 for local dev                                 ║
║                                                              ║
║   HOW TO RUN:                                                 ║
║     1. pip install -r requirements.txt                        ║
║     2. cp .env.example .env  (and edit if needed)             ║
╚══════════════════════════════════════════════════════════════╝
"""

# CRITICAL: eventlet.monkey_patch() MUST be called before any other
# import that touches sockets (pymongo, Flask, etc.). Without this,
# pymongo's SSL connection to MongoDB Atlas breaks because eventlet's
# green sockets don't match the regular SSL sockets pymongo cached.
try:
    import eventlet
    eventlet.monkey_patch()
except ImportError:
    pass

from flask import Flask, render_template, jsonify, send_from_directory, request

from config import Config
from db import create_indexes
from extensions import socketio

# Blueprints (each module owns its own URL prefix).
from auth import auth_bp
from menu import menu_bp
from orders import orders_bp
from reviews import reviews_bp
from analytics import analytics_bp
from realtime import start_change_stream_watcher


# ─────────────────────────────────────────────────────────────────
# FLASK APP FACTORY
# ─────────────────────────────────────────────────────────────────
def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    # Day 4 theory: CORS — allow the configured origins to call the API.
    try:
        from flask_cors import CORS
        CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}},
             supports_credentials=True)
    except ImportError:
        pass  # flask-cors optional; same-origin pages work without it

    # Register every REST blueprint.
    app.register_blueprint(auth_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(analytics_bp)

    # Bind SocketIO to this Flask app (Day 4/7). Same tightened CORS as
    # the REST API — never "*" in production.
    socketio.init_app(app, cors_allowed_origins=Config.CORS_ORIGINS)

    # Create DB indexes once at startup (idempotent).
    create_indexes()

    # ── Page routes (server-rendered HTML shells + client JS) ─────
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/menu")
    def menu_page():
        return render_template("menu.html")

    @app.route("/track")
    def track_page():
        return render_template("track.html")

    @app.route("/my-orders")
    def my_orders_page():
        return render_template("my_orders.html")

    @app.route("/staff")
    def staff_page():
        return render_template("staff.html")

    @app.route("/admin")
    def admin_page():
        return render_template("admin.html")

    @app.route("/login")
    def login_page():
        return render_template("login.html")

    @app.route("/register")
    def register_page():
        return render_template("register.html")

    @app.route("/api-info")
    def api_info():
        return jsonify({
            "name": "SmartCanteen API",
            "version": "1.0",
            "endpoints": [
                "POST /api/auth/register | /login | /logout | GET /me",
                "GET  /api/menu | /api/menu/<id> | PATCH /api/menu/<id>/availability",
                "POST /api/orders | GET /api/orders/my | /live | PATCH /api/orders/<id>/status",
                "GET  /api/analytics/summary | /revenue | /popular | /peak-hours | /export",
            ],
        })

    # ── Health check (used by Render / uptime monitors) ────────────
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "smartcanteen"}), 200

    # ── Error handlers: JSON for API routes, friendly pages otherwise ──
    @app.errorhandler(404)
    def not_found(err):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Endpoint not found."}), 404
        return render_template("error.html", code=404,
                               message="This page wandered off to the canteen."), 404

    @app.errorhandler(500)
    def server_error(err):
        return jsonify({"success": False,
                        "error": "Something broke in the kitchen. We're on it."}), 500

    return app


# ─────────────────────────────────────────────────────────────────
# MODULE-LEVEL APP (used by `gunicorn app:app` in production — Day 9)
# ─────────────────────────────────────────────────────────────────
app = create_app()

# Start the real-time change-stream watcher (Day 7 background thread).
start_change_stream_watcher()


# ─────────────────────────────────────────────────────────────────
# LOCAL DEV ENTRY POINT  (Day 2: 0.0.0.0 + port; Day 9: gunicorn prod)
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Windows console defaults to cp1252 which can't print emojis — force UTF-8.
    import sys as _sys
    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8")
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║        🍔 SmartCanteen — STARTING UP...                       ║
╠══════════════════════════════════════════════════════════════╣
║  ✅ Flask app created. Blueprints registered.                ║
║  ✅ SocketIO bound (WebSockets ready — Day 4 & 7).            ║
║  ✅ MongoDB indexes created (Day 12 & 26).                   ║
║                                                              ║
║  🌐 Open:    http://localhost:{Config.PORT}                   ║
║  📡 LAN URL: http://<your-laptop-ip>:{Config.PORT}  (0.0.0.0) ║
║                                                              ║
║  👤 Demo logins (run `python seed.py` first):                ║
║     student : aarav@college.edu / student123                 ║
║     staff   : staff@college.edu / staff123                    ║
║     admin   : admin@college.edu / admin123                   ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)
    # Day 2 theory: host='0.0.0.0' lets classmates on the same WiFi
    # reach the app via your laptop's local IP. use_reloader=False so
    # the change-stream thread isn't started twice in debug mode.
    socketio.run(app, host=Config.HOST, port=Config.PORT,
                  debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
