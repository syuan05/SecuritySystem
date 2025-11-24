# service_utils.py
import os
import cloudinary
from dotenv import load_dotenv

load_dotenv()

# ======================================================
# 🔹 Cloudinary 設定（統一管理）
# ======================================================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_to_cloudinary(image_bytes):
    """上傳 bytes 圖片到 Cloudinary, 回傳 secure_url"""
    import cloudinary.uploader
    res = cloudinary.uploader.upload(image_bytes)
    return res["secure_url"]

# ======================================================
# 🔹 Gemini 設定（統一管理）
# ======================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"


def call_gemini_api(prompt, image_base64):
    """統一呼叫 Gemini，回傳 raw response"""
    import requests

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }
        ]
    }

    response = requests.post(url, json=payload)
    return response.json()

# ======================================================
# 🔹 Gemini + Gemma Fallback
# ======================================================

def call_gemma_local(prompt, image_base64):
    """
    Gemma 本地推論（你之後可接 ollama 或本地 API）
    這裡先做一個 placeholder，避免報錯
    """
    print("⚠ 使用 Gemma local fallback（尚未實作，可連 ollama）")

    # ⚠️ 如果你之後要接本地 Gemma，這裡改成真正的 API
    # 目前先模擬一個回傳格式（避免程式壞掉）
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": """
{
  "safety_score": 80,
  "safety_level": "Good",
  "summary": "Gemma fallback 模擬：環境尚可",
  "issues": [],
  "suggestions": ["請稍後使用 Gemini 重試"],
  "legal_refs": []
}
"""
                        }
                    ]
                }
            }
        ]
    }


def call_with_fallback(prompt, image_base64):
    """
    Gemini 主模型、Gemma 備援
    """
    try:
        print("⚡ 使用 Gemini 進行推論...")
        return call_gemini_api(prompt, image_base64)

    except Exception as e:
        print("❌ Gemini 失敗，切換到本地 Gemma:", e)
        return call_gemma_local(prompt, image_base64)
