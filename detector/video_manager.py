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

            # ✅ 綁定 callback，讓 YOLO 偵測在同一條線程內進行
            video_worker.callback = module_manager.process

            # ✅ 啟動攝影機串流（內部會維持原速）
            video_worker.start()

            self.workers[cid] = {
                "video": video_worker,
                "modules": module_manager,
                "last_frame": None,
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

    # ==========================================================
    # 🔹 熱重載門線設定（僅更新具 reload_gates() 的模組）
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

        modules = worker_bundle["modules"]
        reloaded = 0
        for m in modules.modules:
            if hasattr(m, "reload_gates"):
                try:
                    m.reload_gates()
                    reloaded += 1
                except Exception as e:
                    print(f"[ERROR] Reload gates failed for camera {camera_id}: {e}")

        print(f"[RELOAD] Camera {camera_id}: {reloaded} modules reloaded.")

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
