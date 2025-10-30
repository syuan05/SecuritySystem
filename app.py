# app.py
from flask import Flask, render_template, jsonify, request, Response
import mysql.connector
from dotenv import load_dotenv
import os
import json
import cv2
from detector.video_manager import VideoManager
import threading
from db_utils import get_db_connection
import time

manager = VideoManager()
load_dotenv()
app = Flask(__name__)


# ====== 頁面 ======
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/camera.html')
def camera_page():
    return render_template('camera.html')

@app.route('/history.html')
def history_page():
    return render_template('history.html')

@app.route("/video_feed/<int:camera_id>")
def video_feed(camera_id):
    def generate():
        while True:
            # ✅ 改這裡：遍歷 .values()
            for worker in manager.workers.values():
                if worker.camera_id == camera_id:
                    if hasattr(worker, "last_frame") and worker.last_frame is not None:
                        _, buffer = cv2.imencode(".jpg", worker.last_frame)
                        frame = buffer.tobytes()
                        yield (b"--frame\r\n"
                               b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
                    break
            time.sleep(0.03)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")



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
        "intrusion": {"table": "gates", "mode": "intrusion_mode", "func": "intrusion"},
        "crowd": {"table": "gates", "mode": "person_count_mode", "func": "crowd_count"},
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
def add_fence(type):
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    if type == "inout":
        table, func_type, mode_col = "gates", "in_out_control", "in_out_control_mode"
    elif type == "intrusion":
        table, func_type, mode_col = "gates", "intrusion", "intrusion_mode"
    elif type == "crowd":
        table, func_type, mode_col = "gates", "crowd_count", "person_count_mode"
    elif type == "people":
        table, func_type, mode_col = "gates", "people_detect", "people_detect_mode"
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
    
@app.route("/api/reload_gates/<int:camera_id>", methods=["POST"])
def reload_gates(camera_id):
    from detector.video_manager import manager_instance
    worker = manager.workers.get(camera_id)
    if worker:
        worker.reload_gates()
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "worker not found"}), 404

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

    # 動態加條件
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


def start_detection_system():
    manager.load_all_cameras()   # 從資料庫撈出所有攝影機
    manager.start_all()          # 為每支攝影機啟動 YOLO 偵測 worker


if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":  # 只在重載後主進程啟動時執行
        threading.Thread(target=start_detection_system, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=True)
