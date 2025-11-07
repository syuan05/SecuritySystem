# detector/detector_peopleflow.py
import cv2, math, time, datetime, json
from ultralytics import YOLO
from detector.detector_base import DetectorBase
from db_utils import get_db_connection
from detector.event_bus import event_bus
from datetime import timedelta
from detector.db_writer import person_count_writer
from detector.event_helper import make_event
from detector.event_bus import event_bus
from detector.global_models import pose_model, pose_model_lock

# =========================================================
# 🔸 輔助工具
# =========================================================
class GateRuntime:
    """儲存每個 gate 的即時狀態"""
    def __init__(self):
        self.last_side = {}
        self.flash_until = 0


def side_sign(a, b, p):
    """判定點 p 在 A->B 的哪一側"""
    ax, ay = a; bx, by = b; px, py = p
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def point_seg_dist(p, a, b):
    """點到線段距離"""
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx-ax, by-ay
    if vx == 0 and vy == 0: return math.hypot(px-ax, py-ay)
    t = ((px-ax)*vx + (py-ay)*vy) / float(vx*vx + vy*vy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t*vx, ay + t*vy
    return math.hypot(px-cx, py-cy)


def format_time(value, default):
    """MySQL TIME / timedelta → HH:MM:SS"""
    if value is None:
        return default
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        h, m = divmod(total_seconds, 3600)
        m, s = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    try:
        return value.strftime("%H:%M:%S")
    except Exception:
        return default


# =========================================================
# 🔸 主類別
# =========================================================
class PersonCountModule(DetectorBase):
    def __init__(self, camera_id):
        super().__init__(camera_id)
        self.model = pose_model
        self.gates = self._load_gates()
        self.rt = {}
        self.conf = 0.4
        self.FLASH_SEC = 1.0

    # =====================================================
    # 🔹 載入門線設定
    # =====================================================
    def _load_gates(self):
        print("[DEBUG] load gates for camera:", self.camera_id)
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT DISTINCT g.gate_id, g.gate_name, g.direction AS in_direction, g.polygon_json
            FROM gates g
            LEFT JOIN func_schedules s
              ON g.gate_id=s.gate_id AND s.function_type='person_count' AND s.is_active=1
            WHERE g.camera_id=%s AND g.person_count_mode=1;
        """, (self.camera_id,))
        gates = []
        for g in cur.fetchall():
            coords = json.loads(g["polygon_json"])
            frame_h, frame_w = 720, 1280

            dir_val = str(g["in_direction"]).strip().upper()
            if dir_val in ["1", "ATOB", "A-B", "AB"]:
                in_dir = 1
            elif dir_val in ["-1", "BTOA", "BA"]:
                in_dir = -1
            else:
                in_dir = 1

            gates.append({
                "id": g["gate_id"],
                "name": g["gate_name"],
                "camera_id": self.camera_id,  
                "a": (int(coords["A"][0] * frame_w), int(coords["A"][1] * frame_h)),
                "b": (int(coords["B"][0] * frame_w), int(coords["B"][1] * frame_h)),
                "in_dir": in_dir,
            })
            print(f"[LOAD] Gate {g['gate_name']} dir={in_dir} ({g['in_direction']})")
        cur.close(); conn.close()
        return gates

    # =====================================================
    # 🔹 主分析函式
    # =====================================================
    from detector.drawer import Drawer
    def process_frame(self, frame):
        COOLDOWN = 0.5
        MIN_NEAR = 30
        last_evt = {}
        with pose_model_lock:  # 🔒 保證單一推論執行
            results = pose_model.track(frame, persist=True, conf=self.conf, imgsz=960, verbose=False)
        events = []
        draw_results = []  # ✅ 給 Drawer 畫用
        if not results:
            return []

        r = results[0]
        if not (r.boxes and len(r.boxes) > 0):
            return []

        boxes = r.boxes.xyxy.cpu().numpy()
        ids = r.boxes.id.cpu().numpy() if r.boxes.id is not None else None
        kps = r.keypoints.xy.cpu().numpy() if hasattr(r, "keypoints") else None

        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = map(int, box.tolist())
            tid = int(ids[i]) if ids is not None else i

            # ⚙️ 取腳底點
            foot = (int((x1 + x2) / 2), int(y2))
            if kps is not None and kps.shape[1] >= 17:
                left_ankle = kps[i][15]
                right_ankle = kps[i][16]
                if left_ankle[0] > 0 and right_ankle[0] > 0:
                    foot = (
                        int((left_ankle[0] + right_ankle[0]) / 2),
                        int((left_ankle[1] + right_ankle[1]) / 2),
                    )

            # ✅ 每幀都記錄 bbox/foot 給 Drawer 畫
            draw_results.append({
                "bbox": (x1, y1, x2, y2),
                "foot": foot
            })

            # --- 檢查每個 Gate 是否跨線 ---
            for g in self.gates:
                rt = self.rt.setdefault(g["id"], GateRuntime())
                prev_side = rt.last_side.get(tid, 0)
                curr_side = side_sign(g["a"], g["b"], foot)
                if curr_side == 0:
                    curr_side = prev_side

                dist = point_seg_dist(foot, g["a"], g["b"])
                if dist > MIN_NEAR:
                    continue

                if prev_side != 0 and curr_side != 0 and prev_side != curr_side:
                    now = time.time()
                    if now - last_evt.get((g["id"], tid), 0) < COOLDOWN:
                        continue
                    last_evt[(g["id"], tid)] = now

                    cross_dir = "A->B" if (prev_side > 0 and curr_side < 0) else "B->A"

                    # --- 時間區間 ---
                    now_t = datetime.datetime.now().time()
                    fmt = "%H:%M:%S"
                    now_t = datetime.datetime.now().time()
                    start_t = datetime.time(0, 0, 0)
                    end_t = datetime.time(23, 59, 59)
                    level = "heavy"  # 固定全時啟用

                    # --- 更新 event bus / 統計 ---
                    event_bus.update_person_count(self.camera_id, g["id"], cross_dir)

                    # --- 寫入資料庫 ---
                    person_count_writer.add_flow(
                        camera_id=self.camera_id,
                        direction=cross_dir
                    )

                    # --- 推事件 ---
                    evt = make_event(
                        "person_count",
                        camera_id=self.camera_id,
                        status="active",
                        gate_id=g["id"],
                        direction=cross_dir,
                        tid=tid,
                        foot=foot
                    )
                    event_bus.push_event(self.camera_id, evt)
                    events.append(evt)

                rt.last_side[tid] = curr_side

        self.last_events = events
        return draw_results  # ✅ 每幀都回傳偵測框



    def run(self, frame):
        return self.process_frame(frame)

    def analyze(self, frame):
        return self.process_frame(frame)

    def reload_gates(self):
        self.gates = self._load_gates()
        print(f"[INFO] Reloaded people-flow gates for camera {self.camera_id}")
