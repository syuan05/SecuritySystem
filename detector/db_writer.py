# detector/db_writer.py
import threading
import queue
import time
from db_utils import get_db_connection

# =====================================================
# 🔹 通用基底類別
# =====================================================
class BaseWriter:
    def __init__(self):
        self.queue = queue.Queue()
        self.running = True
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _worker(self):
        conn = get_db_connection()
        cur = conn.cursor()
        self.batch = []  # 🟢 批次暫存區

        while self.running:
            try:
                item = self.queue.get(timeout=1)
                self.batch.append(item)
                print(f"[DB] {self.__class__.__name__} got item ({len(self.batch)} pending)")

                # 當累積 10 筆（或更多）再一起寫入
                if len(self.batch) >= 10:
                    t0 = time.time()
                    for it in self.batch:
                        self._write(cur, it)
                    conn.commit()
                    print(f"[DB] {self.__class__.__name__} batch commit {len(self.batch)} OK ({time.time()-t0:.3f}s)")
                    self.batch.clear()

            except queue.Empty:
                # 若沒資料但有尚未 commit 的批次，也可視情況寫入
                if self.batch:
                    for it in self.batch:
                        self._write(cur, it)
                    conn.commit()
                    print(f"[DB] {self.__class__.__name__} flush remaining {len(self.batch)} OK (idle)")
                    self.batch.clear()
                continue
            except Exception as e:
                print(f"[{self.__class__.__name__}] Error:", e)

        cur.close()
        conn.close()

    def stop(self):
        self.running = False

    def add(self, **kwargs):
        self.queue.put(kwargs)

    def _write(self, cur, item):
        """子類別覆寫此方法"""
        raise NotImplementedError


# =====================================================
# 🔸 寫入 events 表
# =====================================================
class EventWriter(BaseWriter):
    def _write(self, cur, item):
        cur.execute("""
            INSERT INTO events (camera_id, gate_id, event_type, alert_level, timestamp)
            VALUES (%s, %s, %s, %s, NOW());
        """, (item["camera_id"], item["gate_id"], item["event_type"], item["alert_level"]))

    def add_event(self, camera_id, gate_id, event_type, alert_level):
        self.add(camera_id=camera_id, gate_id=gate_id,
                 event_type=event_type, alert_level=alert_level)


# =====================================================
# 🔸 寫入 people_count 表
# =====================================================
class PersonCountWriter(BaseWriter):
    def _write(self, cur, item):
        # 將 "A->B" / "B->A" 轉成 enum 允許值 "in" / "out"
        dir_map = {
            "A->B": "in",
            "B->A": "out"
        }
        direction = dir_map.get(item["direction"], "in")  # 預設 in
        cur.execute("""
            INSERT INTO people_flow (camera_id, direction, timestamp)
            VALUES (%s, %s, NOW());
        """, (item["camera_id"], direction))
    def add_flow(self, camera_id, direction):
        """非同步新增一筆人流紀錄"""
        self.add(camera_id=camera_id, direction=direction)

# =====================================================
# 🔸 全域實例（模組統一使用）
# =====================================================
event_writer = EventWriter()
person_count_writer = PersonCountWriter()
