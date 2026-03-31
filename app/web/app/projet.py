"""
Smart Irrigation System — Flask Backend
Utilise MySQL au lieu de SQLite.

STRUCTURE DU PROJET ATTENDUE :
  Smart_Irrigation_System/
    app/
      projet.py          <- CE FICHIER
    Data/
      data.json
    data/
      model.pkl          <- livre par le coequipier Data (optionnel)
    web/
      templates/
        index.html
      static/
        css/style.css
        js/script.js
    irrigation_db        <- base MySQL (creee automatiquement)
"""

import json, os
import mysql.connector
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, g

# ─── AJOUT : CORS pour autoriser les requetes du simulateur ──────────────────
# pip install flask-cors
from flask_cors import CORS

# ─── AJOUT : chargement optionnel du modele IA (livre par Data) ──────────────
import joblib

# ─── Chemins absolus ──────────────────────────────────────────────────────────
_BASE      = os.path.dirname(os.path.abspath(__file__))
JSON_FILE  = os.path.join(_BASE, "..", "Data", "data.json")

# ─── AJOUT : chemin vers le modele IA ────────────────────────────────────────
MODEL_PATH = os.path.join(_BASE, "..", "data", "model.pkl")

# ─── Flask ────────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=os.path.join(_BASE, "..", "templates"),
    static_folder=os.path.join(_BASE, "..", "static")
)
app.secret_key = "irrigation-secret-2026"

# ─── AJOUT : activer CORS sur toutes les routes ──────────────────────────────
# Necessaire pour que le simulateur (autre PC) puisse envoyer des requetes
CORS(app)

# ─── Configuration MySQL ──────────────────────────────────────────────────────
DB_CONFIG = {
    "host"    : "localhost",
    "user"    : "root",
    "password": "",               # <- votre mot de passe MySQL
    "database": "irrigation_db"
}

# ─── SUPPRIME : SENSOR_REGISTRY code en dur ───────────────────────────────────
# Les capteurs se creent maintenant automatiquement via POST /api/data
# Plus besoin de les definir ici manuellement

# ─── Seuils d'alerte ──────────────────────────────────────────────────────────
SEUIL_HUM_CRITICAL = 25.0
SEUIL_HUM_WARNING  = 35.0
SEUIL_TMP_CRITICAL = 40.0
SEUIL_TMP_WARNING  = 35.0

# ─── AJOUT : chargement du modele IA au demarrage ────────────────────────────
# Si model.pkl existe (livre par Data), on l'utilise.
# Sinon, on utilise la fonction de secours ai_prediction().
_ML_MODEL = None
if os.path.exists(MODEL_PATH):
    try:
        _ML_MODEL = joblib.load(MODEL_PATH)
        print(f"[INFO] Modele IA charge depuis {MODEL_PATH}")
    except Exception as e:
        print(f"[WARN] Impossible de charger model.pkl : {e}")
else:
    print("[INFO] model.pkl absent — utilisation de la prediction de secours.")

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
    """Cree la base et les tables si elles n'existent pas."""
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
    """Complete les attributs manquants. Retourne None si entree invalide."""
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

    # MODIFIE : plus de SENSOR_REGISTRY, on prend ce qui est dans le JSON
    sensor_name = entry.get("sensor_name") or f"Capteur {sensor_id}"
    zone        = entry.get("zone")        or f"Zone {sensor_id}"

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

# ─── MODIFIE : ai_prediction utilise le vrai modele si disponible ─────────────

def ai_prediction(humidity, temperature, hour):
    """
    Prediction IA.
    - Si model.pkl est charge : utilise le vrai modele ML (livre par Data).
    - Sinon : utilise la logique de secours basee sur les seuils.
    """
    # ── Vrai modele ML ────────────────────────────────────────────────────────
    if _ML_MODEL is not None:
        try:
            features = [[humidity, temperature, hour]]
            pred     = _ML_MODEL.predict(features)[0]
            proba    = _ML_MODEL.predict_proba(features)[0]

            if pred == 1:
                confidence = round(float(proba[1]), 2)
                if confidence > 0.85:
                    return "Irriguer maintenant", confidence, 0
                else:
                    return "Irriguer dans 2h",    confidence, 2
            else:
                return "Pas necessaire", round(float(proba[0]), 2), 8

        except Exception as e:
            print(f"[WARN] Erreur modele ML : {e} — bascule sur logique de secours")

    # ── Logique de secours (sans model.pkl) ───────────────────────────────────
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

# ─── AJOUT : helper interne factorise ────────────────────────────────────────

def ensure_sensor_exists(conn, sensor_id, sensor_name, zone):
    """Insere le capteur s'il n'existe pas encore."""
    c = conn.cursor()
    c.execute("SELECT id FROM sensors WHERE id=%s", (sensor_id,))
    if c.fetchone():
        return
    c.execute(
        "INSERT IGNORE INTO sensors(id, name, zone, active) VALUES(%s,%s,%s,1)",
        (sensor_id, sensor_name, zone)
    )

def _insert_reading_and_side_effects(conn, sensor_id, humidity, temperature, timestamp):
    """
    Insere une lecture + prediction + alerte eventuelle.
    Factorise la logique commune entre load_json_into_db et POST /api/data.
    Retourne 'skipped' si doublon, sinon la recommandation IA.
    """
    c = conn.cursor(dictionary=True)

    # Doublon ?
    c.execute(
        "SELECT id FROM readings WHERE sensor_id=%s AND timestamp=%s",
        (sensor_id, timestamp)
    )
    if c.fetchone():
        return "skipped"

    # Lecture
    c.execute(
        "INSERT INTO readings(sensor_id, timestamp, humidity, temperature) VALUES(%s,%s,%s,%s)",
        (sensor_id, timestamp, humidity, temperature)
    )

    # Prediction IA
    try:
        hour = datetime.strptime(str(timestamp), "%Y-%m-%d %H:%M:%S").hour
    except ValueError:
        hour = datetime.now().hour

    rec, conf, ahead = ai_prediction(humidity, temperature, hour)
    c.execute(
        "INSERT INTO predictions(sensor_id, timestamp, recommend, confidence, hours_ahead) "
        "VALUES(%s,%s,%s,%s,%s)",
        (sensor_id, timestamp, rec, conf, ahead)
    )

    # Alerte si seuil depasse
    alert_type = alert_severity = None
    if humidity < SEUIL_HUM_CRITICAL:
        alert_type, alert_severity = "low_humidity", "critical"
    elif humidity < SEUIL_HUM_WARNING:
        alert_type, alert_severity = "low_humidity", "warning"
    elif temperature > SEUIL_TMP_CRITICAL:
        alert_type, alert_severity = "high_temp", "critical"
    elif temperature > SEUIL_TMP_WARNING:
        alert_type, alert_severity = "high_temp", "warning"

    if alert_type:
        if "humidity" in alert_type:
            seuil = SEUIL_HUM_CRITICAL if alert_severity == "critical" else SEUIL_HUM_WARNING
            msg   = f"Humidite {humidity:.1f}% (seuil : {seuil}%)"
        else:
            seuil = SEUIL_TMP_CRITICAL if alert_severity == "critical" else SEUIL_TMP_WARNING
            msg   = f"Temperature {temperature:.1f}C (seuil : {seuil}C)"

        c.execute(
            "INSERT INTO alerts(sensor_id, timestamp, type, message, severity, resolved) "
            "VALUES(%s,%s,%s,%s,%s,0)",
            (sensor_id, timestamp, alert_type, msg, alert_severity)
        )

    return rec

# ─── Chargement JSON -> MySQL ─────────────────────────────────────────────────

def load_json_into_db():
    """Lit data.json et insere toutes les entrees dans MySQL (import initial)."""
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
    stats = {"total": 0, "inserted": 0, "skipped": 0, "invalid": 0, "irrigations": 0}

    for raw in raw_data:
        stats["total"] += 1
        entry = normalize_entry(raw)

        if entry is None:
            stats["invalid"] += 1
            print(f"[WARN] Entree ignoree : {raw}")
            continue

        ensure_sensor_exists(conn, entry["sensor_id"], entry["sensor_name"], entry["zone"])

        result = _insert_reading_and_side_effects(
            conn,
            entry["sensor_id"],
            entry["humidity"],
            entry["temperature"],
            entry["timestamp"]
        )

        if result == "skipped":
            stats["skipped"] += 1
            continue

        # Irrigation (specifique au JSON historique)
        if entry["irrigation"] and entry["irr_duration"] > 0:
            try:
                ts_dt = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
                ended = (ts_dt + timedelta(minutes=entry["irr_duration"])).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                ended = entry["timestamp"]
            c2 = conn.cursor()
            c2.execute(
                "INSERT INTO irrigation_events"
                "(sensor_id, started_at, ended_at, duration_min, trigger_type) "
                "VALUES(%s,%s,%s,%s,%s)",
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
  Irrigations  : {stats['irrigations']}
""")

# =============================================================================
# AJOUT 1 — Reception des donnees du simulateur embarque
# =============================================================================

@app.route("/api/data", methods=["POST"])
def receive_sensor_data():
    """
    Recoit les donnees du simulateur (coequipier embarque).
    Appelee automatiquement toutes les 30 secondes par simulator.py.

    Corps JSON attendu :
    {
        "sensor_id"   : 1,
        "sensor_name" : "Zone A",      <- optionnel
        "zone"        : "Nord",        <- optionnel
        "humidity"    : 43.2,
        "temperature" : 27.8
    }
    """
    data = request.get_json(silent=True)

    # Validation
    if not data:
        return jsonify({"ok": False, "error": "Corps JSON manquant"}), 400

    for field in ("sensor_id", "humidity", "temperature"):
        if field not in data:
            return jsonify({"ok": False, "error": f"Champ manquant : {field}"}), 400

    try:
        sensor_id   = int(data["sensor_id"])
        humidity    = float(data["humidity"])
        temperature = float(data["temperature"])
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": f"Valeur invalide : {e}"}), 400

    if not (0 <= humidity <= 100):
        return jsonify({"ok": False, "error": "humidity doit etre entre 0 et 100"}), 400

    if not (-10 <= temperature <= 60):
        return jsonify({"ok": False, "error": "temperature hors limites"}), 400

    sensor_name = data.get("sensor_name", f"Capteur {sensor_id}")
    zone        = data.get("zone",        f"Zone {sensor_id}")
    now         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    ensure_sensor_exists(conn, sensor_id, sensor_name, zone)
    recommendation = _insert_reading_and_side_effects(
        conn, sensor_id, humidity, temperature, now
    )
    conn.commit()

    print(f"[DATA] {zone} | H={humidity}% T={temperature}C | {recommendation}")

    return jsonify({
        "ok"            : True,
        "timestamp"     : now,
        "sensor_id"     : sensor_id,
        "recommendation": recommendation,
    })

# =============================================================================
# AJOUT 2 — Rechargement du modele IA a chaud (quand Data livre model.pkl)
# =============================================================================

@app.route("/api/reload-model", methods=["POST"])
def reload_model():
    """
    Recharge model.pkl sans redemarrer Flask.
    Utile quand Data livre une nouvelle version du modele.
    Appel : POST http://localhost:5000/api/reload-model
    """
    global _ML_MODEL
    if not os.path.exists(MODEL_PATH):
        return jsonify({"ok": False, "error": f"model.pkl introuvable : {MODEL_PATH}"}), 404
    try:
        _ML_MODEL = joblib.load(MODEL_PATH)
        return jsonify({"ok": True, "message": "Modele IA recharge avec succes"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── Endpoint rechargement JSON ───────────────────────────────────────────────

@app.route("/api/reload-json", methods=["POST"])
def reload_json():
    load_json_into_db()
    conn = get_db()
    c    = conn.cursor(dictionary=True)
    c.execute("SELECT COUNT(*) as c FROM readings")
    count = c.fetchone()["c"]
    return jsonify({"ok": True, "message": f"JSON recharge — {count} lectures en base"})

# ─── Routes API existantes ────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/dashboard")
def api_dashboard():
    conn = get_db()
    c    = conn.cursor(dictionary=True)

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
        "total_irrigations": total_irrigations,
        "model_active"     : _ML_MODEL is not None,  # AJOUT : utile pour afficher badge IA
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
    row    = c.fetchone()
    latest = row["mx"] if row else None

    if latest:
        latest_dt = latest if isinstance(latest, datetime) \
                    else datetime.strptime(str(latest), "%Y-%m-%d %H:%M:%S")
    else:
        latest_dt = datetime.now()

    since = (latest_dt - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        "SELECT timestamp, humidity, temperature FROM readings "
        "WHERE sensor_id=%s AND timestamp>=%s ORDER BY timestamp ASC",
        (sensor_id, since)
    )
    rows = c.fetchall()
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
        "INSERT INTO irrigation_events"
        "(sensor_id, started_at, ended_at, duration_min, trigger_type) "
        "VALUES(%s,%s,%s,%s,%s)",
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
        latest_dt = latest if isinstance(latest, datetime) \
                    else datetime.strptime(str(latest), "%Y-%m-%d %H:%M:%S")
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
    print("=" * 55)
    print("  Smart Irrigation System")
    print(f"  Modele IA : {'ACTIF (model.pkl)' if _ML_MODEL else 'secours (seuils)'}")
    print("  Dashboard  : http://localhost:5000")
    print("  API data   : POST http://0.0.0.0:5000/api/data")
    print("=" * 55)
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)