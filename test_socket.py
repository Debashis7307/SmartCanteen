import socketio
import requests
import time
import sys

sio = socketio.Client()

@sio.event
def connect():
    print("Connected to server!")
    sio.emit("join_staff")

@sio.on("new_order")
def on_new_order(data):
    print(f"RECEIVED NEW_ORDER: {data}")
    # We exit successfully!
    sys.exit(0)

print("Connecting...")
try:
    sio.connect("http://localhost:5000")
except Exception as e:
    print(f"Connect failed: {e}")
    sys.exit(1)

time.sleep(1)

sess = requests.Session()
login_res = sess.post("http://localhost:5000/api/auth/login", json={"email": "aarav@college.edu", "password": "student123"})
print(f"Login: {login_res.status_code}")

menu_res = sess.get("http://localhost:5000/api/menu")
menu_items = menu_res.json().get("data", [])
valid_item = next(item for item in menu_items if item.get("is_available", True))
print(f"Using item: {valid_item['_id']}")

print("Placing order...")
order_res = sess.post("http://localhost:5000/api/orders", json={
    "items": [{"item_id": valid_item['_id'], "quantity": 1}],
    "special_instructions": "Test realtime"
})
print(f"Order: {order_res.status_code} {order_res.text}")

time.sleep(3)
print("Timeout: did not receive event")
sys.exit(1)
