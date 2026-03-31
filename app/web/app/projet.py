"""
Smart Irrigation System — Flask Backend
Lit les données depuis un fichier JSON (data.json) au lieu de la simulation random.

STRUCTURE DU PROJET ATTENDUE :
  Smart_Irrigation_System/
    app/
      projet.py          <- CE FICHIER
    Data/
      data.json
    templates/
      index.html
    irrigation.db        <- créé automatiquement
"""

import sqlite3, json, os
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, g

# ─── CORRECTION 1 : Chemins absolus ──────────────────────────────────────────
_BASE     = os.path.dirname(os.path.abspath(__file__))
DB        = os.path.join(_BASE, "..", "irrigation.db")
JSON_FILE = os.path.join(_BASE, "..","Data" ,"data.json")

# ─── CORRECTION 2 : template_folder absolu ───────────────────────────────────
app = Flask (
    __name__,
template_folder=os.path.join(_BASE, "..", "..", "web", "templates"),
static_folder=os.path.join(_BASE, "..", "..", "web", "static")
)


app.secret_key = "irrigation-secret-2026"

# ─── Registre des capteurs ────────────────────────────────────────────────────
SENSOR_REGISTRY = {
    1: {"name": "Zone A - Nord",   "zone": "Nord",   "latitude": 31.62, "longitude": -8.01},
    2: {"name": "Zone B - Centre", "zone": "Centre", "latitude": 31.60, "longitude": -8.00},
    3: {"name": "Zone C - Sud",    "zone": "Sud",    "latitude": 31.58, "longitude": -8.02},
    4: {"name": "Zone D - Est",    "zone": "Est",    "latitude": 31.61, "longitude": -7.99},
}

# ─── Seuils d alerte ──────────────────────────────────────────────────────────
SEUIL_HUM_CRITICAL = 25.0
SEUIL_HUM_WARNING  = 35.0
SEUIL_TMP_CRITICAL = 40.0
SEUIL_TMP_WARNING  = 35.0

# ─── Base de données ──────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db:
        db.close()

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS sensors (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            zone      TEXT NOT NULL,
            latitude  REAL,
            longitude REAL,
            active    INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id   INTEGER NOT NULL,
            timestamp   TEXT NOT NULL,
            humidity    REAL NOT NULL,
            temperature REAL NOT NULL,
            FOREIGN KEY(sensor_id) REFERENCES sensors(id)
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id   INTEGER NOT NULL,
            timestamp   TEXT NOT NULL,
            type        TEXT NOT NULL,
            message     TEXT NOT NULL,
            severity    TEXT NOT NULL,
            resolved    INTEGER DEFAULT 0,
            FOREIGN KEY(sensor_id) REFERENCES sensors(id)
        );
        CREATE TABLE IF NOT EXISTS irrigation_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id    INTEGER NOT NULL,
            started_at   TEXT NOT NULL,
            ended_at     TEXT,
            duration_min INTEGER,
            trigger_type TEXT,
            FOREIGN KEY(sensor_id) REFERENCES sensors(id)
        );
        CREATE TABLE IF NOT EXISTS predictions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id   INTEGER NOT NULL,
            timestamp   TEXT NOT NULL,
            recommend   TEXT NOT NULL,
            confidence  REAL NOT NULL,
            hours_ahead INTEGER NOT NULL,
            FOREIGN KEY(sensor_id) REFERENCES sensors(id)
        );
    """)
    conn.commit()
    conn.close()

# ─── Utilitaires JSON ─────────────────────────────────────────────────────────

def normalize_entry(entry):
    timestamp = entry.get("timestamp")
    sensor_id = entry.get("sensor_id")
    humidity  = entry.get("soil_humidity_%")
    temp      = entry.get("temperature_C")

    if None in (timestamp, sensor_id, humidity, temp):
        return None

    try:
        sensor_id = int(sensor_id)
        humidity  = float(humidity)
        temp      = float(temp)
    except (ValueError, TypeError):
        return None

    reg         = SENSOR_REGISTRY.get(sensor_id, {})
    sensor_name = entry.get("sensor_name") or reg.get("name") or f"Capteur {sensor_id}"
    zone        = entry.get("zone")        or reg.get("zone") or f"Zone {sensor_id}"

    alert_type     = entry.get("alert_type")
    alert_severity = entry.get("alert_severity")

    if alert_type is None:
        if humidity < SEUIL_HUM_CRITICAL:
            alert_type, alert_severity = "low_humidity", "critical"
        elif humidity < SEUIL_HUM_WARNING:
            alert_type, alert_severity = "low_humidity", "warning"
        elif temp > SEUIL_TMP_CRITICAL:
            alert_type, alert_severity = "high_temp", "critical"
        elif temp > SEUIL_TMP_WARNING:
            alert_type, alert_severity = "high_temp", "warning"

    raw_irr    = entry.get("irrigation", False)
    irrigation = bool(raw_irr) if not isinstance(raw_irr, bool) else raw_irr
    if isinstance(raw_irr, int):
        irrigation = raw_irr == 1

    irr_duration = int(entry.get("irrigation_duration_min", 0) or 0)

    return {
        "timestamp"     : timestamp,
        "sensor_id"     : sensor_id,
        "sensor_name"   : sensor_name,
        "zone"          : zone,
        "humidity"      : round(humidity, 2),
        "temperature"   : round(temp, 2),
        "alert_type"    : alert_type,
        "alert_severity": alert_severity,
        "irrigation"    : irrigation,
        "irr_duration"  : irr_duration,
    }

def ai_prediction(humidity, temperature, hour):
    score  = max(0, (40 - humidity) * 2)
    score += max(0, (temperature - 30) * 1.5)
    score += 10 if 6  <= hour <= 10 else 0
    score += 5  if 17 <= hour <= 20 else 0

    if humidity < 25:
        return "Irriguer maintenant", min(0.95, score / 100), 0
    elif humidity < 40:
        return "Irriguer dans 2h",    min(0.88, score / 100), 2
    elif humidity < 55:
        return "Surveiller",          0.70,                   4
    else:
        return "Pas necessaire",      0.85,                   8

# ─── Chargement JSON -> base de données ───────────────────────────────────────

def ensure_sensor_exists(conn, sensor_id, sensor_name, zone):
    c = conn.cursor()
    c.execute("SELECT id FROM sensors WHERE id=?", (sensor_id,))
    if c.fetchone():
        return
    reg = SENSOR_REGISTRY.get(sensor_id, {})
    c.execute(
        "INSERT OR IGNORE INTO sensors(id, name, zone, latitude, longitude) VALUES(?,?,?,?,?)",
        (sensor_id, sensor_name, zone, reg.get("latitude"), reg.get("longitude"))
    )

def load_json_into_db():
    if not os.path.exists(JSON_FILE):
        print(f"[WARN] Fichier introuvable : {JSON_FILE}")
        return

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        try:
            raw_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[ERREUR] JSON invalide : {e}")
            return

    if not isinstance(raw_data, list):
        print("[ERREUR] Le JSON doit etre une liste [ {...}, {...} ]")
        return

    conn  = sqlite3.connect(DB)
    c     = conn.cursor()
    stats = {"total": 0, "inserted": 0, "skipped": 0,
             "invalid": 0, "alerts": 0, "irrigations": 0}

    for raw in raw_data:
        stats["total"] += 1
        entry = normalize_entry(raw)

        if entry is None:
            stats["invalid"] += 1
            print(f"[WARN] Entree ignoree : {raw}")
            continue

        c.execute(
            "SELECT id FROM readings WHERE sensor_id=? AND timestamp=?",
            (entry["sensor_id"], entry["timestamp"])
        )
        if c.fetchone():
            stats["skipped"] += 1
            continue

        ensure_sensor_exists(conn, entry["sensor_id"], entry["sensor_name"], entry["zone"])

        c.execute(
            "INSERT INTO readings(sensor_id, timestamp, humidity, temperature) VALUES(?,?,?,?)",
            (entry["sensor_id"], entry["timestamp"], entry["humidity"], entry["temperature"])
        )

        try:
            hour = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S").hour
        except ValueError:
            hour = 12

        rec, conf, ahead = ai_prediction(entry["humidity"], entry["temperature"], hour)
        c.execute(
            "INSERT INTO predictions(sensor_id, timestamp, recommend, confidence, hours_ahead) VALUES(?,?,?,?,?)",
            (entry["sensor_id"], entry["timestamp"], rec, conf, ahead)
        )

        if entry["alert_type"]:
            seuil   = "25" if entry["alert_severity"] == "critical" else "35"
            seuil_t = "40" if entry["alert_severity"] == "critical" else "35"
            msg_map = {
                "low_humidity": f"Humidite {entry['humidity']:.1f}% (seuil : {seuil}%)",
                "high_temp"   : f"Temperature {entry['temperature']:.1f}C (seuil : {seuil_t}C)",
            }
            c.execute(
                "INSERT INTO alerts(sensor_id, timestamp, type, message, severity, resolved) VALUES(?,?,?,?,?,?)",
                (entry["sensor_id"], entry["timestamp"], entry["alert_type"],
                 msg_map.get(entry["alert_type"], f"Alerte : {entry['alert_type']}"),
                 entry["alert_severity"], 0)
            )
            stats["alerts"] += 1

        if entry["irrigation"] and entry["irr_duration"] > 0:
            try:
                ts_dt = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
                ended = (ts_dt + timedelta(minutes=entry["irr_duration"])).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                ended = entry["timestamp"]
            c.execute(
                "INSERT INTO irrigation_events(sensor_id, started_at, ended_at, duration_min, trigger_type) VALUES(?,?,?,?,?)",
                (entry["sensor_id"], entry["timestamp"], ended, entry["irr_duration"], "json")
            )
            stats["irrigations"] += 1

        stats["inserted"] += 1

    conn.commit()
    conn.close()

    print(f"""
[INFO] Chargement JSON termine :
  Fichier      : {JSON_FILE}
  Total        : {stats['total']} entrees
  Inserees     : {stats['inserted']}
  Doublons     : {stats['skipped']} (ignores)
  Invalides    : {stats['invalid']}
  Alertes      : {stats['alerts']}
  Irrigations  : {stats['irrigations']}
""")

# ─── Endpoint rechargement JSON sans redemarrer ───────────────────────────────

@app.route("/api/reload-json", methods=["POST"])
def reload_json():
    load_json_into_db()
    db    = get_db()
    count = db.execute("SELECT COUNT(*) as c FROM readings").fetchone()["c"]
    return jsonify({"ok": True, "message": f"JSON rechargé — {count} lectures en base"})

# ─── Routes API ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/dashboard")
def api_dashboard():
    db      = get_db()
    sensors = db.execute("SELECT * FROM sensors WHERE active=1").fetchall()
    result  = []
    for s in sensors:
        last = db.execute(
            "SELECT * FROM readings WHERE sensor_id=? ORDER BY timestamp DESC LIMIT 1",
            (s["id"],)
        ).fetchone()
        pred = db.execute(
            "SELECT * FROM predictions WHERE sensor_id=? ORDER BY timestamp DESC LIMIT 1",
            (s["id"],)
        ).fetchone()
        unresolved = db.execute(
            "SELECT COUNT(*) as cnt FROM alerts WHERE sensor_id=? AND resolved=0",
            (s["id"],)
        ).fetchone()
        result.append({
            "id"            : s["id"],
            "name"          : s["name"],
            "zone"          : s["zone"],
            "humidity"      : last["humidity"]    if last else 0,
            "temperature"   : last["temperature"] if last else 0,
            "timestamp"     : last["timestamp"]   if last else "",
            "recommendation": pred["recommend"]   if pred else "N/A",
            "confidence"    : round(pred["confidence"] * 100) if pred else 0,
            "alerts"        : unresolved["cnt"]   if unresolved else 0,
        })
    total_alerts      = db.execute("SELECT COUNT(*) as c FROM alerts WHERE resolved=0").fetchone()["c"]
    total_irrigations = db.execute("SELECT COUNT(*) as c FROM irrigation_events").fetchone()["c"]
    return jsonify({
        "sensors"          : result,
        "total_alerts"     : total_alerts,
        "total_irrigations": total_irrigations
    })

@app.route("/api/history/<int:sensor_id>")
def api_history(sensor_id):
    hours  = int(request.args.get("hours", 24))
    db     = get_db()
    latest = db.execute(
        "SELECT MAX(timestamp) as mx FROM readings WHERE sensor_id=?",
        (sensor_id,)
    ).fetchone()["mx"]
    if latest:
        try:
            latest_dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            latest_dt = datetime.now()
    else:
        latest_dt = datetime.now()
    since = (latest_dt - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows  = db.execute(
        "SELECT timestamp, humidity, temperature FROM readings "
        "WHERE sensor_id=? AND timestamp>=? ORDER BY timestamp ASC",
        (sensor_id, since)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/alerts")
def api_alerts():
    db       = get_db()
    resolved = request.args.get("resolved", "0")
    rows     = db.execute(
        "SELECT a.*, s.name as sensor_name, s.zone FROM alerts a "
        "JOIN sensors s ON a.sensor_id=s.id "
        "WHERE a.resolved=? ORDER BY a.timestamp DESC LIMIT 50",
        (int(resolved),)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/alerts/resolve/<int:alert_id>", methods=["POST"])
def resolve_alert(alert_id):
    db = get_db()
    db.execute("UPDATE alerts SET resolved=1 WHERE id=?", (alert_id,))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/irrigations")
def api_irrigations():
    db   = get_db()
    rows = db.execute(
        "SELECT ie.*, s.name as sensor_name, s.zone FROM irrigation_events ie "
        "JOIN sensors s ON ie.sensor_id=s.id ORDER BY started_at DESC LIMIT 30"
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/irrigate", methods=["POST"])
def irrigate():
    data      = request.json
    sensor_id = data.get("sensor_id")
    duration  = data.get("duration", 30)
    db        = get_db()
    now       = datetime.now()
    end       = now + timedelta(minutes=duration)
    db.execute(
        "INSERT INTO irrigation_events(sensor_id, started_at, ended_at, duration_min, trigger_type) VALUES(?,?,?,?,?)",
        (sensor_id,
         now.strftime("%Y-%m-%d %H:%M:%S"),
         end.strftime("%Y-%m-%d %H:%M:%S"),
         duration, "manual")
    )
    db.commit()
    return jsonify({"ok": True, "message": f"Irrigation demarree ({duration} min)"})

@app.route("/api/stats")
def api_stats():
    db     = get_db()
    latest = db.execute("SELECT MAX(timestamp) as mx FROM readings").fetchone()["mx"]
    if latest:
        try:
            latest_dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            latest_dt = datetime.now()
    else:
        latest_dt = datetime.now()
    since_7d = (latest_dt - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    daily_hum = db.execute("""
        SELECT DATE(timestamp)           as day,
               ROUND(AVG(humidity),2)    as avg_hum,
               ROUND(AVG(temperature),2) as avg_tmp,
               ROUND(MIN(humidity),2)    as min_hum
        FROM readings WHERE timestamp>=?
        GROUP BY DATE(timestamp) ORDER BY day
    """, (since_7d,)).fetchall()

    daily_irr = db.execute("""
        SELECT DATE(started_at)  as day,
               COUNT(*)          as count,
               SUM(duration_min) as total_min
        FROM irrigation_events WHERE started_at>=?
        GROUP BY DATE(started_at) ORDER BY day
    """, (since_7d,)).fetchall()

    alert_dist = db.execute("""
        SELECT type, severity, COUNT(*) as count
        FROM alerts WHERE timestamp>=?
        GROUP BY type, severity
    """, (since_7d,)).fetchall()

    zone_hum = db.execute("""
        SELECT s.zone,
               ROUND(AVG(r.humidity),2)    as avg_hum,
               ROUND(AVG(r.temperature),2) as avg_tmp
        FROM readings r JOIN sensors s ON r.sensor_id=s.id
        WHERE r.id IN (SELECT MAX(id) FROM readings GROUP BY sensor_id)
        GROUP BY s.zone
    """).fetchall()

    return jsonify({
        "daily_humidity"    : [dict(r) for r in daily_hum],
        "daily_irrigation"  : [dict(r) for r in daily_irr],
        "alert_distribution": [dict(r) for r in alert_dist],
        "zone_humidity"     : [dict(r) for r in zone_hum],
    })

@app.route("/api/predictions/<int:sensor_id>")
def api_predictions(sensor_id):
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM predictions WHERE sensor_id=? ORDER BY timestamp DESC LIMIT 48",
        (sensor_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/live")
def api_live():
    db   = get_db()
    rows = db.execute("""
        SELECT r.sensor_id, r.humidity, r.temperature, r.timestamp, s.name, s.zone
        FROM readings r JOIN sensors s ON r.sensor_id=s.id
        WHERE r.id IN (SELECT MAX(id) FROM readings GROUP BY sensor_id)
    """).fetchall()
    return jsonify([dict(r) for r in rows])

# ─── Lancement ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # CORRECTION 3 : PAS de os.chdir() ici
    init_db()
    load_json_into_db()
    print("Smart Irrigation System demarre sur http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)