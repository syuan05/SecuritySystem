# detector/global_models.py
from ultralytics import YOLO
import types
import ultralytics.nn.autobackend as autobackend
import threading
import torch

pose_model_lock = threading.Lock()
print("[INIT] Loading YOLOv11 pose model (shared, safe mode)...")

# ============================================================
# 🔸 1️⃣ GPU / CPU 自動偵測
# ============================================================
USE_CUDA = torch.cuda.is_available()
DEVICE = "cuda:0" if USE_CUDA else "cpu"
print(f"[DEVICE] CUDA available: {USE_CUDA}, using device: {DEVICE}")

# ============================================================
# 🔸 2️⃣ 全域覆寫 AutoBackend.__init__ 以禁用 fuse()
# ============================================================
_old_init = autobackend.AutoBackend.__init__

def _safe_init(self, *args, **kwargs):
    """
    攔截 Ultralytics AutoBackend 初始化時的 fuse 過程，
    避免多執行緒同時 fuse() 時觸發 AttributeError: bn。
    """
    try:
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
# 🔸 3️⃣ 建立 YOLO 模型 + 強制移動到 GPU（可 fallback）
# ============================================================
try:
    pose_model = YOLO("yolo11n-pose")
    pose_model.to(DEVICE)     # ⭐ 強制指定 GPU / CPU
    print(f"[INIT] YOLOv11 pose model loaded on: {pose_model.device}")

except Exception as e:
    print(f"[ERROR] Failed to load YOLO on GPU, fallback to CPU: {e}")
    pose_model = YOLO("yolo11n-pose")
    pose_model.to("cpu")
    print(f"[INIT] YOLOv11 pose model fallback device: {pose_model.device}")

print("[INIT] YOLOv11 pose model loaded successfully (safe mode).")
