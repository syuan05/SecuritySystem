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
GEMINI_MODEL = "gemini-2.0-flash"


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
