"""
Smart Irrigation System — Flask Backend
Utilise MySQL au lieu de SQLite.

STRUCTURE DU PROJET ATTENDUE :
  Smart_Irrigation_System/
    app/
      projet.py          <- CE FICHIER
    Data/
      data.json
    web/
      templates/
        index.html
      static/
        css/style.css
        js/script.js
    irrigation_db        <- base MySQL (créée automatiquement)
"""

import json, os
import mysql.connector
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, g

# ─── Chemins absolus ──────────────────────────────────────────────────────────
_BASE     = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(_BASE, "..", "Data", "data.json")

# ─── Flask ────────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=os.path.join(_BASE, "..", "..", "web", "templates"),
    static_folder=os.path.join(_BASE,   "..", "..", "web", "static")
)
app.secret_key = "irrigation-secret-2026"

# ─── Configuration MySQL ──────────────────────────────────────────────────────
# Modifiez ces valeurs selon votre configuration
DB_CONFIG = {
    "host"    : "localhost",
    "user"    : "root",
    "password": "",               # <- votre mot de passe MySQL
    "database": "irrigation_db"
}

# ─── Registre des capteurs ────────────────────────────────────────────────────
SENSOR_REGISTRY = {
    1: {"name": "Zone A - Nord",   "zone": "Nord",   "latitude": 31.62, "longitude": -8.01},
    2: {"name": "Zone B - Centre", "zone": "Centre", "latitude": 31.60, "longitude": -8.00},
    3: {"name": "Zone C - Sud",    "zone": "Sud",    "latitude": 31.58, "longitude": -8.02},
    4: {"name": "Zone D - Est",    "zone": "Est",    "latitude": 31.61, "longitude": -7.99},
}

# ─── Seuils d'alerte ──────────────────────────────────────────────────────────
SEUIL_HUM_CRITICAL = 25.0
SEUIL_HUM_WARNING  = 35.0
SEUIL_TMP_CRITICAL = 40.0
SEUIL_TMP_WARNING  = 35.0

# ─── Connexion MySQL ──────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = mysql.connector.connect(**DB_CONFIG)
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db and db.is_connected():
        db.close()

# ─── Initialisation de la base ────────────────────────────────────────────────

def init_db():
    """Crée la base et les tables si elles n'existent pas."""
    conn = mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )
    c = conn.cursor()

    c.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
    c.execute(f"USE {DB_CONFIG['database']}")

    c.execute("""
        CREATE TABLE IF NOT EXISTS sensors (
            id        INT AUTO_INCREMENT PRIMARY KEY,
            name      VARCHAR(100) NOT NULL,
            zone      VARCHAR(50)  NOT NULL,
            latitude  FLOAT,
            longitude FLOAT,
            active    INT DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            sensor_id   INT      NOT NULL,
            timestamp   DATETIME NOT NULL,
            humidity    FLOAT    NOT NULL,
            temperature FLOAT    NOT NULL,
            FOREIGN KEY(sensor_id) REFERENCES sensors(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            sensor_id   INT         NOT NULL,
            timestamp   DATETIME    NOT NULL,
            type        VARCHAR(50) NOT NULL,
            message     TEXT        NOT NULL,
            severity    VARCHAR(20) NOT NULL,
            resolved    INT DEFAULT 0,
            FOREIGN KEY(sensor_id) REFERENCES sensors(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS irrigation_events (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            sensor_id    INT         NOT NULL,
            started_at   DATETIME    NOT NULL,
            ended_at     DATETIME,
            duration_min INT,
            trigger_type VARCHAR(20),
            FOREIGN KEY(sensor_id) REFERENCES sensors(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            sensor_id   INT          NOT NULL,
            timestamp   DATETIME     NOT NULL,
            recommend   VARCHAR(100) NOT NULL,
            confidence  FLOAT        NOT NULL,
            hours_ahead INT          NOT NULL,
            FOREIGN KEY(sensor_id) REFERENCES sensors(id)
        )
    """)

    conn.commit()
    conn.close()
    print("[INFO] Base de donnees MySQL initialisee.")

# ─── Utilitaires JSON ─────────────────────────────────────────────────────────

def normalize_entry(entry):
    """Complète les attributs manquants. Retourne None si entrée invalide."""
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
    """Prédiction IA basée sur humidité, température et heure."""
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

# ─── Chargement JSON -> MySQL ─────────────────────────────────────────────────

def ensure_sensor_exists(conn, sensor_id, sensor_name, zone):
    """Insère le capteur s'il n'existe pas encore."""
    c = conn.cursor()
    c.execute("SELECT id FROM sensors WHERE id=%s", (sensor_id,))
    if c.fetchone():
        return
    reg = SENSOR_REGISTRY.get(sensor_id, {})
    c.execute(
        "INSERT IGNORE INTO sensors(id, name, zone, latitude, longitude) VALUES(%s,%s,%s,%s,%s)",
        (sensor_id, sensor_name, zone, reg.get("latitude"), reg.get("longitude"))
    )

def load_json_into_db():
    """Lit data.json et insère toutes les entrées dans MySQL."""
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

    conn  = mysql.connector.connect(**DB_CONFIG)
    c     = conn.cursor(dictionary=True)
    stats = {"total": 0, "inserted": 0, "skipped": 0,
             "invalid": 0, "alerts": 0, "irrigations": 0}

    for raw in raw_data:
        stats["total"] += 1
        entry = normalize_entry(raw)

        if entry is None:
            stats["invalid"] += 1
            print(f"[WARN] Entree ignoree : {raw}")
            continue

        # Vérification doublon
        c.execute(
            "SELECT id FROM readings WHERE sensor_id=%s AND timestamp=%s",
            (entry["sensor_id"], entry["timestamp"])
        )
        if c.fetchone():
            stats["skipped"] += 1
            continue

        ensure_sensor_exists(conn, entry["sensor_id"], entry["sensor_name"], entry["zone"])

        # Lecture
        c.execute(
            "INSERT INTO readings(sensor_id, timestamp, humidity, temperature) VALUES(%s,%s,%s,%s)",
            (entry["sensor_id"], entry["timestamp"], entry["humidity"], entry["temperature"])
        )

        # Prédiction IA
        try:
            hour = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S").hour
        except ValueError:
            hour = 12

        rec, conf, ahead = ai_prediction(entry["humidity"], entry["temperature"], hour)
        c.execute(
            "INSERT INTO predictions(sensor_id, timestamp, recommend, confidence, hours_ahead) VALUES(%s,%s,%s,%s,%s)",
            (entry["sensor_id"], entry["timestamp"], rec, conf, ahead)
        )

        # Alerte
        if entry["alert_type"]:
            seuil   = "25" if entry["alert_severity"] == "critical" else "35"
            seuil_t = "40" if entry["alert_severity"] == "critical" else "35"
            msg_map = {
                "low_humidity": f"Humidite {entry['humidity']:.1f}% (seuil : {seuil}%)",
                "high_temp"   : f"Temperature {entry['temperature']:.1f}C (seuil : {seuil_t}C)",
            }
            c.execute(
                "INSERT INTO alerts(sensor_id, timestamp, type, message, severity, resolved) VALUES(%s,%s,%s,%s,%s,%s)",
                (entry["sensor_id"], entry["timestamp"], entry["alert_type"],
                 msg_map.get(entry["alert_type"], f"Alerte : {entry['alert_type']}"),
                 entry["alert_severity"], 0)
            )
            stats["alerts"] += 1

        # Irrigation
        if entry["irrigation"] and entry["irr_duration"] > 0:
            try:
                ts_dt = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
                ended = (ts_dt + timedelta(minutes=entry["irr_duration"])).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                ended = entry["timestamp"]
            c.execute(
                "INSERT INTO irrigation_events(sensor_id, started_at, ended_at, duration_min, trigger_type) VALUES(%s,%s,%s,%s,%s)",
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

# ─── Endpoint rechargement JSON ───────────────────────────────────────────────

@app.route("/api/reload-json", methods=["POST"])
def reload_json():
    load_json_into_db()
    conn  = get_db()
    c     = conn.cursor(dictionary=True)
    c.execute("SELECT COUNT(*) as c FROM readings")
    count = c.fetchone()["c"]
    return jsonify({"ok": True, "message": f"JSON rechargé — {count} lectures en base"})

# ─── Routes API ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/dashboard")
def api_dashboard():
    conn    = get_db()
    c       = conn.cursor(dictionary=True)

    c.execute("SELECT * FROM sensors WHERE active=1")
    sensors = c.fetchall()

    result = []
    for s in sensors:
        c.execute(
            "SELECT * FROM readings WHERE sensor_id=%s ORDER BY timestamp DESC LIMIT 1",
            (s["id"],)
        )
        last = c.fetchone()

        c.execute(
            "SELECT * FROM predictions WHERE sensor_id=%s ORDER BY timestamp DESC LIMIT 1",
            (s["id"],)
        )
        pred = c.fetchone()

        c.execute(
            "SELECT COUNT(*) as cnt FROM alerts WHERE sensor_id=%s AND resolved=0",
            (s["id"],)
        )
        unresolved = c.fetchone()

        result.append({
            "id"            : s["id"],
            "name"          : s["name"],
            "zone"          : s["zone"],
            "humidity"      : last["humidity"]    if last else 0,
            "temperature"   : last["temperature"] if last else 0,
            "timestamp"     : str(last["timestamp"]) if last else "",
            "recommendation": pred["recommend"]   if pred else "N/A",
            "confidence"    : round(pred["confidence"] * 100) if pred else 0,
            "alerts"        : unresolved["cnt"]   if unresolved else 0,
        })

    c.execute("SELECT COUNT(*) as c FROM alerts WHERE resolved=0")
    total_alerts = c.fetchone()["c"]

    c.execute("SELECT COUNT(*) as c FROM irrigation_events")
    total_irrigations = c.fetchone()["c"]

    return jsonify({
        "sensors"          : result,
        "total_alerts"     : total_alerts,
        "total_irrigations": total_irrigations
    })

@app.route("/api/history/<int:sensor_id>")
def api_history(sensor_id):
    hours = int(request.args.get("hours", 24))
    conn  = get_db()
    c     = conn.cursor(dictionary=True)

    c.execute(
        "SELECT MAX(timestamp) as mx FROM readings WHERE sensor_id=%s",
        (sensor_id,)
    )
    row = c.fetchone()
    latest = row["mx"] if row else None

    if latest:
        latest_dt = latest if isinstance(latest, datetime) else datetime.strptime(str(latest), "%Y-%m-%d %H:%M:%S")
    else:
        latest_dt = datetime.now()

    since = (latest_dt - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        "SELECT timestamp, humidity, temperature FROM readings "
        "WHERE sensor_id=%s AND timestamp>=%s ORDER BY timestamp ASC",
        (sensor_id, since)
    )
    rows = c.fetchall()

    # Convertir datetime en string pour JSON
    for r in rows:
        r["timestamp"] = str(r["timestamp"])

    return jsonify(rows)

@app.route("/api/alerts")
def api_alerts():
    conn     = get_db()
    c        = conn.cursor(dictionary=True)
    resolved = request.args.get("resolved", "0")

    c.execute(
        "SELECT a.*, s.name as sensor_name, s.zone FROM alerts a "
        "JOIN sensors s ON a.sensor_id=s.id "
        "WHERE a.resolved=%s ORDER BY a.timestamp DESC LIMIT 50",
        (int(resolved),)
    )
    rows = c.fetchall()
    for r in rows:
        r["timestamp"] = str(r["timestamp"])
    return jsonify(rows)

@app.route("/api/alerts/resolve/<int:alert_id>", methods=["POST"])
def resolve_alert(alert_id):
    conn = get_db()
    c    = conn.cursor()
    c.execute("UPDATE alerts SET resolved=1 WHERE id=%s", (alert_id,))
    conn.commit()
    return jsonify({"ok": True})

@app.route("/api/irrigations")
def api_irrigations():
    conn = get_db()
    c    = conn.cursor(dictionary=True)
    c.execute(
        "SELECT ie.*, s.name as sensor_name, s.zone FROM irrigation_events ie "
        "JOIN sensors s ON ie.sensor_id=s.id ORDER BY started_at DESC LIMIT 30"
    )
    rows = c.fetchall()
    for r in rows:
        r["started_at"] = str(r["started_at"])
        r["ended_at"]   = str(r["ended_at"]) if r["ended_at"] else None
    return jsonify(rows)

@app.route("/api/irrigate", methods=["POST"])
def irrigate():
    data      = request.json
    sensor_id = data.get("sensor_id")
    duration  = data.get("duration", 30)
    conn      = get_db()
    c         = conn.cursor()
    now       = datetime.now()
    end       = now + timedelta(minutes=duration)
    c.execute(
        "INSERT INTO irrigation_events(sensor_id, started_at, ended_at, duration_min, trigger_type) VALUES(%s,%s,%s,%s,%s)",
        (sensor_id,
         now.strftime("%Y-%m-%d %H:%M:%S"),
         end.strftime("%Y-%m-%d %H:%M:%S"),
         duration, "manual")
    )
    conn.commit()
    return jsonify({"ok": True, "message": f"Irrigation demarree ({duration} min)"})

@app.route("/api/stats")
def api_stats():
    conn = get_db()
    c    = conn.cursor(dictionary=True)

    c.execute("SELECT MAX(timestamp) as mx FROM readings")
    row    = c.fetchone()
    latest = row["mx"] if row else None

    if latest:
        latest_dt = latest if isinstance(latest, datetime) else datetime.strptime(str(latest), "%Y-%m-%d %H:%M:%S")
    else:
        latest_dt = datetime.now()

    since_7d = (latest_dt - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        SELECT DATE(timestamp)           as day,
               ROUND(AVG(humidity),2)    as avg_hum,
               ROUND(AVG(temperature),2) as avg_tmp,
               ROUND(MIN(humidity),2)    as min_hum
        FROM readings WHERE timestamp>=%s
        GROUP BY DATE(timestamp) ORDER BY day
    """, (since_7d,))
    daily_hum = c.fetchall()
    for r in daily_hum:
        r["day"] = str(r["day"])

    c.execute("""
        SELECT DATE(started_at)  as day,
               COUNT(*)          as count,
               SUM(duration_min) as total_min
        FROM irrigation_events WHERE started_at>=%s
        GROUP BY DATE(started_at) ORDER BY day
    """, (since_7d,))
    daily_irr = c.fetchall()
    for r in daily_irr:
        r["day"] = str(r["day"])

    c.execute("""
        SELECT type, severity, COUNT(*) as count
        FROM alerts WHERE timestamp>=%s
        GROUP BY type, severity
    """, (since_7d,))
    alert_dist = c.fetchall()

    c.execute("""
        SELECT s.zone,
               ROUND(AVG(r.humidity),2)    as avg_hum,
               ROUND(AVG(r.temperature),2) as avg_tmp
        FROM readings r JOIN sensors s ON r.sensor_id=s.id
        WHERE r.id IN (SELECT MAX(id) FROM readings GROUP BY sensor_id)
        GROUP BY s.zone
    """)
    zone_hum = c.fetchall()

    return jsonify({
        "daily_humidity"    : daily_hum,
        "daily_irrigation"  : daily_irr,
        "alert_distribution": alert_dist,
        "zone_humidity"     : zone_hum,
    })

@app.route("/api/predictions/<int:sensor_id>")
def api_predictions(sensor_id):
    conn = get_db()
    c    = conn.cursor(dictionary=True)
    c.execute(
        "SELECT * FROM predictions WHERE sensor_id=%s ORDER BY timestamp DESC LIMIT 48",
        (sensor_id,)
    )
    rows = c.fetchall()
    for r in rows:
        r["timestamp"] = str(r["timestamp"])
    return jsonify(rows)

@app.route("/api/live")
def api_live():
    conn = get_db()
    c    = conn.cursor(dictionary=True)
    c.execute("""
        SELECT r.sensor_id, r.humidity, r.temperature, r.timestamp, s.name, s.zone
        FROM readings r JOIN sensors s ON r.sensor_id=s.id
        WHERE r.id IN (SELECT MAX(id) FROM readings GROUP BY sensor_id)
    """)
    rows = c.fetchall()
    for r in rows:
        r["timestamp"] = str(r["timestamp"])
    return jsonify(rows)

# ─── Lancement ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    load_json_into_db()
    print("Smart Irrigation System demarre sur http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
