import threading
import time
import cv2
from detector.video_worker import VideoWorker
from detector.module_manager import ModuleManager

class VideoManager:
    """
    管理所有攝影機與模組：
    --------------------------------------------------
    - 每支攝影機：VideoWorker + ModuleManager
    - VideoWorker 定時讀取影像，並呼叫 module_manager.process()
    - 不重複開啟 thread、不重複跑 YOLO
    """

    def __init__(self):
        self.workers = {}

    # ==========================================================
    # 🔹 初始化所有攝影機
    # ==========================================================
    def load_all_cameras(self):
        from db_utils import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT camera_id, camera_url FROM cameras;")
        cameras = cur.fetchall()
        cur.close(); conn.close()

        print(f"[INIT] Loaded {len(cameras)} cameras from database.")

        for cam in cameras:
            cid, url = cam["camera_id"], cam["camera_url"]
            video_worker = VideoWorker(cid, url)
            module_manager = ModuleManager(cid, url)

            # ✅ 用 module_manager=module_manager 捕捉當前的物件
            def callback(frame, camera_id=cid, module_manager=module_manager):
                drawn_frame = module_manager.process(frame, camera_id)
                return drawn_frame

            video_worker.callback = callback
            video_worker.start()

            self.workers[cid] = {
                "video": video_worker,
                "modules": module_manager,
                "running": True
            }

            print(f"[INFO] Started detection pipeline for camera {cid}")

    # ==========================================================
    # 🔹 取得最新畫面（供 Flask /video_feed 使用）
    # ==========================================================
    def get_last_frame(self, camera_id):
        bundle = self.workers.get(camera_id)
        if not bundle:
            return None
        return bundle["video"].get_frame()

    def get_raw_frame(self, camera_id):
        bundle = self.workers.get(camera_id)
        if not bundle:
            return None
        return bundle["video"].get_raw_frame()   # ← ✔ 正確

    # ==========================================================
    # 🔹 熱重載門線設定（更新模組 + 通知刷新）
    # ==========================================================
    def reload_gates(self, camera_id=None):
        if camera_id:
            self._reload_single(camera_id)
        else:
            for cid in self.workers.keys():
                self._reload_single(cid)

    def _reload_single(self, camera_id):
        worker_bundle = self.workers.get(camera_id)
        if not worker_bundle:
            print(f"[WARN] Reload skipped: camera {camera_id} not found.")
            return

        old_video = worker_bundle["video"]
        old_url = old_video.camera_url

        print(f"[RELOAD] Camera {camera_id}: rebuilding ModuleManager...")

        # 1️⃣ 重新建立全新的 ModuleManager（會重新讀 DB 的新版 gates）
        new_manager = ModuleManager(camera_id, old_url)
        worker_bundle["modules"] = new_manager

        # 2️⃣ 更新 callback，使 VideoWorker 使用新的 module_manager
        def callback(frame, camera_id=camera_id, module_manager=new_manager):
            return module_manager.process(frame, camera_id)

        old_video.callback = callback

        # 3️⃣ 要求 VideoWorker 下一幀強制重畫
        old_video.request_reload_refresh()

        print(f"[RELOAD] Camera {camera_id}: ModuleManager fully reloaded AND redraw requested.")


    # ==========================================================
    # 🔹 停止所有攝影機
    # ==========================================================
    def stop_all(self):
        for cid, w in self.workers.items():
            w["running"] = False
            w["video"].stop()
            print(f"[STOP] Camera {cid} stopped.")

# ==============================================================
# 🔹 全域唯一實例（供 app.py 使用）
# ==============================================================
manager_instance = VideoManager()