# detector/detector_inout.py
import cv2, math, time, datetime, json
from ultralytics import YOLO
from detector.detector_base import DetectorBase
from db_utils import get_db_connection
from datetime import timedelta
from detector.db_writer import event_writer
from detector.event_bus import event_bus
from detector.event_helper import make_event
from detector.global_models import pose_model, pose_model_lock

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
    nx, ny = -vy, vx
    s = (px - ax) * nx + (py - ay) * ny
    if s > 0:  return +1
    if s < 0:  return -1
    return 0


def point_seg_dist(p, a, b):
    """計算點 p 到線段 AB 的距離"""
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
class InOutModule(DetectorBase):
    def __init__(self, camera_id):
        super().__init__(camera_id)
        self.model = pose_model
        self.gates = self._load_gates()
        self.rt = {}
        self.conf = 0.3

    # =====================================================
    # 🔹 將 MySQL TIME / timedelta 轉成 HH:MM:SS
    # =====================================================
    def _format_time(self, value, default):
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
                "start": self._format_time(g["start_time"], "00:00:00"),
                "end": self._format_time(g["end_time"], "23:59:59"),
                "type": "inout"
            })
            print(f"[LOAD] Gate {g['gate_name']} dir={in_dir} ({g['in_direction']})")
        cur.close(); conn.close()
        return gates

    # =====================================================
    # 🔹 主分析函式
    # =====================================================
    def process_frame(self, frame):
        model = self.model
        COOLDOWN = 0.5
        MIN_NEAR = 30
        last_evt = {}
        
        with pose_model_lock:
            results = self.model.track(frame, persist=True, conf=self.conf, imgsz=960, verbose=False)
        
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
                left_ankle, right_ankle = kps[i][15], kps[i][16]
                if left_ankle[0] > 0 and right_ankle[0] > 0:
                    foot = (
                        int((left_ankle[0] + right_ankle[0]) / 2),
                        int((left_ankle[1] + right_ankle[1]) / 2),
                    )

            draw_results.append({
                "bbox": (x1, y1, x2, y2),
                "foot": foot
            })

            # --- 以下是跨線事件檢查 ---
            for g in self.gates:
                rt = self.rt.setdefault(g["id"], GateRuntime())
                prev_side = rt.last_side.get(tid, 0)
                curr_side = side_sign(g["a"], g["b"], foot)
                if curr_side == 0:
                    curr_side = prev_side

                if point_seg_dist(foot, g["a"], g["b"]) > MIN_NEAR:
                    continue

                # --- 偵測跨線事件 ---
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

                    # 時間區段判定
                    now_t = datetime.datetime.now().time()
                    fmt = "%H:%M:%S"
                    start_t = datetime.datetime.strptime(g["start"], fmt).time()
                    end_t = datetime.datetime.strptime(g["end"], fmt).time()
                    in_active = (start_t <= now_t <= end_t) if start_t <= end_t else (now_t >= start_t or now_t <= end_t)
                    level = "heavy" if in_active else "light"

                    # 門線閃爍顏色 & 寫事件
                    event_bus.mark_gate_alert(self.camera_id, g["id"], level)
                    event_writer.add_event(
                        camera_id=self.camera_id,
                        gate_id=g["id"],
                        event_type="inout",
                        alert_level=level
                    )

                    # 建立統一事件格式
                    evt = make_event(
                        "inout",
                        camera_id=self.camera_id,
                        status=level,
                        gate_id=g["id"],
                        direction=cross_dir,
                        violation=is_violation,
                        tid=tid,
                        foot=foot
                    )
                    event_bus.push_event(self.camera_id, evt)
                    events.append(evt)

                rt.last_side[tid] = curr_side

        self.last_events = events
        return draw_results

    def run(self, frame):
        return self.process_frame(frame)

    def analyze(self, frame):
        return self.process_frame(frame)

    # =====================================================
    # 🔹 重新載入門線設定（✅ 修正為非阻塞方式）
    # =====================================================
    def reload_gates(self):
        """
        重新載入門線設定並請求畫面刷新
        ✅ 使用非阻塞方式通知 VideoWorker 更新
        """
        self.gates = self._load_gates()
        print(f"[INFO] Reloaded {len(self.gates)} in/out gates for camera {self.camera_id}")

        # ✅ 通知 VideoWorker 下一幀重繪（非阻塞）
        try:
            from detector.video_manager import manager_instance
            worker_bundle = manager_instance.workers.get(self.camera_id)
            if worker_bundle:
                video_worker = worker_bundle["video"]
                video_worker.request_reload_refresh()
            else:
                print(f"[WARN] No worker found for camera {self.camera_id}")
        except Exception as e:
            print(f"[ERROR] Failed to request reload refresh: {e}")