# detector/detector_inout.py
import cv2, math, time, datetime, json
from ultralytics import YOLO
from detector.detector_base import DetectorBase
from db_utils import get_db_connection
from datetime import timedelta

# =========================================================
# 🔸 輔助工具類別與函式
# =========================================================
class GateRuntime:
    """用於儲存每個 gate 的即時狀態"""
    def __init__(self):
        self.last_side = {}      # 每個 tid 上一幀在哪一側
        self.flash_color = None  # 閃爍顏色
        self.flash_until = 0     # 顯示時間


def side_sign(a, b, p):
    """計算外積符號 (判斷點在門線哪一側)"""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def point_seg_dist(p, a, b):
    """計算點 p 到線段 AB 的距離"""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    projx, projy = ax + t * dx, ay + t * dy
    return math.hypot(px - projx, py - projy)


def unit_normal(a, b):
    """取得 AB 的法向量單位方向"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return (0, 0)
    nx, ny = -dy / length, dx / length
    return nx, ny


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
class InOutDetector(DetectorBase):
    def __init__(self, camera_id, camera_url):
        super().__init__(camera_id, camera_url)
        self.model = YOLO("models/yolo11n.pt") 
        self.gates = self._load_gates()
        self.rt = {}  # GateRuntime 暫存
        self.cap = cv2.VideoCapture(camera_url)
        self.FLASH_SEC = 0.5  # 閃爍時間
        self.conf = 0.5  

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
            gates.append({
                "id": g["gate_id"],
                "name": g["gate_name"],
                "a": (int(coords["A"][0] * frame_w), int(coords["A"][1] * frame_h)),
                "b": (int(coords["B"][0] * frame_w), int(coords["B"][1] * frame_h)),
                "in_dir": g["in_direction"],
                "start": self._format_time(g["start_time"], "00:00:00"),
                "end": self._format_time(g["end_time"], "23:59:59")
            })
        cur.close(); conn.close()
        print(f"[LOAD] Camera {self.camera_id} with in/out gates loaded.")
        return gates

    # =====================================================
    # 🔹 寫入事件到資料庫
    # =====================================================
    def _save_event(self, gate, state):
        now = datetime.datetime.now().time()
        fmt = "%H:%M:%S"

        start_t = datetime.datetime.strptime(gate["start"], fmt).time()
        end_t   = datetime.datetime.strptime(gate["end"], fmt).time()

        # 支援跨日區間
        if start_t <= end_t:
            in_active = start_t <= now <= end_t
        else:
            in_active = now >= start_t or now <= end_t

        level = "heavy" if in_active else "light"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO events (camera_id, gate_id, event_type, alert_level, timestamp)
            VALUES (%s, %s, %s, %s, NOW());
        """, (self.camera_id, gate["id"], "inout_cross", level))
        conn.commit()
        cur.close()
        conn.close()

    # =====================================================
    # 🔹 主執行迴圈
    # =====================================================
    def run(self):
        print(f"[INFO] InOutDetector started for camera {self.camera_id}")

        model = self.model
        COOLDOWN = 1.0        # 1 秒內不重複觸發
        MIN_NEAR = 30         # 人到門線的最大距離（像素）
        MIN_NORM_MOVE = 2     # 法向位移最小量（像素）
        last_evt = {}         # (gate_id, tid) → last_time

        def unit_normal(a, b):
            ax, ay = a; bx, by = b
            vx, vy = bx - ax, by - ay
            L = math.hypot(vx, vy) or 1.0
            return (-vy / L, vx / L)

        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            results = model.track(frame, persist=True, conf=self.conf, classes=[0], verbose=False)
            now = time.time()

            if results:
                r = results[0]
                if r.boxes is not None and len(r.boxes) > 0:
                    for b in r.boxes:
                        if b.id is None:
                            continue
                        tid = int(b.id.item())
                        x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                        foot = (int((x1 + x2) / 2), int(y2))  # 腳底點

                        # 顯示框與腳點
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.circle(frame, foot, 4, (0, 0, 255), -1)
                        cv2.putText(frame, f"ID {tid}", (x1, max(0, y1 - 6)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                        for g in self.gates:
                            if g["a"][0] < 0 or g["b"][0] < 0:
                                continue
                            rt = self.rt.setdefault(g["id"], GateRuntime())

                            curr_side = side_sign(g["a"], g["b"], foot)
                            prev_side = rt.last_side.get(tid, 0)

                            # 距離門線太遠 → 不檢查
                            dist = point_seg_dist(foot, g["a"], g["b"])
                            if dist > MIN_NEAR:
                                continue

                            # -------------------------
                            # 偵測跨越門線
                            # -------------------------
                            if prev_side != 0 and curr_side != 0 and prev_side != curr_side:
                                # 計算法向位移
                                nx, ny = unit_normal(g["a"], g["b"])
                                dx, dy = (foot[0] - rt.last_side.get(f"{tid}_x", foot[0]),
                                        foot[1] - rt.last_side.get(f"{tid}_y", foot[1]))
                                norm_move = abs(dx * nx + dy * ny)
                                rt.last_side[f"{tid}_x"] = foot[0]
                                rt.last_side[f"{tid}_y"] = foot[1]

                                if norm_move < MIN_NORM_MOVE:
                                    continue  # 抖動忽略

                                cross_dir = "A->B" if (prev_side < 0 and curr_side > 0) else "B->A"

                                # 使用資料庫 in_dir（1 表示 A→B 為內部，-1 表示 B→A）
                                inside_prev = is_inside(prev_side, g["in_dir"])
                                inside_curr = is_inside(curr_side, g["in_dir"])

                                if not inside_prev and inside_curr:
                                    state = "Entry"
                                elif inside_prev and not inside_curr:
                                    state = "Exit"
                                else:
                                    state = "Unknown"

                                # -------------------------
                                # 冷卻檢查
                                # -------------------------
                                if now - last_evt.get((g["id"], tid), 0) < COOLDOWN:
                                    continue
                                last_evt[(g["id"], tid)] = now

                                print(f"[CROSS] tid={tid}, gate={g['name']}, cross_dir={cross_dir}, "
                                    f"in_dir={g['in_dir']}, state={state}")

                                # -------------------------
                                # 顯示與記錄
                                # -------------------------
                                cv2.putText(frame, f"{cross_dir} ({state})", (x1, y2 + 20),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                            (0, 0, 255) if state == "Entry" else (0, 255, 0), 2)

                                # 寫入事件資料庫
                                self._save_event(g, state)

                                # 閃爍效果
                                rt.flash_color = (0, 0, 255) if state == "Entry" else (0, 255, 0)
                                rt.flash_until = now + self.FLASH_SEC

                            rt.last_side[tid] = curr_side

            # -------------------------
            # 畫門線與閃爍效果
            # -------------------------
            tnow = time.time()
            for g in self.gates:
                if g["a"][0] < 0 or g["b"][0] < 0:
                    continue
                rt = self.rt.setdefault(g["id"], GateRuntime())
                color = rt.flash_color if tnow < rt.flash_until else (255, 255, 255)
                cv2.line(frame, g["a"], g["b"], color, 2)
                cv2.putText(frame, g["name"], (g["a"][0] + 8, g["a"][1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # -------------------------
            # 顯示畫面（可選）
            # -------------------------
            self.last_frame = frame.copy()
            cv2.imshow(str(self.camera_id), frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break


    # =====================================================
    # 🔹 重新載入門線設定
    # =====================================================
    def reload_gates(self):
        self.gates = self._load_gates()
        print(f"[INFO] Reloaded gates for camera {self.camera_id}")
