"""
╔══════════════════════════════════════════════════════════════╗
║   SmartCanteen — Real-Time Engine (realtime.py)             ║
║                                                              ║
║   Bridges MongoDB and the browser so updates appear WITHOUT  ║
║   anyone pressing refresh.                                   ║
║                                                              ║
║   Day 4 theory: WebSockets, Socket.IO, rooms, CORS           ║
║   Day 7 theory: event-driven arch, background thread, async, ║
║                 pub/sub — the DB publishes, the socket room   ║
║                 subscribes. Flask routes can't block forever, ║
║                 so a DAEMON thread holds the infinite watch.  ║
║                                                              ║
║   Day 22 (course): MongoDB Change Streams.                   ║
║   NOTE: Change Streams require a REPLICA SET. A standalone    ║
║   `mongod` cannot open one, so we gracefully fall back to     ║
║   emitting directly from each API route (already wired in     ║
║   orders.py / menu.py). The thread here is the "true" path    ║
║   used once MongoDB is a replica set or on Atlas.              ║
╚══════════════════════════════════════════════════════════════╝
"""

import threading
import logging

from flask_socketio import join_room, leave_room
from flask import request

from db import orders_col, menu_col
from db import serialize_doc
from extensions import socketio
from config import Config

log = logging.getLogger("smartcanteen.realtime")


# ─────────────────────────────────────────────────────────────────
# SOCKET.IO EVENT HANDLERS  (Day 4: client ↔ server events)
# ─────────────────────────────────────────────────────────────────
# A "room" is just a named group of connected sockets. We put each
# student into a room named after their token, and every staff member
# into a shared "staff_dashboard" room. Emitting to a room delivers
# the event to ONLY those sockets — private & efficient (Day 7).

@socketio.on("connect")
def handle_connect():
    """A new browser just opened a WebSocket connection."""
    log.info("⚡ socket connected: %s", request.sid)


@socketio.on("track_order")
def handle_track_order(data):
    """Student wants live updates for a specific token.

    Client sends: { token: 47 }  → we join room "order_47".
    Only that room receives status changes for token 47.
    """
    token = (data or {}).get("token")
    if token is None:
        return
    room = f"order_{token}"
    join_room(room)
    log.info("👤 joined room %s (sid=%s)", room, request.sid)


@socketio.on("join_staff")
def handle_join_staff(_data=None):
    """Staff member opens the kitchen dashboard → join the staff room."""
    join_room("staff_dashboard")
    log.info("👨‍🍳 joined staff_dashboard (sid=%s)", request.sid)


@socketio.on("leave_order")
def handle_leave_order(data):
    token = (data or {}).get("token")
    if token is not None:
        leave_room(f"order_{token}")


@socketio.on("disconnect")
def handle_disconnect():
    log.info("🔌 socket disconnected: %s", request.sid)


# ─────────────────────────────────────────────────────────────────
# MONGODB CHANGE STREAM WATCHER  (Day 7: background daemon thread)
# ─────────────────────────────────────────────────────────────────
# Flask request handlers must RETURN quickly — they cannot sit in an
# infinite loop. So we spawn ONE background thread at startup that
# holds the change stream open and forwards events to Socket.IO.
# `daemon=True` means the thread dies with the main process (clean
# shutdown — Day 3 signals / SIGINT).
def _watch_collection(col, room_fn, event_name):
    """Watch one collection forever, emitting changes to socket rooms.

    col       : the pymongo collection to watch
    room_fn   : callable(change_doc) -> room name (or None to skip)
    event_name: the socket event name clients listen for
    """
    # full_document='updateLookup' so UPDATE events include the new doc.
    pipeline = [{"$match": {"operationType": {"$in": ["insert", "update"]}}}]
    while True:
        try:
            with col.watch(pipeline, full_document="updateLookup") as stream:
                log.info("👁️  change stream open on %s", col.name)
                for change in stream:
                    doc = change.get("fullDocument")
                    if not doc:
                        continue
                    room = room_fn(doc)
                    if room is None:
                        continue
                    payload = serialize_doc(doc)
                    socketio.emit(event_name, payload, room=room)
        except Exception as exc:
            # Connection dropped / not a replica set. Wait and retry
            # rather than crashing the whole server. Day 7: resilient
            # event-driven systems must self-heal.
            log.warning("change stream on %s paused: %s", col.name, exc)
            import time
            time.sleep(3)


def _order_room(doc):
    """Each order lives in room order_<token> AND the staff room."""
    token = doc.get("token_number")
    if token is None:
        return None
    return f"order_{token}"


def start_change_stream_watcher():
    """Launch the background watcher threads (call once at startup)."""
    if not Config.CHANGE_STREAMS_ENABLED:
        log.info("ℹ️  change streams disabled by config — using "
                 "direct emit fallback from API routes.")
        return

    # Day 7: two watchers run concurrently as daemon threads.
    # Orders → students see status changes; menu → everyone sees stock.
    threading.Thread(
        target=_watch_collection,
        args=(orders_col, _order_room, "order_status_update"),
        daemon=True, name="orders-watcher",
    ).start()
    threading.Thread(
        target=_watch_collection,
        args=(menu_col, lambda d: "menu_live", "menu_changed"),
        daemon=True, name="menu-watcher",
    ).start()
