import sqlite3

conn = sqlite3.connect("ims.db")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT,
    count INTEGER,
    created_at REAL,
    status TEXT DEFAULT "OPEN",
    rca TEXT,
    rca_submitted_at REAL,
    resolved_at REAL,
    severity TEXT
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS signal_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER,
        component_id TEXT,
        created_at REAL
    )
""")

conn.commit()
conn.close()

print("DB setup done")