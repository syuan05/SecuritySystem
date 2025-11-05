# detector/event_bus.py
import threading
from collections import defaultdict

class EventBus:
    """
    負責管理所有 camera 的事件狀態（即時畫面回饋用）
    - 每個 camera_id 維護：
        * active_gates : {gate_id: level / color}
        * active_people: {track_id: color / label}
        * people_count : 整體進出統計
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.gate_status = defaultdict(dict)
        self.people_status = defaultdict(dict)
        self.people_count = defaultdict(lambda: {"in": 0, "out": 0, "now": 0})

    # === InOut 模組用 ===
    def mark_gate_alert(self, camera_id, gate_id, level="light"):
        with self.lock:
            # 🔸 light 或 heavy 都先標記為紅色，但加上時間戳
            now = time.time()
            self.gate_status[camera_id][gate_id] = {
                "color": (0, 0, 255),  # 紅色
                "timestamp": now
            }



    # === People Flow 模組用 ===
    def update_people_count(self, camera_id, delta):
        with self.lock:
            data = self.people_count[camera_id]
            if delta > 0:
                data["in"] += 1
            else:
                data["out"] += 1
            data["now"] = data["in"] - data["out"]

    # === Drawer 讀取用 ===
    def get_state(self, camera_id):
        with self.lock:
            return {
                "gates": dict(self.gate_status[camera_id]),
                "people": dict(self.people_status[camera_id]),
                "count": dict(self.people_count[camera_id]),
            }

# 全域唯一事件總線
event_bus = EventBus()
