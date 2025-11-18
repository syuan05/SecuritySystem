import threading
import time
import base64
import cv2
import json
from db_utils import get_db_connection
from detector.video_manager import manager_instance as manager
from detector.safety_ai import analyze_image_with_gemini
from service_utils import upload_to_cloudinary

def run_safety_scheduler():
    print("🔄 Safety Analyzer Scheduler started.")
    time.sleep(20)
    # ============================================
    # 🚀 1️⃣ 啟動時第一次跑（不看 safety_next_run）
    # ============================================
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

        for cam in cameras:
            run_single_safety_analysis(cam)   # ⭐ 執行一次 AI 分析

        cur.close()
        conn.close()

        print("✅ Initial safety analysis completed.")
    except Exception as e:
        print("❌ Initial safety analysis error:", e)

    # ============================================
    # 🚀 2️⃣ 之後才進入排程模式（用 safety_next_run）
    # ============================================
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

            now = time.time()

            for cam in cameras:
                next_run = cam["safety_next_run"]
                interval = cam["safety_analysis_interval"] or 30

                # 如果 next_run 是 None → 代表第一次 → 設定下一次時間而不執行
                if not next_run:
                    # 👍 初次分析已做，這邊只設定下一次
                    cur.execute("""
                        UPDATE cameras
                        SET safety_next_run = NOW() + INTERVAL %s MINUTE
                        WHERE camera_id=%s
                    """, (interval, cam["camera_id"]))
                    conn.commit()
                    continue

                # 判斷是否到時間
                should_run = (now >= next_run.timestamp())
                if not should_run:
                    continue

                # ⭐ 到時間 → 執行分析
                run_single_safety_analysis(cam)

                # 更新下一次時間
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

        time.sleep(60)
def run_single_safety_analysis(cam):
    cam_id = cam["camera_id"]
    print(f"📸 Running safety analysis for camera {cam_id}")

    frame = manager.get_last_frame(cam_id)
    if frame is None:
        print(f"⚠ Camera {cam_id} no frame.")
        return

    # Convert to Base64
    _, buf = cv2.imencode(".jpg", frame)
    b64_image = base64.b64encode(buf).decode()

    # Upload to Cloudinary
    image_url = upload_to_cloudinary(buf.tobytes())

    # Run Gemini analysis
    result, raw = analyze_image_with_gemini(
        b64_image,
        cam["safety_location_type"] or "未指定",
        cam["safety_prompt_custom"] or ""
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
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
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
        return

    # 正常存入成功的分析結果
    cur.execute("""
        INSERT INTO safety_reports (
            camera_id, safety_score, safety_level, summary,
            issues, legal_refs, suggestions,
            raw_ai_response, image_url, image_base64,
            location_type, location_custom
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
