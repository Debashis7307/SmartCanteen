"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Authentication Blueprint (auth_bp)         ║
║                                                              ║
║   Securing the front door of the application.                ║
║                                                              ║
║   Day 5 theory — Authentication, JWT & Web Security:          ║
║     • bcrypt  → hash passwords (never store plain text!)     ║
║     • JWT     → stateless signed tokens, no server memory    ║
║     • RBAC    → role-based access control (student/staff/admin)║
║     • httpOnly cookie → stores JWT safe from XSS             ║
║     • NoSQL injection → validate input types before querying ║
║                                                              ║
║   Day 27 (course): .env secrets / DB auth (the OTHER kind)   ║
╚══════════════════════════════════════════════════════════════╝
"""

from datetime import datetime, timedelta, timezone
from functools import wraps
import time
from collections import defaultdict

import bcrypt
import jwt
from bson import ObjectId
from flask import Blueprint, request, jsonify, make_response

from config import Config
from db import users_col, serialize_doc
from extensions import socketio

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ─────────────────────────────────────────────────────────────────
# JWT HELPERS  (Day 5 theory)
# ─────────────────────────────────────────────────────────────────
def create_jwt(user):
    """Sign and return a JWT for an authenticated user.

    The token is NOT encrypted — anyone can decode the payload. It is
    only SIGNED: tampering with the payload breaks the signature, so
    the server will reject a forged `role`. Never put secrets inside!
    """
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": str(user["_id"]),
        "name": user["name"],
        "role": user["role"],
        "roll_number": user.get("roll_number", ""),
        # `exp` (expiry) is the single most important security claim.
        # Even if a token leaks, it stops working after this time.
        "exp": now + timedelta(hours=Config.JWT_EXPIRY_HOURS),
        "iat": now,
    }
    # HS256 = HMAC-SHA256, keyed by our SECRET_KEY.
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def decode_jwt(token):
    """Verify a JWT's signature & expiry, returning the payload.

    Returns None if the token is invalid, tampered, or expired.
    """
    try:
        return jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None  # token lived its life — user must log in again
    except jwt.InvalidTokenError:
        return None  # signature mismatch / malformed → reject silently


def current_user():
    """Return the decoded JWT payload for the current request, or None.

    Every protected route reads the JWT from the httpOnly cookie.
    """
    token = request.cookies.get(Config.JWT_COOKIE_NAME)
    if not token:
        return None
    return decode_jwt(token)


def require_role(*allowed_roles):
    """Decorator enforcing Role-Based Access Control (Day 5: RBAC).

    Usage:
        @auth_bp.route("/api/...")
        @require_role("admin")            # only admin
        @require_role("staff", "admin")   # staff OR admin

    It runs BEFORE the route:
      1. Pull the JWT from the httpOnly cookie.
      2. Verify the signature (tampering → 401).
      3. Check the role is permitted (wrong role → 403).
      4. Attach the payload to `request` for the route to use.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                # 401 = "who are you?" (no/invalid credentials)
                return jsonify({"success": False, "error": "Login required."}), 401
            if allowed_roles and user["role"] not in allowed_roles:
                # 403 = "I know who you are, but you may NOT do this."
                return jsonify({"success": False,
                                "error": "Access denied — insufficient role."}), 403
            # Stash the identity on the request so the route can read
            # request.current_user["user_id"] etc.
            request.current_user = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────
# RATE LIMITING — brute-force protection (Day 5 theory)
# ─────────────────────────────────────────────────────────────────
# In-memory, single-process limiter (fine for one gunicorn worker on the
# free tier). For multi-worker scale this would live in Redis.
_rate_buckets = defaultdict(list)

def rate_limit(max_calls, window_sec, key_fn=None):
    """Decorate a route to cap calls per key within a rolling window.

    key_fn(request) -> a string key (default: the client IP).
    Returns 429 when the limit is exceeded.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = (key_fn or (lambda r: r.remote_addr or "anon"))(request)
            now = time.time()
            bucket = _rate_buckets[key]
            _rate_buckets[key] = [t for t in bucket if t > now - window_sec]
            if len(_rate_buckets[key]) >= max_calls:
                resp = jsonify({"success": False,
                                "error": "Too many attempts. Please wait a minute."})
                resp.status_code = 429
                return resp
            _rate_buckets[key].append(now)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────
# INPUT VALIDATION — defends against NoSQL Injection (Day 5)
# ─────────────────────────────────────────────────────────────────
# If we passed raw JSON straight into a Mongo query, an attacker could
# send {"email": {"$gt": ""}, "password": {"$gt": ""}} and bypass the
# login password check entirely! We force every field to be a plain
# string, which strips any $-operator objects.
def _require_str(value, field):
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


# ─────────────────────────────────────────────────────────────────
# ROUTE: REGISTER  (POST /api/auth/register)
# ─────────────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
@rate_limit(20, 60)
def register():
    """Create a new user account.

    Body: { name, email, password, roll_number?, role? }
    The role is chosen at sign-up (student | staff | admin) so a demo
    user can pick which dashboard they want to explore. Defaults to
    student when omitted.
    """
    data = request.get_json(silent=True) or {}

    # --- Validate & sanitize every field (NoSQL-injection safe) ---
    name = _require_str(data.get("name"), "name")
    email = _require_str(data.get("email"), "email")
    password = _require_str(data.get("password"), "password")
    if not (name and email and password):
        return jsonify({"success": False,
                        "error": "name, email, and password are required."}), 400
    if len(password) < 6:
        return jsonify({"success": False,
                        "error": "Password must be at least 6 characters."}), 400

    email = email.lower()
    roll_number = _require_str(data.get("roll_number", ""), "roll_number") or ""

    # Role chosen at sign-up. Coerce to a safe string (NoSQL-injection
    # defence) and validate against the allowed set.
    role = _require_str(data.get("role", "student"), "role") or "student"
    if role not in ("student", "staff", "admin"):
        return jsonify({"success": False,
                        "error": "Role must be student, staff, or admin."}), 400

    # --- Uniqueness check (the unique index is the real backstop) ---
    if users_col.find_one({"email": email}):
        return jsonify({"success": False,
                        "error": "An account with this email already exists."}), 409

    # --- Day 5: bcrypt hashing ---
    # bcrypt.gensalt() generates a random salt and embeds a cost factor.
    # The salt + cost travel INSIDE the hash string, so we never store
    # them separately. `password` must be bytes.
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    user_doc = {
        "name": name,
        "email": email,
        "password_hash": password_hash.decode("utf-8"),  # store as string
        "role": role,              # chosen at sign-up (student/staff/admin)
        "roll_number": roll_number,
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
    }
    result = users_col.insert_one(user_doc)

    # Issue a token so the student is logged in immediately.
    user_doc["_id"] = result.inserted_id
    token = create_jwt(user_doc)
    resp = jsonify({"success": True, "message": "Account created! Welcome aboard.",
                    "data": {"user": serialize_doc(user_doc)}})
    # httpOnly cookie → JS can't read it (XSS defence). SameSite=Lax
    # mitigates CSRF. (Day 5: CSRF / cookie security trade-offs.)
    resp.set_cookie(Config.JWT_COOKIE_NAME, token,
                    httponly=True, samesite="Lax", max_age=Config.JWT_EXPIRY_HOURS * 3600,
                    path="/")
    return resp, 201


# ─────────────────────────────────────────────────────────────────
# ROUTE: LOGIN  (POST /api/auth/login)
# ─────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
@rate_limit(10, 60)
def login():
    """Authenticate a user and issue a JWT cookie.

    Body: { email, password }
    """
    data = request.get_json(silent=True) or {}
    email = _require_str(data.get("email"), "email")
    password = _require_str(data.get("password"), "password")
    if not (email and password):
        return jsonify({"success": False,
                        "error": "email and password are required."}), 400

    email = email.lower()

    # NOTE: we always respond with the SAME generic error whether the
    # email or the password was wrong. Telling an attacker "email not
    # found" vs "wrong password" leaks which emails are registered.
    user = users_col.find_one({"email": email})
    if not user or not bcrypt.checkpw(password.encode("utf-8"),
                                     user["password_hash"].encode("utf-8")):
        return jsonify({"success": False,
                        "error": "Invalid email or password."}), 401

    # Record last login (Day 8 course: $set partial update).
    users_col.update_one({"_id": user["_id"]},
                         {"$set": {"last_login": datetime.now(timezone.utc)}})

    token = create_jwt(user)
    resp = jsonify({"success": True, "message": f"Welcome back, {user['name']}!",
                    "data": {"user": serialize_doc(user)}})
    resp.set_cookie(Config.JWT_COOKIE_NAME, token,
                    httponly=True, samesite="Lax", max_age=Config.JWT_EXPIRY_HOURS * 3600,
                    path="/")
    return resp


# ─────────────────────────────────────────────────────────────────
# ROUTE: LOGOUT  (POST /api/auth/logout)
# ─────────────────────────────────────────────────────────────────
@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Clear the auth cookie. (JWT is stateless, so the server "forgets"
    the user instantly — no session row to delete.)"""
    resp = jsonify({"success": True, "message": "Logged out. See you at the canteen!"})
    resp.delete_cookie(Config.JWT_COOKIE_NAME, path="/")
    return resp


# ─────────────────────────────────────────────────────────────────
# ROUTE: ME  (GET /api/auth/me)  — "who am I right now?"
# ─────────────────────────────────────────────────────────────────
@auth_bp.route("/me", methods=["GET"])
def me():
    """Return the currently logged-in user's profile (or 401)."""
    user = current_user()
    if not user:
        return jsonify({"success": False, "error": "Not logged in."}), 401
    # Look up fresh data so role/name changes (if an admin demoted them)
    # are reflected without re-issuing the token.
    doc = users_col.find_one({"_id": ObjectId(user["user_id"])})
    return jsonify({"success": True, "data": {"user": serialize_doc(doc),
                                               "token_claims": user}})
