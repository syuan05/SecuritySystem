# app.py
from flask import Flask, render_template, jsonify, request, Response
import os, cv2, json, time, threading
from dotenv import load_dotenv
from db_utils import get_db_connection
from detector.video_manager import manager_instance as manager


load_dotenv()
app = Flask(__name__)
# manager = VideoManager()   # 只建立實例，不載入模型、不開攝影機


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/camera')
def camera():
    return render_template('camera.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')


@app.route("/video_feed/<int:camera_id>")
def video_feed(camera_id):
    def generate():
        while True:
            frame = manager.get_last_frame(camera_id)
            # if frame is not None:
                # print(f"[STREAM] Sending frame from camera {camera_id} at {time.time():.3f}")
            if frame is not None:
                _, buffer = cv2.imencode(".jpg", frame)
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
            time.sleep(0.05)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route('/api/cameras')
def get_cameras():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT camera_id, camera_name, camera_url FROM cameras ORDER BY camera_id;")
    data = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(data)


@app.route('/api/camera/<int:camera_id>')
def get_camera(camera_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT camera_id, camera_name, camera_url,
               falling_detection_mode, climbing_detection_mode
        FROM cameras WHERE camera_id = %s;
    """, (camera_id,))
    cam = cur.fetchone()
    if not cam:
        cur.close(); conn.close()
        return jsonify({"error": "Camera not found"}), 404

    # 抓 schedule
    cur.execute("""
        SELECT function_type, start_time, end_time
        FROM func_schedules
        WHERE camera_id = %s
          AND function_type IN ('falling', 'climbing')
          AND is_active = 1;
    """, (camera_id,))
    schedules = cur.fetchall()
    cur.close(); conn.close()

    def fmt_time(t):
        if not t: return "--:--"
        if isinstance(t, str): return t[:5]
        if hasattr(t, "seconds"):
            h, m = divmod(int(t.total_seconds()) // 60, 60)
            return f"{h:02d}:{m:02d}"
        return str(t)

    cam["schedules"] = {
        s["function_type"]: {"start": fmt_time(s["start_time"]), "end": fmt_time(s["end_time"])}
        for s in schedules
    }
    return jsonify(cam)

@app.route('/api/fence/<string:type>')
def get_fence(type):
    cam_id = request.args.get("camera_id")
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    config = {
        "inout": {"table": "gates", "mode": "in_out_control_mode", "func": "in_out_control"},
        "intrusion": {"table": "gates", "mode": "intrusion_mode", "func": "intrusion"},
        "crowd": {"table": "gates", "mode": "person_count_mode", "func": "person_count"},
        "people": {"table": "gates", "mode": "people_detect_mode", "func": "people_detect"}
    }

    if type not in config:
        return jsonify({"error": "invalid type"}), 400

    table = config[type]["table"]
    mode_col = config[type]["mode"]
    func_type = config[type]["func"]

    # --- 抓主表 ---
    cur.execute(f"""
        SELECT gate_id AS id, gate_name AS name, direction
        FROM {table}
        WHERE camera_id = %s AND {mode_col} = TRUE
        ORDER BY gate_id;
    """, (cam_id,))
    items = cur.fetchall()

    # --- 抓 schedule ---
    cur.execute("""
        SELECT gate_id, start_time, end_time
        FROM func_schedules
        WHERE function_type = %s AND is_active = 1;
    """, (func_type,))
    schedules = cur.fetchall()

    sched_map = {
        s["gate_id"]: {
            "start_time": fmt_time(s["start_time"]),
            "end_time": fmt_time(s["end_time"])
        } for s in schedules
    }

    for g in items:
        g.update(sched_map.get(g["id"], {"start_time": "--:--", "end_time": "--:--"}))

    cur.close()
    conn.close()
    return jsonify(items)

def fmt_time(t):
    """將 MySQL TIME (timedelta or str) 安全轉成 HH:MM"""
    if not t:
        return "--:--"
    if isinstance(t, str):
        return t[:5]
    if hasattr(t, "seconds"):
        total_seconds = int(t.total_seconds())
        h = (total_seconds // 3600) % 24
        m = (total_seconds % 3600) // 60
        return f"{h:02d}:{m:02d}"
    return str(t)

@app.route('/api/fence/<string:type>/add', methods=['POST'])
@app.route('/api/fence/<string:type>/add', methods=['POST'])
def add_fence(type):
    data = request.json
    print("📦 Received JSON for fence:", json.dumps(data, indent=2, ensure_ascii=False))
    conn = get_db_connection()
    cur = conn.cursor()

    if type == "inout":
        table, func_type, mode_col = "gates", "in_out_control", "in_out_control_mode"
        need_schedule = True
    elif type == "intrusion":
        table, func_type, mode_col = "gates", "intrusion", "intrusion_mode"
        need_schedule = True
    elif type == "crowd":
        table, func_type, mode_col = "gates", "person_count", "person_count_mode"
        need_schedule = False
    elif type == "people":
        table, func_type, mode_col = "gates", "people_detect", "people_detect_mode"
        need_schedule = False
    else:
        return jsonify({"error": "invalid type"}), 400

    try:
        # === Step 1. 新增主表 ===
        cur.execute(f"""
            INSERT INTO {table} (
                camera_id, gate_name, polygon_json, direction, {mode_col}
            ) VALUES (%s, %s, %s, %s, TRUE);
        """, (
            data["camera_id"],
            data["name"],
            json.dumps({"A": data["point_a"], "B": data["point_b"]}),
            data.get("direction", "N/A")
        ))
        obj_id = cur.lastrowid

        # === Step 2. 視情況新增對應的 schedule ===
        if need_schedule:
            cur.execute("""
                INSERT INTO func_schedules (camera_id, gate_id, function_type, start_time, end_time, is_active)
                VALUES (%s, %s, %s, %s, %s, 1);
            """, (
                data["camera_id"],
                obj_id,
                func_type,
                data["start_time"],
                data["end_time"]
            ))
        else:
            # 不需要時間的功能就只記錄啟用狀態
            cur.execute("""
                INSERT INTO func_schedules (camera_id, gate_id, function_type, is_active)
                VALUES (%s, %s, %s, 1);
            """, (
                data["camera_id"],
                obj_id,
                func_type
            ))

        conn.commit()
        return jsonify({
            "status": "ok",
            "id": obj_id,
            "type": type,
            "received": data
        })

    except Exception as e:
        conn.rollback()
        print("❌ Add fence error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        cur.close()
        conn.close()


# 更新 / 刪除圍籬
@app.route('/api/gate_fence/<int:fence_id>', methods=['PUT', 'DELETE'])
def update_or_delete_fence(fence_id):
    conn = get_db_connection(); cur = conn.cursor()
    if request.method == "DELETE":
        cur.execute("DELETE FROM func_schedules WHERE id=%s;", (fence_id,))
    else:
        d = request.json
        cur.execute("""
            UPDATE func_schedules
            SET fence_name=%s, direction=%s, start_time=%s, end_time=%s
            WHERE id=%s;
        """, (d["name"], d["direction"], d["start_time"], d["end_time"], fence_id))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"status": "ok"})

@app.route("/api/mode/<mode>", methods=["POST"])
def update_mode(mode):
    data = request.get_json()
    camera_id = data["camera_id"]
    enabled = data["enabled"]

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1️⃣ 更新 cameras 表
        cur.execute(f"""
            UPDATE cameras 
            SET {mode}_detection_mode = %s 
            WHERE camera_id = %s;
        """, (enabled, camera_id))

        # 2️⃣ 同步更新 func_schedules 啟用狀態
        cur.execute("""
            UPDATE func_schedules
            SET is_active = %s
            WHERE camera_id = %s AND function_type = %s;
        """, (1 if enabled else 0, camera_id, mode))

        conn.commit()
        return jsonify({"status": "ok", "message": f"{mode} mode updated"})

    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        cur.close()
        conn.close()

    return jsonify({"status": "ok", "message": f"{mode} mode updated"})

@app.route("/api/schedule/<mode>", methods=["POST"])
def update_schedule(mode):
    data = request.get_json()
    camera_id = data["camera_id"]
    start = data["start_time"]
    end = data["end_time"]

    conn = get_db_connection()
    cur = conn.cursor()

    # 檢查是否已有紀錄
    cur.execute("""
        SELECT COUNT(*) AS cnt FROM func_schedules
        WHERE camera_id=%s AND function_type=%s;
    """, (camera_id, mode))
    exists = cur.fetchone()[0]

    if exists:
        # 更新既有時間設定
        cur.execute("""
            UPDATE func_schedules
            SET start_time=%s, end_time=%s
            WHERE camera_id=%s AND function_type=%s AND is_active=1;
        """, (start, end, camera_id, mode))
    else:
        # 若沒有該相機的紀錄 → 新增一筆
        cur.execute("""
            INSERT INTO func_schedules (camera_id, function_type, start_time, end_time, is_active)
            VALUES (%s, %s, %s, %s, 1);
        """, (camera_id, mode, start, end))

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "message": f"{mode} schedule updated"})
    
@app.route("/api/reload_gates/<int:camera_id>", methods=["POST"])
def reload_gates(camera_id):
    print(f"🔄 Reloading gates for camera {camera_id} ...")
    print(id(manager))
    try:
        manager.reload_gates(camera_id)   # 🔁 同一個 manager 物件
        return jsonify({"status": "ok", "camera_id": camera_id})
    except Exception as e:
        print(f"❌ reload_gates() failed for camera {camera_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/events')
def get_events():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 取得查詢參數
    event_type = request.args.get("type")
    level = request.args.get("level")
    start = request.args.get("start")
    end = request.args.get("end")

    query = """
        SELECT 
            e.event_id,
            e.camera_id,
            c.camera_name,
            e.gate_id,
            g.gate_name,
            e.event_type,
            e.alert_level,
            e.timestamp
        FROM events e
        LEFT JOIN cameras c ON e.camera_id = c.camera_id
        LEFT JOIN gates g ON e.gate_id = g.gate_id
        WHERE 1=1
    """
    params = []

    if event_type:
        query += " AND e.event_type = %s"
        params.append(event_type)

    if level:
        query += " AND e.alert_level = %s"
        params.append(level)

    if start:
        query += " AND e.timestamp >= %s"
        params.append(start)

    if end:
        query += " AND e.timestamp <= %s"
        params.append(end)

    query += " ORDER BY e.timestamp DESC"

    cur.execute(query, params)
    data = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(data)

@app.route("/api/people/hourly")
def people_hourly():
    camera_id = request.args.get("camera_id", type=int)
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    if camera_id:
        cur.execute("""
            SELECT HOUR(timestamp) AS hour, COUNT(*) AS count
            FROM people_flow
            WHERE timestamp >= NOW() - INTERVAL 24 HOUR
              AND camera_id = %s
            GROUP BY HOUR(timestamp)
            ORDER BY hour;
        """, (camera_id,))
    else:
        cur.execute("""
            SELECT HOUR(timestamp) AS hour, COUNT(*) AS count
            FROM people_flow
            WHERE timestamp >= NOW() - INTERVAL 24 HOUR
            GROUP BY HOUR(timestamp)
            ORDER BY hour;
        """)
    data = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(data)


# 🔹 近一週
@app.route("/api/people/weekly")
def people_weekly():
    camera_id = request.args.get("camera_id", type=int)
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    if camera_id:
        cur.execute("""
            SELECT DATE(timestamp) AS date, COUNT(*) AS count
            FROM people_flow
            WHERE timestamp >= CURDATE() - INTERVAL 7 DAY
              AND camera_id = %s
            GROUP BY DATE(timestamp)
            ORDER BY date;
        """, (camera_id,))
    else:
        cur.execute("""
            SELECT DATE(timestamp) AS date, COUNT(*) AS count
            FROM people_flow
            WHERE timestamp >= CURDATE() - INTERVAL 7 DAY
            GROUP BY DATE(timestamp)
            ORDER BY date;
        """)
    data = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(data)


# 🔹 自訂時段
@app.route("/api/people/custom")
def people_custom():
    start = request.args.get("start", "09:00")
    end = request.args.get("end", "18:00")
    camera_id = request.args.get("camera_id", type=int)
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    if camera_id:
        cur.execute(f"""
            SELECT DATE(timestamp) AS date, COUNT(*) AS count
            FROM people_flow
            WHERE HOUR(timestamp) BETWEEN HOUR(%s) AND HOUR(%s)
              AND timestamp >= CURDATE() - INTERVAL 7 DAY
              AND camera_id = %s
            GROUP BY DATE(timestamp)
            ORDER BY date;
        """, (start, end, camera_id))
    else:
        cur.execute(f"""
            SELECT DATE(timestamp) AS date, COUNT(*) AS count
            FROM people_flow
            WHERE HOUR(timestamp) BETWEEN HOUR(%s) AND HOUR(%s)
              AND timestamp >= CURDATE() - INTERVAL 7 DAY
            GROUP BY DATE(timestamp)
            ORDER BY date;
        """, (start, end))
    data = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(data)

def start_detection_system():
    print("🔄 Loading cameras and starting detection system...")
    try:
        manager.load_all_cameras()        
        print("✅ Detection system started successfully.")
    except Exception as e:
        print(f"❌ Detection system startup failed: {e}")


if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=start_detection_system, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=True)