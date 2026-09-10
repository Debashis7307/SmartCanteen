# 🍔 SmartCanteen — College Canteen Pre-Order System

> **The capstone project of the MongoDB + Python course.**
> A real-world full-stack web app that solves a daily pain point for every college student — long queues at the canteen during short breaks.

Built over 10 days as the final project, putting together **30 days of MongoDB + Python** learning into one production-ready product.

---

## 🎯 The Problem It Solves

Every college student knows this: the break is 15 minutes, the canteen queue is 30 minutes long. Students miss food. Canteen staff are overwhelmed. Food gets wasted because no one knows demand.

**SmartCanteen fixes all of this.** Pre-order from class → get a token → walk up when the food is ready → skip the queue.

---

## ✨ Features

### For Students
- 🍽️ Browse live digital menu with photos, prices, availability & ratings
- 🛒 Add to cart, place pre-order, get a token number
- 🎯 **Live order tracking** — Placed → Preparing → Ready → Collected (real-time, no refresh)
- 📦 Personal order history with spending analytics
- ⭐ Rate dishes (1–5 stars + review text)
- ↻ One-tap reorder of past meals
- 🧠 Smart suggestions ("Your usuals" based on order history)

### For Canteen Staff
- 👨‍🍳 **Live kitchen dashboard** — new orders appear instantly via WebSocket
- ✅ Mark orders: Preparing → Ready → Collected with one tap
- 🚫 Toggle items Out of Stock instantly (auto-greys out for every student in real-time)
- 🎯 Update order status from the tracking screen too
- 🔔 Audio alert + visual flash on new orders

### For Admin (Canteen Manager / HOD)
- 📊 **Analytics dashboard** with animated, eye-catching charts:
  - 💰 Revenue over time (bar + trend line, gradient bars)
  - 🏆 Top 5 most-ordered dishes (ranked table + horizontal bars)
  - ⏰ **Peak hours heatmap** — 15-minute windows, color-graded from dark→yellow, hover tooltips, pulsing hot zones
  - 🥧 Revenue by category (animated doughnut with center total)
  - 🗑️ Waste tracker (cancelled/uncollected orders → lost revenue)
  - 👤 Top spending students leaderboard
  - ⬇️ CSV export of all orders
- ⚡ Menu management with stock toggles

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Database | MongoDB (localhost:27017) | Flexible schema, powerful aggregation |
| Backend | Python + Flask | REST API, blueprints, role-based access |
| Real-time | Flask-SocketIO + Change Streams | Live order & stock updates |
| Frontend | HTML + CSS + Vanilla JS | No framework needed — fast & clean |
| Charts | Chart.js (CDN) | Animated analytics dashboard |
| Auth | bcrypt + JWT (httpOnly cookie) | Secure, stateless, RBAC |
| Images | GridFS (pymongo) | Menu item photos in MongoDB |
| Deployment | Render + Gunicorn + Docker | Production-ready |

---

## 🚀 Run Locally

### Prerequisites
- Python 3.10+
- MongoDB running on `localhost:27017` (standalone or replica set)

### Steps

```bash
# 1. Clone / open the project
cd FinalProject_CanteenSystem/SmartCanteen

# 2. Create & activate a virtual environment
python -m venv venv
# Windows:  venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
copy .env.example .env       # Windows
cp .env.example .env         # Mac/Linux
# Edit .env if your MongoDB isn't at localhost:27017

# 5. Seed the database (loads 28 dishes, 18 users, ~140 orders, reviews)
python seed.py

# 6. Start the app
python app.py

# 7. Open http://localhost:5000 in your browser
```

### Demo Logins (after seeding)

| Role | Email | Password |
|------|-------|----------|
| 👨‍🎓 Student | `aarav@college.edu` | `student123` |
| 👨‍🍳 Staff | `staff@college.edu` | `staff123` |
| 📊 Admin | `admin@college.edu` | `admin123` |

---

## 📁 Project Structure

```
SmartCanteen/
├── app.py                 # Flask app factory + page routes + entry point
├── config.py              # Environment-driven configuration
├── db.py                  # MongoDB connection, indexes, serializers
├── extensions.py          # Shared SocketIO instance
├── seed.py                # Loads demo menu, users, orders, reviews
├── requirements.txt
├── .env.example
├── .gitignore
│
├── auth.py                # Blueprint: register, login, logout, JWT, RBAC
├── menu.py                # Blueprint: menu CRUD, search, GridFS, stock toggle
├── orders.py              # Blueprint: place order, track, token, reorder
├── reviews.py             # Blueprint: ratings & reviews
├── analytics.py           # Blueprint: revenue, popular, peak-hours, waste, CSV
├── realtime.py            # Socket.IO rooms + Change Stream background thread
│
├── static/
│   ├── css/
│   │   ├── base.css        # Theme, navbar, buttons, cards, toasts
│   │   └── pages.css       # Menu, cart, track, staff, admin, heatmap styles
│   └── js/
│       ├── api.js         # Fetch wrapper (credentials, error handling)
│       ├── common.js      # Auth state, navbar, toasts, Socket.IO, helpers
│       ├── auth.js        # Login & register page logic
│       ├── menu.js        # Menu grid, cart, search, dish-of-the-day
│       ├── track.js       # Live order tracking + staff controls
│       ├── staff.js       # Kitchen dashboard + stock management
│       ├── admin.js       # Analytics charts + heatmap
│       ├── my_orders.js   # Order history + reorder
│       └── index.js       # Landing page
│
└── templates/
    ├── base.html          # Shared layout (nav, footer, CDN links)
    ├── index.html         # Landing page
    ├── login.html         # Login form + demo logins
    ├── register.html      # Student signup
    ├── menu.html          # Menu + cart drawer
    ├── track.html         # Live order tracking
    ├── my_orders.html     # Order history
    ├── staff.html         # Kitchen dashboard
    └── admin.html         # Analytics dashboard
```

---

## 🔌 API Routes

### Auth (`/api/auth`)
| Method | Route | Action | Access |
|--------|-------|--------|--------|
| POST | `/register` | Create account | Anyone |
| POST | `/login` | Login → JWT cookie | Anyone |
| POST | `/logout` | Clear cookie | Logged in |
| GET | `/me` | Current user profile | Logged in |

### Menu (`/api/menu`)
| Method | Route | Action | Access |
|--------|-------|--------|--------|
| GET | `` | List available dishes (cached) | Anyone |
| GET | `/<id>` | Single dish + reviews | Anyone |
| GET | `/categories/list` | Distinct categories | Anyone |
| GET | `/dish-of-the-day` | Daily special | Anyone |
| GET | `/<id>/image` | Serve dish photo | Anyone |
| POST | `` | Add dish | Admin |
| PUT | `/<id>` | Update dish | Admin |
| DELETE | `/<id>` | Remove dish | Admin |
| PATCH | `/<id>/availability` | Toggle stock (atomic) | Staff/Admin |
| POST | `/<id>/image` | Upload photo (GridFS) | Staff/Admin |

### Orders (`/api/orders`)
| Method | Route | Action | Access |
|--------|-------|--------|--------|
| POST | `` | Place order (atomic stock) | Student |
| GET | `/my` | My order history | Student |
| GET | `/live` | All live orders | Staff/Admin |
| GET | `/all` | All orders (paginated) | Admin |
| GET | `/<id>` | Single order | Owner/Staff/Admin |
| GET | `/token/<n>` | Track by token | Anyone |
| PATCH | `/<id>/status` | Update status | Staff/Admin |
| POST | `/reorder/<id>` | Rebuild cart from past order | Student |
| GET | `/suggestions` | "Your usuals" | Student |

### Reviews (`/api/reviews`)
| Method | Route | Action | Access |
|--------|-------|--------|--------|
| POST | `` | Add review + update avg rating | Student |
| GET | `/<item_id>` | Reviews for a dish | Anyone |

### Analytics (`/api/analytics`) — Admin only
| Method | Route | Action |
|--------|-------|--------|
| GET | `/summary` | KPI cards (revenue, orders, avg, live, waste) |
| GET | `/revenue?period=week` | Daily revenue for charts |
| GET | `/popular?limit=5` | Top dishes |
| GET | `/peak-hours?period=month` | 15-min slot heatmap data |
| GET | `/waste?period=month` | Cancelled/uncollected orders |
| GET | `/top-students?period=month` | Top spenders |
| GET | `/categories?period=week` | Revenue by category |
| GET | `/export?period=month` | CSV download |

---

## 🗄️ MongoDB Collections

| Collection | Purpose |
|-----------|---------|
| `users` | Auth, roles (student/staff/admin), roll numbers |
| `menu_items` | Dishes with price, stock, ratings, GridFS image ref |
| `orders` | Token, snapshot items, status lifecycle, timestamps |
| `reviews` | Per-dish ratings & comments |
| `daily_tokens` | Auto-resetting token counter (TTL index) |
| `fs.files` / `fs.chunks` | GridFS image storage |

---

## 🎓 Course Concepts Used (by teaching day)

| Teaching Day | Concept | Where in the code |
|-------------|---------|-------------------|
| Day 1 | Architecture overview | `app.py` blueprint wiring |
| Day 2 | 0.0.0.0 binding, TCP, ports | `app.py` `socketio.run(host='0.0.0.0')` |
| Day 3 | Atomic ops, race conditions, env vars | `orders.py` atomic stock, `config.py` |
| Day 4 | CORS, WebSockets, Socket.IO | `extensions.py`, `realtime.py`, `menu.py` |
| Day 5 | bcrypt, JWT, RBAC, NoSQL injection | `auth.py` — full auth blueprint |
| Day 6 | Caching, TTL indexes, CAP | `menu.py` cache, `db.py` TTL on tokens |
| Day 7 | Async, event loop, change streams, rooms | `realtime.py` background thread |
| Day 8 | Fetch, DOM, Promises, Chart.js | All `static/js/*.js` files |
| Day 9 | Git, GitHub, Render, Docker, Gunicorn | `Dockerfile`, `requirements.txt`, `.gitignore` |

Plus all 30 course days: `insert_one`, `find`, `update_one` `$set`, `delete`,
query operators, `sort/limit/skip`, indexes, text search, aggregation pipelines
(`$match`, `$group`, `$sum`, `$avg`, `$unwind`, `$lookup`, `$dateToString`,
`$hour`, `$floor`), GridFS, and more.

---

## 🐳 Docker (Day 9)

```bash
# Build the image
docker build -t smartcanteen .

# Run it (MongoDB must be reachable — use host network or Atlas)
docker run -p 5000:5000 -e MONGO_URI=mongodb://host.docker.internal:27017 -e SECRET_KEY=your-secret smartcanteen
```

---

## ☁️ Deploy to Render (Day 9)

1. Push this folder to a GitHub repo
2. On Render → New Web Service → connect the repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn --bind 0.0.0.0:$PORT --worker-class eventlet app:app`
5. Add environment variables: `MONGO_URI`, `MONGO_DB_NAME`, `SECRET_KEY`, `CORS_ORIGINS`
6. Deploy → get your public URL! 🎉

---

## 🔢 Key MongoDB Indexes

```python
users.create_index("email", unique=True)          # fast + unique login lookup
menu.create_index([("name", TEXT), ("description", TEXT)])  # full-text search
orders.create_index([("status", 1), ("placed_at", -1)])      # live orders compound
tokens.create_index("expires_at", expireAfterSeconds=0)       # TTL auto-reset
```

---

## 📊 Key Aggregation Pipelines

- **Revenue**: `$match` by date → `$group` by day → `$sum` total
- **Top dishes**: `$unwind` items → `$group` by name → `$sum` quantity → `$sort` → `$limit`
- **Peak hours**: `$project` hour + minute → `$floor` into 15-min slots → `$group` count
- **Waste**: `$match` cancelled → `$unwind` items → `$group` wasted qty + lost revenue

---

*Built during the MongoDB + Python Course — 10-Day Capstone Project.*
