from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis
import json
import sqlite3
import time
import threading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_STATUSES = {"OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"}

VALID_TRANSITIONS = {
    "OPEN": ["INVESTIGATING"],
    "INVESTIGATING": ["RESOLVED"],
    "RESOLVED": ["CLOSED"],
    "CLOSED": []
}

rate_limit_store = {}
RATE_LIMIT = 5
WINDOW = 10

signal_count = 0
start_time = time.time()

r = redis.Redis(host="redis", port=6379, decode_responses=True)

conn = sqlite3.connect("ims.db", check_same_thread=False)

def refresh_cache():
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC")
    rows = cursor.fetchall()

    incidents = []

    for row in rows:
        created_at = row[3]
        rca_submitted_at = row[6]

        mttr = None
        if rca_submitted_at is not None:
            mttr = rca_submitted_at - created_at

        incidents.append({
            "id": row[0],
            "component_id": row[1],
            "count": row[2],
            "created_at": created_at,
            "status": row[4],
            "rca": row[5],
            "rca_submitted_at": row[6],
            "resolved_at": row[7],
            "mttr": mttr,
            "severity": row[8]
        })

    r.set("incidents_cache", json.dumps(incidents))

@app.get("/")
def home():
  return {"status": "IMS Running🚀"}

@app.post("/ingest")
async def ingest(signal: dict):
  
  client_id = "global"
  now = time.time()
  if client_id not in rate_limit_store:
    rate_limit_store[client_id] = []

  rate_limit_store[client_id] = [
    t for t in rate_limit_store[client_id] 
    if now - t < WINDOW
  ]  

  if len(rate_limit_store[client_id]) >= RATE_LIMIT:
    return {"error": "Rate limit exceeded"}

  global signal_count
  signal_count +=1  

  rate_limit_store[client_id].append(now)

  r.lpush("signal_queue", json.dumps(signal))
  return {"status": "queued"}   

@app.get("/incidents")
def get_incidents():

  cached = r.get("incidents_cache")

  if cached:
    return json.loads(cached)

  cursor = conn.cursor()
  cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC")
  rows = cursor.fetchall()  

  incidents = []

  for row in rows:
    created_at = row[3]
    rca_submitted_at = row[6]
    resolved_at = row[7]

    mttr = None

    if rca_submitted_at is not None:
      mttr = rca_submitted_at - created_at

    incidents.append(
      {
        "id": row[0],
        "component_id": row[1],
        "count": row[2],
        "created_at": created_at,
        "status": row[4],
        "rca": row[5],
        "rca_submitted_at": rca_submitted_at,
        "resolved_at": resolved_at,
        "mttr": mttr,
        "severity": row[8]
      }
    )
  return incidents  

@app.post("/incidents/{incident_id}/status")
def update_status(incident_id: int, status: str):

  status = status.upper()

  if status not in VALID_STATUSES:
    return {"error": "Invalid status"}

  cursor = conn.cursor()
  cursor.execute(
    "SELECT * FROM incidents WHERE id = ?", (incident_id,)
  )
  row = cursor.fetchone()

  if not row:
    return {"error": "Incident not found"}

  current_status = row[4]
  rca = row[5]

  if status not in VALID_TRANSITIONS[current_status]:
    return {
      "error": f"Invalid transition from {current_status} to {status}"
    }  

  if status == "CLOSED" and (not rca or rca.strip() == ""):
    return {"error": "Cannot close incident without RCA"}

  if status == "CLOSED":
    now = time.time()
    cursor.execute(
      "UPDATE incidents SET status = ?, resolved_at = ? WHERE id = ?",
      (status, now, incident_id)
    )  
  else:
    cursor.execute(
      "UPDATE incidents SET status = ? WHERE id = ?",
      (status, incident_id)
    )  
  conn.commit()

  refresh_cache()

  return {"message": f"incident {incident_id} updated to {status}"}

@app.post("/incidents/{incident_id}/rca")
def add_rca(incident_id: int, rca: str):

  if not rca or rca.strip() == "":
    return {"error": "RCA cannot be empty"}

  cursor = conn.cursor()
  now = time.time()

  cursor.execute(
    "SELECT * FROM incidents WHERE id = ?", (incident_id,)
  )  

  row = cursor.fetchone()

  if not row:
    return {"error": "Incident not found"}

  current_status = row[4]

  if current_status == "CLOSED":
    return {"error": "Cannot modify RCA after incident is closed"}  

  cursor.execute(
    "UPDATE incidents SET rca = ?, rca_submitted_at = ? WHERE id = ?", (rca, now, incident_id)
  )
  conn.commit()

  refresh_cache()

  return {"message": f"RCA added to incident {incident_id}"}

@app.get("/health")
def health():
  return {
    "status": "healthy"
  }  

@app.get("/metrics")
def metrics():

  uptime = time.time() - start_time

  signals_per_second = 0

  if uptime > 0:
    signals_per_second = signal_count / uptime

  return {
    "total_signals": signal_count,
    "uptime_seconds": uptime,
    "signals_per_second": signals_per_second
  }   

def print_metrics():

  while True:
    uptime = time.time() - start_time

    signal_per_second = 0

    if uptime > 0:
      signal_per_second = signal_count / uptime

    print(f"[Metrics] signals/sec: {signal_per_second:.2f}")

    time.sleep(5)  

threading.Thread(target = print_metrics, daemon = True).start() 

@app.get("/metrics/signals")
def get_signal_metrics():
  now = int(time.time() // 60)

  data = []

  for i in range(10):
    minute = now - i
    count = r.get(f"signals_per_minute:{minute}")

    data.append({
      "minute": minute,
      "count": int(count) if count else 0
      })

  return data  

@app.get("/incidents/{incident_id}/signals")
def get_signals(incident_id: int):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM signal_logs WHERE incident_id = ?",
        (incident_id,)
    )
    rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "component_id": row[2],
            "created_at": row[3]
        }
        for row in rows
    ]  