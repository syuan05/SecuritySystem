# detector/detector_inout.py
import cv2, math, time, datetime, json
from ultralytics import YOLO
from detector.detector_base import DetectorBase
from db_utils import get_db_connection
from datetime import timedelta
from detector.db_writer import db_writer
from detector.event_bus import event_bus

# =========================================================
# 🔸 輔助工具類別與函式
# =========================================================
class GateRuntime:
    """用於儲存每個 gate 的即時狀態"""
    def __init__(self):
        self.last_side = {}      # 每個 tid 上一幀在哪一側
        self.flash_color = None  # 閃爍顏色
        self.flash_until = 0     # 顯示時間


def side_sign(a, b, p) -> int:
    """以 A->B 的左法向量判斷點 p 位於 A 側(-1)、B 側(+1) 或 線上(0)。"""
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx - ax, by - ay
    nx, ny = -vy, vx  # 左法向（未正規化也可以）
    s = (px - ax) * nx + (py - ay) * ny
    if s > 0:  return +1   # B 側（左側）
    if s < 0:  return -1   # A 側（右側）
    return 0               # 線上

def point_seg_dist(p, a, b):
    """計算點 p 到線段 AB 的距離"""
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx-ax, by-ay
    if vx == 0 and vy == 0: return math.hypot(px-ax, py-ay)
    t = ((px-ax)*vx + (py-ay)*vy) / float(vx*vx + vy*vy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t*vx, ay + t*vy
    return math.hypot(px-cx, py-cy)



def is_inside(side_val, in_dir):
    """根據門線方向與外積符號判定是否在內側"""
    # in_dir: +1 表示 A→B 方向為內部，-1 表示相反
    if in_dir == 1:
        return side_val > 0
    else:
        return side_val < 0


# =========================================================
# 🔸 主類別
# =========================================================
class InOutModule(DetectorBase):
    def __init__(self, camera_id):
        super().__init__(camera_id)
        self.model = YOLO("models/yolo11n-pose.pt") 
        self.gates = self._load_gates()
        self.rt = {}  # GateRuntime 暫存
        self.FLASH_SEC = 1.5  # 閃爍時間
        self.conf = 0.3  

    # =====================================================
    # 🔹 將 MySQL TIME / timedelta 轉成 HH:MM:SS
    # =====================================================
    def _format_time(self, value, default):
        if value is None:
            return default
        if isinstance(value, timedelta):
            total_seconds = int(value.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        try:
            return value.strftime("%H:%M:%S")
        except Exception:
            return default

    # =====================================================
    # 🔹 從資料庫載入門線設定
    # =====================================================
    def _load_gates(self):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT g.gate_id, g.gate_name, g.direction AS in_direction, g.polygon_json,
                   s.start_time, s.end_time
            FROM gates g
            LEFT JOIN func_schedules s
              ON g.gate_id=s.gate_id AND s.function_type='in_out_control' AND s.is_active=1
            WHERE g.camera_id=%s AND g.in_out_control_mode=1;
        """, (self.camera_id,))
        gates = []
        for g in cur.fetchall():
            coords = json.loads(g["polygon_json"])
            frame_h, frame_w = 720, 1280
            # ---- 安全轉型方向 ----
            dir_val = str(g["in_direction"]).strip().upper()

            if dir_val in ["1", "ATOB", "A-B", "AB"]:
                in_dir = 1       # A→B 為內側
            elif dir_val in ["-1", "BTOA", "BA"]:
                in_dir = -1      # B→A 為內側
            else:
                in_dir = 1       # 預設
            # ---------------------

            gates.append({
                "id": g["gate_id"],
                "name": g["gate_name"],
                "a": (int(coords["A"][0] * frame_w), int(coords["A"][1] * frame_h)),
                "b": (int(coords["B"][0] * frame_w), int(coords["B"][1] * frame_h)),
                "in_dir": in_dir,
                "start": self._format_time(g["start_time"], "00:00:00"),
                "end": self._format_time(g["end_time"], "23:59:59")
            })
            print(f"[LOAD] Gate {g['gate_name']} dir={in_dir} ({g['in_direction']})")
        cur.close(); conn.close()
        # print(f"[LOAD] Camera {self.camera_id} with in/out gates loaded.")
        return gates

    # =====================================================
    # 🔹 寫入事件到資料庫
    # =====================================================
    # def _save_event(self, gate, state):
    #     from detector.db_writer import db_writer
    #     now = datetime.datetime.now().time()
    #     fmt = "%H:%M:%S"

    #     start_t = datetime.datetime.strptime(gate["start"], fmt).time()
    #     end_t   = datetime.datetime.strptime(gate["end"], fmt).time()

    #     # 支援跨日區間
    #     if start_t <= end_t:
    #         in_active = start_t <= now <= end_t
    #     else:
    #         in_active = now >= start_t or now <= end_t

    #     level = "heavy" if in_active else "light"

    #     db_writer.add_event(
    #         camera_id=self.camera_id,
    #         gate_id=g["id"],
    #         event_type="inout",
    #         alert_level=level
    #     )

    def run(self, frame):
        """滿足抽象基底的 run 方法，可直接用 process_frame"""
        self.process_frame(frame)
        return getattr(self, "last_events", [])

    # =====================================================
    # 🔹 主執行迴圈
    # =====================================================
    def process_frame(self, frame):
        model = self.model
        COOLDOWN = 0.5
        MIN_NEAR = 30
        MIN_NORM_MOVE = 0
        last_evt = {}

        results = model.track(frame, persist=True, conf=self.conf, imgsz=960, verbose=False)
        events = []
        if results:
            r = results[0]
            if r.boxes is not None and len(r.boxes) > 0:
                boxes = r.boxes.xyxy.cpu().numpy()
                ids = r.boxes.id.cpu().numpy() if r.boxes.id is not None else None
                kps = r.keypoints.xy.cpu().numpy() if hasattr(r, "keypoints") else None
                for i, box in enumerate(boxes):
                    x1, y1, x2, y2 = map(int, box.tolist())
                    tid = int(ids[i]) if ids is not None else i
                    # 預設腳底
                    foot = (int((x1 + x2) / 2), int(y2))
                    if kps is not None and kps.shape[1] >= 17:
                        left_ankle = kps[i][15]
                        right_ankle = kps[i][16]
                        if left_ankle[0] > 0 and right_ankle[0] > 0:
                            foot = (
                                int((left_ankle[0] + right_ankle[0]) / 2),
                                int((left_ankle[1] + right_ankle[1]) / 2),
                            )
                    events.append({
                        "type": "person",
                        "tid": tid,
                        "bbox": [x1, y1, x2, y2],
                        "foot": foot
                    })
                    # 檢查所有 gates
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
                            is_violation = not (
                                (cross_dir == "A->B" and g["in_dir"] == 1) or
                                (cross_dir == "B->A" and g["in_dir"] == -1)
                            )

                            now_t = datetime.datetime.now().time()
                            fmt = "%H:%M:%S"
                            start_t = datetime.datetime.strptime(g["start"], fmt).time()
                            end_t = datetime.datetime.strptime(g["end"], fmt).time()
                            if start_t <= end_t:
                                in_active = start_t <= now_t <= end_t
                            else:
                                in_active = now_t >= start_t or now_t <= end_t
                            level = "heavy" if in_active else "light"

                            event_bus.mark_gate_alert(self.camera_id, g["id"], level)

                            # 人流計數更新 (+1 表示進入，-1 表示離開)
                            if cross_dir == "A->B":
                                event_bus.update_people_count(self.camera_id, +1)
                            else:
                                event_bus.update_people_count(self.camera_id, -1)
                            # ✅ 非同步寫入資料庫
                            # self._save_event(g, state="inout")

                            # print(f"[EVENT]")
                            db_writer.add_event(
                                camera_id=self.camera_id,
                                gate_id=g["id"],
                                event_type="inout",
                                alert_level=level
                            )
                            # === 回傳事件 ===
                            events.append({
                                "type": "inout",
                                "gate_id": g["id"],
                                "tid": tid,
                                "violation": is_violation,
                                "level": level,
                                "cross_dir": cross_dir,
                                "foot": foot,
                                "bbox": [x1, y1, x2, y2],
                                "timestamp": datetime.datetime.now().isoformat()
                            })

                        rt.last_side[tid] = curr_side

        self.last_events = events

    def analyze(self, frame):
        self.process_frame(frame)
        return getattr(self, "last_events", [])


    # =====================================================
    # 🔹 重新載入門線設定
    # =====================================================
    def reload_gates(self):
        self.gates = self._load_gates()
        print(f"[INFO] Reloaded gates for camera {self.camera_id}")
