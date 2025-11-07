# detector/global_models.py
from ultralytics import YOLO
import types
import ultralytics.nn.autobackend as autobackend
import threading
pose_model_lock = threading.Lock()
print("[INIT] Loading YOLOv11 pose model (shared, safe mode)...")

# ============================================================
# 🔸 1️⃣ 全域覆寫 AutoBackend.__init__ 以禁用 fuse()
# ============================================================
_old_init = autobackend.AutoBackend.__init__

def _safe_init(self, *args, **kwargs):
    """
    攔截 Ultralytics AutoBackend 初始化時的 fuse 過程，
    避免多執行緒同時 fuse() 時觸發 AttributeError: bn。
    """
    try:
        # 在 kwargs 中偵測 verbose 或 model 並改寫成安全版本
        if "model" in kwargs and hasattr(kwargs["model"], "fuse"):
            kwargs["model"].fuse = lambda *a, **kw: kwargs["model"]
        _old_init(self, *args, **kwargs)
    except AttributeError as e:
        if "bn" in str(e):
            print("[SAFE_MODE] Skipped fuse() due to bn deletion conflict.")
        else:
            raise e

autobackend.AutoBackend.__init__ = _safe_init

# ============================================================
# 🔸 2️⃣ 建立 YOLO 模型（不會再 fuse）
# ============================================================
pose_model = YOLO("models/yolo11n-pose.pt")

print("[INIT] YOLOv11 pose model loaded successfully (safe mode).")
