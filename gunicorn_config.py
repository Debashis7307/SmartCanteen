"""
SmartCanteen — Gunicorn Configuration
─────────────────────────────────────────────────────────────────────
eventlet.monkey_patch() MUST run before the app module is imported.
Gunicorn loads this config file BEFORE it imports `app:app`, so calling
monkey_patch here guarantees every socket/lock/thread is greened before
pymongo, Flask, or any other module touches them. This silences the
"RLock(s) were not greened" warning and prevents potential deadlocks.
"""
import os
import eventlet

eventlet.monkey_patch()

# ── Gunicorn settings ──────────────────────────────────────────────
worker_class = "eventlet"
workers = 1
timeout = 120
bind = "0.0.0.0:{}".format(os.environ.get("PORT", "5000"))
accesslog = "-"
