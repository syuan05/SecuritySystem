# app.py
from flask import Flask, render_template, jsonify, request, Response
import mysql.connector
from dotenv import load_dotenv
import os
import json
import cv2


# ====== 載入 .env ======
load_dotenv()

app = Flask(__name__)

# ====== 從環境變數讀取資料庫設定 ======
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "ssl_disabled": False
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# ====== 頁面 ======
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/camera.html')
def camera_page():
    return render_template('camera.html')

@app.route('/video_feed/<int:camera_id>')

@app.route("/video_feed/<int:camera_id>")
def video_feed(camera_id):
    """從資料庫撈出影片連結，推流到前端"""
    # === 1️⃣ 從資料庫取得 camera_url ===
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT camera_url FROM cameras WHERE camera_id=%s;", (camera_id,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        return "Camera not found", 404

    camera_url = row["camera_url"]
    print(f"[INFO] 開啟串流：Camera {camera_id} → {camera_url}")

    # === 2️⃣ 讀取影片/RTSP ===
    cap = cv2.VideoCapture(camera_url)
    if not cap.isOpened():
        return f"無法開啟串流：{camera_url}", 500

    # === 3️⃣ 推流產生器 ===
    def generate():
        while True:
            ok, frame = cap.read()
            if not ok:
                # 如果是影片檔案 → 重新循環播放
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            # （你可以在這裡加 YOLO 偵測、畫框、門線等）
            cv2.putText(frame, f"Camera {camera_id}", (40, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # 轉成 JPEG bytes
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    # === 4️⃣ 回傳 Response ===
    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ====== API ======
@app.route('/api/cameras')
def get_cameras():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT camera_id, camera_name, camera_url FROM cameras ORDER BY camera_id;")
    data = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(data)

@app.route('/api/camera/<int:camera_id>')
def get_camera(camera_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 讀取 camera 基本資料
    cur.execute("""
        SELECT camera_id, camera_name, camera_url,
               falling_detection_mode, climbing_detection_mode
        FROM cameras
        WHERE camera_id = %s;
    """, (camera_id,))
    cam = cur.fetchone()

    if not cam:
        cur.close(); conn.close()
        return jsonify({"error": "Camera not found"}), 404

    # 讀取該攝影機的 schedule
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
        """安全格式化 MySQL TIME 欄位（timedelta → HH:MM）"""
        if t is None:
            return "--:--"
        if isinstance(t, str):
            return t[:5]
        if hasattr(t, "seconds"):
            total_seconds = int(t.total_seconds())
            h = (total_seconds // 3600) % 24
            m = (total_seconds % 3600) // 60
            return f"{h:02d}:{m:02d}"
        return str(t)

    cam["schedules"] = {
        s["function_type"]: {
            "start": fmt_time(s["start_time"]),
            "end": fmt_time(s["end_time"])
        } for s in schedules
    }

    return jsonify(cam)



@app.route('/api/fence/<string:type>')
def get_fence(type):
    cam_id = request.args.get("camera_id")
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    config = {
        "inout": {"table": "gates", "mode": "in_out_control_mode", "func": "in_out_control"},
        "intrusion": {"table": "fences", "mode": "intrusion_mode", "func": "intrusion"},
        "crowd": {"table": "zones", "mode": "crowd_count_mode", "func": "crowd_count"},
        "people": {"table": "zones", "mode": "people_detect_mode", "func": "people_detect"}
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
def add_fence(type):
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    if type == "inout":
        table, func_type, mode_col = "gates", "in_out_control", "in_out_control_mode"
    elif type == "intrusion":
        table, func_type, mode_col = "fences", "intrusion", "intrusion_mode"
    elif type == "crowd":
        table, func_type, mode_col = "zones", "crowd_count", "crowd_count_mode"
    elif type == "people":
        table, func_type, mode_col = "zones", "people_detect", "people_detect_mode"
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
            data["direction"]
        ))
        obj_id = cur.lastrowid

        # === Step 2. 新增對應的 schedule ===
        cur.execute("""
            INSERT INTO func_schedules (camera_id, gate_id, function_type, start_time, end_time, is_active)
            VALUES (%s, %s, %s, %s, %s, 1);
        """, (data["camera_id"], obj_id, func_type, data["start_time"], data["end_time"]))

        conn.commit()
        return jsonify({"status": "ok", "id": obj_id})

    except Exception as e:
        conn.rollback()
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
    

if __name__ == '__main__':
    app.run(debug=True)
