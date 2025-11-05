# detector/db_writer.py
import threading
import queue
import time
from db_utils import get_db_connection

class DBWriter:
    def __init__(self):
        self.queue = queue.Queue()
        self.running = True
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _worker(self):
        conn = get_db_connection()
        cur = conn.cursor()
        while self.running:
            batch = []
            try:
                # 一次取多筆
                for _ in range(10):
                    batch.append(self.queue.get(timeout=1))
            except queue.Empty:
                pass

            for item in batch:
                try:
                    cur.execute("""
                        INSERT INTO events (camera_id, gate_id, event_type, alert_level, timestamp)
                        VALUES (%s, %s, %s, %s, NOW());
                    """, (item["camera_id"], item["gate_id"], item["event_type"], item["alert_level"]))
                except Exception as e:
                    print("[DBWriter] Error:", e)
            conn.commit()


    def add_event(self, camera_id, gate_id, event_type, alert_level):
        """放入佇列（供偵測模組呼叫）"""
        self.queue.put({
            "camera_id": camera_id,
            "gate_id": gate_id,
            "event_type": event_type,
            "alert_level": alert_level
        })

# 🔹 全域唯一 DBWriter 實例
db_writer = DBWriter()
