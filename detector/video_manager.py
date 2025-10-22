# detector/video_manager.py
# 所有攝影機對應的偵測執行緒
import threading
from db_utils import get_db_connection
from detector.detector_inout import InOutDetector


class VideoManager:
    def __init__(self):
        # camera_id → worker 對照表（方便查找）
        self.workers = {}

    def load_all_cameras(self):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT camera_id, camera_url FROM cameras;")
        cameras = cur.fetchall()

        print(f"[DEBUG] Cameras found: {len(cameras)}")

        for cam in cameras:
            camera_id = cam["camera_id"]
            camera_url = cam["camera_url"]

            from detector.detector_inout import InOutDetector
            worker = InOutDetector(camera_id, camera_url)
            self.workers[camera_id] = worker

            # cur.execute("""
            #     SELECT COUNT(*) AS cnt
            #     FROM gates
            #     WHERE camera_id = %s AND in_out_control_mode = 1;
            # """, (camera_id,))
            # cnt = cur.fetchone()["cnt"]
            # print(f"[DEBUG] Camera {camera_id} gate count = {cnt}")

        cur.close()
        conn.close()
        print(f"[DEBUG] Loaded {len(self.workers)} camera workers.")


    def start_all(self):
        """為所有攝影機啟動 YOLO 偵測執行緒"""
        for cid, w in self.workers.items():
            t = threading.Thread(target=w.run, daemon=True)
            t.start()
            print(f"[INFO] Started InOutDetector for Camera {cid}")

    def stop_all(self):
        """停止所有偵測執行緒"""
        for w in self.workers.values():
            w.stop()

    def get_worker(self, camera_id):
        """提供外部 API 查找對應攝影機的偵測執行緒"""
        return self.workers.get(camera_id)

    def reload_worker_gates(self, camera_id):
        """由 Flask 呼叫時，重新載入指定攝影機的門線設定"""
        worker = self.get_worker(camera_id)
        if worker:
            worker.reload_gates()
            print(f"[INFO] Reloaded gates for camera {camera_id}")
            return True
        return False


# 全域唯一管理器實例
manager_instance = VideoManager()
