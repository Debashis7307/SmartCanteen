# ════════════════════════════════════════════════════════════════
# SmartCanteen — Dockerfile  (Day 9 theory: containers & deployment)
# ════════════════════════════════════════════════════════════════
# WHY Docker? "It works on my machine!" → "It works EVERYWHERE."
# This file bundles the app + its exact Python + libraries into a
# portable image that runs identically on any OS.
#
# Build:  docker build -t smartcanteen .
# Run:    docker run -p 5000:5000 -e MONGO_URI=mongodb://host.docker.internal:27017 -e SECRET_KEY=changeme smartcanteen
# ════════════════════════════════════════════════════════════════

# Start from a lightweight Python image (Day 9: slim base = smaller image)
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy dependencies FIRST (cache optimization: if code changes but
# requirements don't, Docker reuses the cached pip install layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Tell Flask which port to listen on (Day 2: 0.0.0.0 = all interfaces)
ENV PORT=5000
ENV HOST=0.0.0.0

# Expose the port to the host
EXPOSE 5000

# Day 9: Gunicorn is the production WSGI server. It spawns multiple
# OS worker processes (Day 3 theory) to handle concurrent students.
# eventlet provides the async backend SocketIO needs.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--worker-class", "eventlet", "app:app"]
