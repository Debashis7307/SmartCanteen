"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Shared Extensions                           ║
║                                                              ║
║   The SocketIO object must be importable by BOTH app.py       ║
║   (which binds it to the Flask app) and realtime.py / the     ║
║   blueprints (which emit events). If we created it inside      ║
║   app.py we'd get a circular import. Defining it here first   ║
║   solves that — classic Flask extension pattern.              ║
║                                                              ║
║   Day 4 theory: WebSockets & Socket.IO                       ║
║   Day 7 theory: background thread emits to rooms             ║
╚══════════════════════════════════════════════════════════════╝
"""

from flask_socketio import SocketIO

from config import Config

# Eventlet is available on Render for production-grade async, and 
# locally it is patched in app.py.
# Day 4 theory: CORS origins must be tightened (never "*") so only
# our own frontend can open a WebSocket — otherwise any site can
# eavesdrop on live order data.
socketio = SocketIO(
    cors_allowed_origins=Config.CORS_ORIGINS,
    ping_timeout=60,                # keep long-lived connections healthy
    ping_interval=25,
)
