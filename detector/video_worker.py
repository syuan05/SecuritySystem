import cv2
import threading
import time
import os

class VideoWorker:
    def __init__(self, camera_id, camera_url):
        self.camera_id = camera_id
        self.camera_url = camera_url
        self.frame = None
        self.running = True
        self.lock = threading.Lock()
        self.callback = None  # 外部指定 callback 函式（ModuleManager用）

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

        # 嘗試抓取 FPS，沒有就預設30
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 60:
            fps = 30.0
        frame_interval = 1.0 / fps

        print(f"[INFO] Camera {self.camera_id} stream opened at {fps:.1f} FPS")

        while self.running:
            start_time = time.time()
            ok, frame = cap.read()

            # 🔁 若影片播放結束，自動重播
            if not ok or frame is None:
                # 嘗試重設影片到開頭
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    print(f"[WARN] Camera {self.camera_id}: failed to read frame (loop retry)")
                    time.sleep(0.1)
                    continue

            # 更新最新畫面緩衝
            with self.lock:
                self.frame = frame.copy()

            # 若有註冊 callback（例如 YOLO 模組）
            if self.callback:
                try:
                    self.callback(frame)
                except Exception as e:
                    print(f"[ERROR] Camera {self.camera_id} callback failed: {e}")

            # 控制原始播放速率
            elapsed = time.time() - start_time
            delay = frame_interval - elapsed
            if delay > 0:
                time.sleep(delay)

        cap.release()
        print(f"[INFO] Camera {self.camera_id} stopped.")

    # 取得最新畫面
    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    # 停止執行
    def stop(self):
        self.running = False
