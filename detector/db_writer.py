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
        conn.autocommit = True  # ✅ 強制自動提交，避免 transaction 堆積
        cur = conn.cursor()
        self.batch = []  # 🟢 批次暫存區

        while self.running:
            try:
                # 取出資料
                item = self.queue.get(timeout=1)
                self.batch.append(item)
                print(f"[DB] {self.__class__.__name__} got item ({len(self.batch)} pending)")

                # 當累積滿 10 筆就批次寫入
                if len(self.batch) >= 10:
                    for it in self.batch:
                        self._write(cur, it)
                    conn.commit()
                    print(f"[DB] {self.__class__.__name__} batch commit {len(self.batch)} OK")
                    self.batch.clear()

                    # ✅ 重建 cursor（釋放舊資源，避免卡死）
                    cur.close()
                    cur = conn.cursor()

            except queue.Empty:
                # 💤 queue 空時也 flush 一次
                if self.batch:
                    for it in self.batch:
                        self._write(cur, it)
                    conn.commit()
                    print(f"[DB] {self.__class__.__name__} flush remaining {len(self.batch)} OK (idle)")
                    self.batch.clear()

                    # ✅ 這兩行最關鍵！重建 cursor 防止 idle lock
                    cur.close()
                    cur = conn.cursor()
                continue

            except Exception as e:
                print(f"[{self.__class__.__name__}] Error:", e)

        # 🔚 thread 結束時關閉
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
        """將人流資料寫入資料庫（含 gate_id）"""
        dir_map = {"A->B": "in", "B->A": "out"}
        direction = dir_map.get(item.get("direction"), "in")

        try:
            cur.execute("""
                INSERT INTO people_flow (gate_id, camera_id, direction, timestamp)
                VALUES (%s, %s, %s, NOW());
            """, (
                item.get("gate_id"),
                item.get("camera_id"),
                direction
            ))
        except Exception as e:
            print(f"[PersonCountWriter] SQL Error: {e}")

    def add_flow(self, gate_id, camera_id, direction):
        """非同步新增一筆人流紀錄"""
        self.add(gate_id=gate_id, camera_id=camera_id, direction=direction)


# =====================================================
# 🔸 全域實例（模組統一使用）
# =====================================================
event_writer = EventWriter()
person_count_writer = PersonCountWriter()
