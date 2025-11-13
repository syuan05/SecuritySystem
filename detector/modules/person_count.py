# detector/detector_peopleflow.py
import cv2, math, time, datetime, json
from ultralytics import YOLO
from detector.detector_base import DetectorBase
from db_utils import get_db_connection
from detector.event_bus import event_bus
from datetime import timedelta
from detector.db_writer import person_count_writer
from detector.event_helper import make_event
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
    """以 A->B 的左法向量判斷點 p 位於 A 側(-1)、B 側(+1) 或 線上(0)。"""
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx - ax, by - ay
    nx, ny = -vy, vx
    s = (px - ax) * nx + (py - ay) * ny
    if s > 0:  return +1
    if s < 0:  return -1
    return 0


def point_seg_dist(p, a, b):
    """點到線段距離"""
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx-ax, by-ay
    if vx == 0 and vy == 0: return math.hypot(px-ax, py-ay)
    t = ((px-ax)*vx + (py-ay)*vy) / float(vx*vx + vy*vy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t*vx, ay + t*vy
    return math.hypot(px-cx, py-cy)


# =========================================================
# 🔸 主類別
# =========================================================
class PersonCountModule(DetectorBase):
    def __init__(self, camera_id):
        super().__init__(camera_id)
        self.model = pose_model
        self.gates = self._load_gates()
        self.rt = {}
        self.conf = 0.3

    # =====================================================
    # 🔹 載入門線設定
    # =====================================================
    def _load_gates(self):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT g.gate_id, g.gate_name, g.direction AS in_direction, g.polygon_json
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
                "type": "person"
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
        with pose_model_lock: 
            results = pose_model.track(frame, persist=True, conf=self.conf, imgsz=960, verbose=False)
        events = []
        draw_results = [] 
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

            foot = (int((x1 + x2) / 2), int(y2))
            if kps is not None and kps.shape[1] >= 17:
                left_ankle = kps[i][15]
                right_ankle = kps[i][16]
                if left_ankle[0] > 0 and right_ankle[0] > 0:
                    foot = (
                        int((left_ankle[0] + right_ankle[0]) / 2),
                        int((left_ankle[1] + right_ankle[1]) / 2),
                    )

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
                        gate_id=g["id"],
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
        """重新載入門線設定並立即更新"""
        self.gates = self._load_gates()  # ✅ 就跟 __init__ 時一樣
        print(f"[INFO] Reloaded in/out gates for camera {self.camera_id}")

        try:
            from detector.video_manager import manager_instance
            from detector.drawer import Drawer
            drawer = Drawer()

            worker_bundle = manager_instance.workers.get(self.camera_id)
            if not worker_bundle:
                print(f"[WARN] No worker found for camera {self.camera_id}, skip refresh.")
                return

            video_worker = worker_bundle["video"]
            frame = video_worker.get_frame()
            if frame is None:
                print(f"[WARN] No frame available for camera {self.camera_id}, skip refresh.")
                return

            # ✅ 重畫新的線條
            new_frame = drawer.draw_gates_only(frame, self.gates)
            with video_worker.lock:
                video_worker.frame = new_frame.copy()

            print(f"[REFRESH] Camera {self.camera_id}: gates redrawn after reload.")
        except Exception as e:
            import traceback
            print(f"[ERROR] Failed to refresh frame for camera {self.camera_id}: {e}")
            traceback.print_exc()
