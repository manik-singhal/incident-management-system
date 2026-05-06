import redis
import json
import time
import threading
import sqlite3

r = redis.Redis(host="redis", port=6379, decode_responses=True)

print("Worker started... waiting for signals")

debounce_store = {}
WINDOW = 10

lock = threading.Lock()

conn = sqlite3.connect("ims.db", check_same_thread=False)
cursor = conn.cursor()

def get_severity(component):
    if "DB" in component:
        return "P0"
    elif "API" in component or "MCP" in component:
        return "P1"
    elif "CACHE" in component or "QUEUE" in component:
        return "P2"
    else:
        return "P3"

def execute_with_retry(query, params):
    retries = 3

    for attempt in range(retries):
        try:
            cursor.execute(query, params)
            return
        except Exception as e:
            print(f"DB error: {e}, retrying...")

            time.sleep(1)

    print("FAILED after retries.")            

def check_debounce():
    while True:
        now = time.time()

        with lock:
            components = list(debounce_store.keys())

        for component in components:
            with lock:
                if component not in debounce_store:
                    continue
                    
                first_seen = debounce_store[component]["first_seen"]
                signals = debounce_store[component]["signals"]
                count = debounce_store[component]["count"]

            if now - first_seen >= WINDOW:
                severity = get_severity(component)
                execute_with_retry(
                    "INSERT INTO incidents (component_id, count, created_at, status, severity) VALUES (?,?,?,?,?)",
                    (component, count, now, "OPEN", severity)
                    )

                incident_id = cursor.lastrowid

                for sig in signals:
                    execute_with_retry(
                        "INSERT INTO signal_logs (incident_id, component_id, created_at) VALUES (?,?,?)", (incident_id, component, now)
                    )  
                conn.commit()

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

                print(f"INCIDENT STORED: {component} with {len(signals)} signals")    
                
                with lock:
                    if component in debounce_store:
                        del debounce_store[component]

        time.sleep(1)

threading.Thread(target=check_debounce, daemon=True).start()    

while True:
    _, data = r.brpop("signal_queue")
    signal = json.loads(data)

    component = signal.get("component_id")
    now = time.time()

    minute = int(now // 60)
    r.incr(f"signals_per_minute:{minute}")

    with lock:
        if component not in debounce_store:
            debounce_store[component] = {
                "count": 1,
                "first_seen": now,
                "signals": [signal]
            }
        else:
            debounce_store[component]["count"] += 1
            debounce_store[component]["signals"].append(signal)

    
    
