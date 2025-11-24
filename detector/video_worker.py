import cv2
import threading
import time

class VideoWorker:
    def __init__(self, camera_id, camera_url):
        self.camera_id = camera_id
        self.camera_url = camera_url
        self.frame = None
        self.running = True
        self.lock = threading.Lock()
        self.callback = None  # 模組分析回呼（會回傳已繪製的 frame）
        self.frame_counter = 0
        self.raw_frame = None
        # ✅ 新增：reload 刷新標記
        self.reload_pending = False
        self.reload_lock = threading.Lock()

    # 啟動讀取執行緒
    def start(self):
        t = threading.Thread(target=self.run, daemon=True)
        t.start()

    # 主讀取迴圈
    def run(self):
        cap = cv2.VideoCapture(self.camera_url)
        if not cap.isOpened():
            print(f"[ERROR] Camera {self.camera_id} failed to open stream: {self.camera_url}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 60:
            fps = 30.0
        frame_interval = 1.0 / fps

        print(f"[INFO] Camera {self.camera_id} stream opened at {fps:.1f} FPS")

        target_size = (1280, 720)

        from detector.drawer import Drawer
        drawer = Drawer()

        while self.running:
            start = time.time()
            
            # ✅ 檢查是否有 reload 請求
            should_reload = False
            with self.reload_lock:
                if self.reload_pending:
                    should_reload = True
                    self.reload_pending = False
            
            ok, frame = cap.read()

            if not ok or frame is None:
                time.sleep(1/30)
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            with self.lock:
                self.raw_frame = frame.copy()

            frame = cv2.resize(frame, target_size)

            # -------- callback，只能執行一次 --------
            if self.callback:
                try:
                    results, gates, gate_name_map = self.callback(frame)
                except Exception as e:
                    print(f"[ERROR] callback failed: {e}")
                    continue
            else:
                time.sleep(1/30)
                results, gates, gate_name_map = ([], [], {})

            # -------- Drawer畫圖 --------
            try:
                # ✅ 如果是 reload 請求，強制重繪所有線條
                if should_reload:
                    print(f"[RELOAD] Camera {self.camera_id}: Redrawing gates after reload")
                    drawn = drawer.draw(frame, self.camera_id, results, gates, gate_name_map)
                else:
                    drawn = drawer.draw(frame, self.camera_id, results, gates, gate_name_map)
                
                with self.lock:
                    self.frame = drawn
            except Exception as e:
                print(f"[DRAW ERROR] {e}")

            elapsed = time.time() - start
            delay = frame_interval - elapsed
            if delay > 0:
                time.sleep(delay)

        cap.release()
        print(f"[INFO] Camera {self.camera_id} stopped.")

    # ✅ 新增：請求刷新畫面（非阻塞）
    def request_reload_refresh(self):
        """
        標記需要重繪 gates，下一幀會自動處理
        這是非阻塞的，避免與主執行緒競爭 lock
        """
        with self.reload_lock:
            self.reload_pending = True
        print(f"[INFO] Camera {self.camera_id}: Reload refresh requested")

    # 取得最新畫面（Flask 串流用）
    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()
    def get_raw_frame(self):
        with self.lock:
            return None if self.raw_frame is None else self.raw_frame.copy()
    def stop(self):
        self.running = False