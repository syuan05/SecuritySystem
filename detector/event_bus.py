# detector/event_bus.py
import threading
import time
from collections import defaultdict

class EventBus:
    """
    管理所有 camera 的即時事件與統計資訊
    ----------------------------------------------------
    - gates: 各門線的警報顏色 / 時間戳
    - person_count: 全域進出統計 (in/out/now)
    - gate_counts: 每個 gate 的進出統計
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.gate_status = defaultdict(dict)
        self.person_count = defaultdict(lambda: {"in": 0, "out": 0, "now": 0})
        self.gate_counts = defaultdict(lambda: defaultdict(lambda: {"in": 0, "out": 0}))
        self.last_events = defaultdict(list)

    # ======================================================
    # 🔹 InOut 警報事件（紅線閃爍）
    # ======================================================
    def mark_gate_alert(self, camera_id, gate_id, level="light"):
        # if camera_id is None:
        #     print(f"[WARN] Skip alert: gate {gate_id} missing camera_id")
        #     return
        # with self.lock:
        #     now = time.time()
        #     color = (0, 0, 255) if level == "heavy" else (0, 255, 255)
        with self.lock:
            now = time.time()
            color = (0, 0, 255)
            self.gate_status[camera_id][gate_id] = {
                "color": color,
                "timestamp": now
            }

    # ======================================================
    # 🔹 人流統計更新（總量 + 各 Gate）
    # ======================================================
    def update_person_count(self, camera_id, gate_id, direction):
        with self.lock:
            # --- 全域統計 ---
            total = self.person_count[camera_id]
            if direction == "A->B":
                total["in"] += 1
            elif direction == "B->A":
                total["out"] += 1
            total["now"] = total["in"] - total["out"]

            # --- 各門線統計 ---
            gate_stat = self.gate_counts[camera_id][gate_id]
            if direction == "A->B":
                gate_stat["in"] += 1
            elif direction == "B->A":
                gate_stat["out"] += 1

    # ======================================================
    # 🔹 統一事件推送（給前端或 Drawer）
    # ======================================================
    def push_event(self, camera_id, event):
        """所有模組事件進入此入口"""
        with self.lock:
            self.last_events[camera_id].append(event)
            if len(self.last_events[camera_id]) > 30:
                self.last_events[camera_id] = self.last_events[camera_id][-30:]

            # 若是人流事件，更新統計
            if event["type"] == "person_count":
                direction = event["meta"].get("direction", "")
                gate_id = event["meta"].get("gate_id", 0)
                self.update_person_count(camera_id, gate_id, direction)

    # ======================================================
    # 🔹 Drawer 讀取用
    # ======================================================
    def get_state(self, camera_id):
        with self.lock:
            return {
                "gates": dict(self.gate_status[camera_id]),
                "person_total": dict(self.person_count[camera_id]),
                "gate_counts": {
                    gid: dict(v) for gid, v in self.gate_counts[camera_id].items()
                },
                "events": list(self.last_events[camera_id])
            }
    def ensure_person_count_init(self, camera_id, gate_ids=None):
        """確保即使剛啟動也有初始統計結構"""
        with self.lock:
            _ = self.person_count[camera_id]
            gates = self.gate_counts[camera_id]
            if gate_ids:
                for gid in gate_ids:
                    _ = gates[gid]  # 觸發 defaultdict 建立 {"in":0, "out":0}

# 🔸 全域唯一 EventBus 實例
event_bus = EventBus()
