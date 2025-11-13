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

        # 正確取得 modules
        modules = worker_bundle["modules"]

        # === 重新載入每個模組 ===
        reloaded = 0
        for m in modules.modules:
            if hasattr(m, "reload_gates"):
                try:
                    m.reload_gates()
                    reloaded += 1
                except Exception as e:
                    print(f"[ERROR] Reload gates failed for module in camera {camera_id}: {e}")

        print(f"[RELOAD] Camera {camera_id}: {reloaded} modules reloaded.")

        # === 收集所有 gate IDs (人流 + inout) ===
        person_gate_ids = []
        for m in modules.modules:
            if m.__class__.__name__ == "PersonCountModule":
                if hasattr(m, "gates"):
                    person_gate_ids.extend([g["id"] for g in m.gates])
        # === 初始化 event_bus 統計（確保左上面板更新） ===
        try:
            from detector.event_bus import event_bus
            event_bus.ensure_person_count_init(camera_id, person_gate_ids)
        except Exception as e:
            print(f"[ERROR] ensure_person_count_init failed for camera {camera_id}: {e}")

        # === 立即刷新畫面 ===
        try:
            video_worker = worker_bundle["video"]
            frame = video_worker.get_frame()
            if frame is not None:
                from detector.drawer import Drawer
                drawer = Drawer()

                # 全部線條（inout + person_count）
                all_gates = []
                for m in modules.modules:
                    if hasattr(m, "gates"):
                        all_gates.extend(m.gates)

                new_frame = drawer.draw_gates_only(frame, all_gates)
                with video_worker.lock:
                    video_worker.frame = new_frame.copy()

                print(f"[REFRESH] Camera {camera_id}: gates redrawn after reload.")
            else:
                print(f"[WARN] No frame available for camera {camera_id}, skip refresh.")

        except Exception as e:
            import traceback
            print(f"[ERROR] Failed to refresh frame for camera {camera_id}: {e}")
            traceback.print_exc()


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
