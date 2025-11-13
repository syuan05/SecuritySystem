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
        with self.lock:
            now = time.time()
            self.gate_status[camera_id][gate_id] = {
                "color": (0, 0, 255),     # 紅色
                "flash_until": now + 2,   # 🔥 2秒後清除
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
        """
        所有模組事件進入此入口
        ⚠️ 不要在這裡更新統計 - 統計應該在模組內更新
        """
        with self.lock:
            self.last_events[camera_id].append(event)
            if len(self.last_events[camera_id]) > 30:
                self.last_events[camera_id] = self.last_events[camera_id][-30:]

            # ❌ 移除重複更新
            # if event["type"] == "person_count":
            #     direction = event["meta"].get("direction", "")
            #     gate_id = event["meta"].get("gate_id", 0)
            #     self.update_person_count(camera_id, gate_id, direction)

    # ======================================================
    # 🔹 Drawer 讀取用（非阻塞）
    # ======================================================
    def get_state(self, camera_id):
        with self.lock:
            gates = {}
            now = time.time()

            # 自動復原超時閃爍
            for gid, info in self.gate_status[camera_id].items():
                if info.get("flash_until", 0) < now:
                    gates[gid] = {"color": (0, 255, 0)}   # 綠色
                else:
                    gates[gid] = {"color": info.get("color", (0, 255, 0))}
            
            return {
                "gates": gates,
                "person_total": dict(self.person_count[camera_id]),
                "gate_counts": {
                    gid: dict(v) for gid, v in self.gate_counts[camera_id].items()
                },
                "events": list(self.last_events[camera_id])
            }
    
    def ensure_person_count_init(self, camera_id, gate_ids=None):
        """初始化統計數據結構"""
        with self.lock:
            # 初始化總量
            _ = self.person_count[camera_id]

            if gate_ids is None:
                return

            # 刪除不存在的 gate
            current = self.gate_counts[camera_id]
            to_delete = [gid for gid in current.keys() if gid not in gate_ids]
            for gid in to_delete:
                del current[gid]

            # 新增新 gate
            for gid in gate_ids:
                _ = current[gid]   # defaultdict → 自動建立 {"in":0,"out":0}

# 🔸 全域唯一 EventBus 實例
event_bus = EventBus()