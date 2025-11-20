import threading
import time
import base64
import cv2
import json
from db_utils import get_db_connection
from detector.video_manager import manager_instance as manager
from detector.safety_ai import analyze_image_with_gemini
from service_utils import upload_to_cloudinary


# =============================================
# 單次分析
# =============================================
def run_single_safety_analysis(cam):
    cam_id = cam["camera_id"]
    print(f"📸 Running safety analysis for camera {cam_id}")

    frame = manager.get_raw_frame(cam_id)
    if frame is None:
        print(f"⚠ Camera {cam_id} no frame.")
        return False

    # Convert to bytes & base64
    _, buf = cv2.imencode(".jpg", frame)
    b64_image = base64.b64encode(buf).decode()

    # Upload image
    image_url = upload_to_cloudinary(buf.tobytes())

    # AI analysis
    result, raw = analyze_image_with_gemini(
        b64_image,
        cam["safety_location_type"] or "未指定",
        cam.get("safety_prompt_custom") or ""
    )

    conn = get_db_connection()
    cur = conn.cursor()

    if result is None:
        print(f"⚠ Gemini analysis failed for camera {cam_id}")

        cur.execute("""
            INSERT INTO safety_reports (
                camera_id, summary, raw_ai_response,
                image_url, image_base64,
                location_type, location_custom
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            cam_id,
            "Gemini 分析失敗",
            raw,
            image_url,
            b64_image,
            cam["safety_location_type"],
            cam["safety_location_custom"],
        ))
        conn.commit()
        cur.close()
        conn.close()
        return False

    # 成功 → 寫入安全分析資料
    cur.execute("""
        INSERT INTO safety_reports (
            camera_id, safety_score, safety_level, summary,
            issues, legal_refs, suggestions,
            raw_ai_response, image_url, image_base64,
            location_type, location_custom
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        cam_id,
        result["safety_score"],
        result["safety_level"],
        result["summary"],
        json.dumps(result["issues"]),
        json.dumps(result["legal_refs"]),
        json.dumps(result["suggestions"]),
        raw,
        image_url,
        b64_image,
        cam["safety_location_type"],
        cam["safety_location_custom"],
    ))

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Safety report stored for camera {cam_id}")
    return True



# =============================================
# 主排程
# =============================================
def run_safety_scheduler():
    print("🔄 Safety Analyzer Scheduler started.")
    time.sleep(20)   # 等待攝影機 stream 連線穩定

    # -----------------------------------------
    # 1️⃣ 啟動時 → 先跑每台攝影機一次分析
    # -----------------------------------------
    try:
        print("🚀 Running initial safety analysis for all cameras...")

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT *
            FROM cameras
            WHERE safety_analysis_enabled = 1
        """)
        cameras = cur.fetchall()
        cur.close()
        conn.close()

        # 初次分析
        for cam in cameras:
            run_single_safety_analysis(cam)
            time.sleep(3)  # 避免 Gemini 過載

        print("⏱ Setting next_run after initial analysis...")

        # 初次分析後 → 正確設定下一次時間
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE cameras
            SET safety_next_run = NOW() + INTERVAL safety_analysis_interval MINUTE
            WHERE safety_analysis_enabled = 1
        """)
        conn.commit()
        cur.close()
        conn.close()

        print("✅ Initial safety analysis completed.\n")

    except Exception as e:
        print("❌ Initial safety analysis error:", e)


    # -----------------------------------------
    # 2️⃣ 進入排程模式
    # -----------------------------------------
    while True:
        try:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT *
                FROM cameras
                WHERE safety_analysis_enabled = 1
            """)
            cameras = cur.fetchall()
            cur.close()
            conn.close()

            now_ts = time.time()

            for cam in cameras:
                next_run = cam["safety_next_run"]
                interval = cam["safety_analysis_interval"] or 30

                # 無 next_run → 不跑，設定下一次
                if not next_run:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE cameras
                        SET safety_next_run = NOW() + INTERVAL %s MINUTE
                        WHERE camera_id=%s
                    """, (interval, cam["camera_id"]))
                    conn.commit()
                    cur.close()
                    conn.close()
                    continue

                # 檢查是否到時間
                if now_ts < next_run.timestamp():
                    continue

                # ⭐ 到時間 → 執行分析
                run_single_safety_analysis(cam)

                # 設下一次
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE cameras
                    SET safety_next_run = NOW() + INTERVAL %s MINUTE
                    WHERE camera_id=%s
                """, (interval, cam["camera_id"]))
                conn.commit()
                cur.close()
                conn.close()

        except Exception as e:
            print("❌ Scheduler error:", e)

        time.sleep(60)   # 每 60 秒檢查一次
