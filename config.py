"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Central Configuration                       ║
║                                                              ║
║   All tunable settings live here and read from the OS        ║
║   environment (so the same code runs locally AND on Render).  ║
║                                                              ║
║   Day 2 theory: 0.0.0.0 binding, ports, HTTP                 ║
║   Day 3 theory: Environment variables & the .env convention  ║
║   Day 5 theory: SECRET_KEY signs our JWTs                    ║
║   Day 6 theory: Cache TTLs & scaling knobs                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import os

try:
    # python-dotenv loads values from a local .env file into os.environ.
    # If the file is missing (e.g. on Render, where vars come from the
    # dashboard) this just silently does nothing — safe to call.
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    """Application configuration, sourced from environment variables.

    WHY a class?  It groups every setting in one place and gives us a
    clean type (Config.MONGO_URI) instead of os.environ.get(...) calls
    scattered across every file.
    """

    # ── Database ─────────────────────────────────────────────────
    # Day 4 (course): MongoClient connection string.
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "smart_canteen")

    # ── Security ─────────────────────────────────────────────────
    # Day 5 theory: this secret signs every JWT. Keep it long & random.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-production-secret")

    # Fail fast: a default secret in production would let anyone forge JWTs.
    if (os.environ.get("FLASK_ENV") == "production"
            and SECRET_KEY == "dev-only-not-for-production-secret"):
        raise RuntimeError(
            "SECRET_KEY is still the default! Set a long random value "
            "(e.g. `python -c \"import secrets; print(secrets.token_hex(32))\"`) "
            "in the environment before running in production."
        )

    # Day 5 theory: JWT expiry. Short-lived access tokens limit the
    # damage if a token is ever stolen.
    JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "12"))

    # Name of the httpOnly cookie that carries our JWT (Day 5 + Day 8).
    # httpOnly means JavaScript cannot read it → defends against XSS.
    JWT_COOKIE_NAME = "sc_token"

    # ── Networking ───────────────────────────────────────────────
    # Day 2 theory: 0.0.0.0 = "listen on every network interface"
    # so other devices on the same WiFi can reach the app.
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))

    # Day 4 theory: CORS — which origins the browser may call us from.
    CORS_ORIGINS = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:5000,https://smartcanteen.onrender.com",
        ).split(",")
        if o.strip()
    ]

    # ── Caching knobs (Day 6 theory) ─────────────────────────────
    # The menu changes rarely → perfect cache candidate. We cache it
    # in-memory for this many seconds to mimic a Redis TTL. On a real
    # scaled deployment this key would live in Redis (see Day 6 notes).
    MENU_CACHE_TTL = int(os.environ.get("MENU_CACHE_TTL", "30"))

    # ── Real-time ────────────────────────────────────────────────
    # Day 7 theory: MongoDB Change Streams REQUIRE a replica set.
    # When running a standalone mongod (common in dev) we cannot open a
    # change stream, so this flag lets us gracefully fall back to a
    # SocketIO emit-after-each-API-write strategy instead of crashing.
    CHANGE_STREAMS_ENABLED = os.environ.get(
        "CHANGE_STREAMS_ENABLED", "true"
    ).lower() == "true"
