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

        target_size = (1280, 720)  # ✅ 統一輸出大小

        while self.running:
            start_time = time.time()
            ok, frame = cap.read()
            if not ok:
                print(f"[WARN] Camera {self.camera_id}: failed to read frame")
            else:
                print(f"[PERF] Camera {self.camera_id}: frame read took {time.time()-start_time:.3f}s")
            # 🔁 若影片結束，自動重播
            if not ok or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    print(f"[WARN] Camera {self.camera_id}: failed to read frame (loop retry)")
                    time.sleep(0.1)
                    continue

            # ✅ 統一大小
            frame = cv2.resize(frame, target_size)

            processed_frame = frame

            if self.callback:
                cb_start = time.time()
                print(f"[LOOP] Camera {self.camera_id}: starting callback")
                result = self.callback(frame)
                print(f"[LOOP] Camera {self.camera_id}: callback returned")
                print(f"[PERF] Camera {self.camera_id}: callback took {time.time()-cb_start:.3f}s")
                try:
                    result = self.callback(frame)
                    if result is not None:
                        with self.lock:
                            self.frame = result.copy()
                        continue
                except Exception as e:
                    import traceback
                    print(f"[ERROR] Camera {self.camera_id} callback failed: {e}")
                    traceback.print_exc()

            with self.lock:
                self.frame = processed_frame.copy()

            elapsed = time.time() - start_time
            delay = frame_interval - elapsed
            if delay > 0:
                time.sleep(delay)

        cap.release()
        print(f"[INFO] Camera {self.camera_id} stopped.")


    # 取得最新畫面（Flask 串流用）
    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.running = False
