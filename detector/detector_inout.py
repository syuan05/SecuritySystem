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
class InOutDetector(DetectorBase):
    def __init__(self, camera_id, camera_url):
        super().__init__(camera_id, camera_url)
        self.model = YOLO("models/yolo11n-pose.pt") 
        self.gates = self._load_gates()
        self.rt = {}  # GateRuntime 暫存
        self.cap = cv2.VideoCapture(camera_url)
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
        # print(f"[INFO] InOutDetector started for camera {self.camera_id}")

        model = self.model
        COOLDOWN = 0.5       # 1 秒內不重複觸發
        MIN_NEAR = 30        # 人到門線的最大距離（像素）
        MIN_NORM_MOVE = 0     # 法向位移最小量（像素）
        last_evt = {}         # (gate_id, tid) → last_time

        def unit_normal(a, b):
            ax, ay = a; bx, by = b
            vx, vy = bx - ax, by - ay
            L = math.hypot(vx, vy) or 1.0
            return (-vy / L, vx / L)

        while self.running:
            tnow = time.time()
            ok, frame = self.cap.read()
            if not ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            # results = model.track(frame, persist=True, conf=self.conf, classes=[0], verbose=False)
            results = model.track(frame, persist=True, conf=self.conf, imgsz=960, verbose=False)
            events = []
            now = time.time()

            if results:
                r = results[0]
                if r.boxes is not None and len(r.boxes) > 0:
                    boxes = r.boxes.xyxy.cpu().numpy()
                    ids = r.boxes.id.cpu().numpy() if r.boxes.id is not None else None
                    kps = r.keypoints.xy.cpu().numpy() if hasattr(r, "keypoints") else None

                    for i, box in enumerate(boxes):
                        x1, y1, x2, y2 = map(int, box.tolist())
                        tid = int(ids[i]) if ids is not None else i

                        # 預設腳底中點
                        foot = (int((x1 + x2) / 2), int(y2))

                        # 如果有關鍵點，就用雙腳踝中點
                        if kps is not None and kps.shape[1] >= 17:
                            left_ankle = kps[i][15]
                            right_ankle = kps[i][16]
                            if left_ankle[0] > 0 and right_ankle[0] > 0:
                                foot = (
                                    int((left_ankle[0] + right_ankle[0]) / 2),
                                    int((left_ankle[1] + right_ankle[1]) / 2),
                                )

                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.circle(frame, foot, 5, (0, 0, 255), -1)
                        # print("Has keypoints:", hasattr(r, "keypoints"), "Shape:", None if not hasattr(r, "keypoints") else r.keypoints.xy.shape)


                        for g in self.gates:
                            if g["a"][0] < 0 or g["b"][0] < 0:
                                continue
                            rt = self.rt.setdefault(g["id"], GateRuntime())

                            # --- 側邊判斷 ---
                            prev_side = rt.last_side.get(tid, 0)
                            curr_side = side_sign(g["a"], g["b"], foot)
                            if curr_side == 0:
                                curr_side = prev_side

                            # --- 距離門線太遠，不檢查 ---
                            dist = point_seg_dist(foot, g["a"], g["b"])
                            if dist > MIN_NEAR:
                                continue
                            
                            print(f"[CROSS] tid={tid}, gate={g['name']} "
                                    f"prev_side={prev_side}, curr_side={curr_side},dist={dist:.1f}")
                            # --- 偵測跨越門線 ---
                            if prev_side != 0 and curr_side != 0 and prev_side != curr_side:

                                # --- 冷卻檢查 ---
                                if tnow  - last_evt.get((g["id"], tid), 0) < COOLDOWN:
                                    continue
                                last_evt[(g["id"], tid)] = now

                                # --- 法向位移計算 ---
                                nx, ny = unit_normal(g["a"], g["b"])
                                dx, dy = (
                                    foot[0] - rt.last_side.get(f"{tid}_x", foot[0]),
                                    foot[1] - rt.last_side.get(f"{tid}_y", foot[1])
                                )
                                norm_move = abs(dx * nx + dy * ny)
                                rt.last_side[f"{tid}_x"] = foot[0]
                                rt.last_side[f"{tid}_y"] = foot[1]

                                if norm_move < MIN_NORM_MOVE:
                                    print(f"[DEBUG] norm_move={norm_move:.2f}, MIN_NORM_MOVE={MIN_NORM_MOVE}")
                                    continue  # 抖動忽略

                                # --- 判斷跨越方向 ---
                                cross_dir = "A->B" if (prev_side > 0 and curr_side < 0) else "B->A"

                                # --- 根據 in_dir 判斷 Entry / Exit ---
                                if (cross_dir == "A->B" and int(g["in_dir"]) == 1) or \
                                (cross_dir == "B->A" and int(g["in_dir"]) == -1):
                                    state = "Entry"
                                    color = (0, 255, 0)
                                    text = f"{cross_dir} ({state})"
                                else:
                                    state = "inout"
                                    color = (0, 0, 255)
                                    text = f"{cross_dir} (Invasion)"
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
                                    # 寫入資料庫
                                    conn = get_db_connection()
                                    cur = conn.cursor()
                                    cur.execute("""
                                        INSERT INTO events (camera_id, gate_id, event_type, alert_level, timestamp)
                                        VALUES (%s, %s, %s, %s, NOW());
                                    """, (self.camera_id, g["id"], "inout", level))
                                    cv2.putText(frame, text, (x1, y2 + 20),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                                    rt.flash_color = color
                                    rt.flash_until = now + self.FLASH_SEC
                                    conn.commit()
                                    cur.close()
                                    conn.close()

                                # --- 顯示在畫面上 ---
                                

                                # --- 閃爍效果 ---
                                
                            rt.last_side[tid] = curr_side

            # -------------------------
            # 畫門線與閃爍效果
            # -------------------------
            # tnow = time.time()
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
