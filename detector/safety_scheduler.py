# safety_scheduler.py — 修正版（確保所有欄位正確儲存）
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
# 單次分析（修正版 - 確保所有欄位都正確儲存）
# =============================================
def run_single_safety_analysis(cam):
    """
    執行單次安全分析（完整版）
    
    流程:
    1. 擷取攝影機畫面
    2. 上傳圖片到 Cloudinary
    3. 呼叫 AI 分析（含 RAG）
    4. 將結果寫入資料庫（確保所有欄位）
    """
    cam_id = cam["camera_id"]
    print(f"\n{'='*60}")
    print(f"📸 Camera {cam_id} - 開始安全分析")
    print(f"{'='*60}")
    
    # Step 1: 取得畫面
    frame = manager.get_raw_frame(cam_id)
    if frame is None:
        print(f"⚠️  Camera {cam_id} 無法取得畫面")
        return False
    
    # Step 2: 轉換為 base64
    _, buf = cv2.imencode(".jpg", frame)
    b64_image = base64.b64encode(buf).decode()
    
    # # Step 3: 上傳到 Cloudinary（選用）
    # image_url = ""
    # try:
    #     image_url = upload_to_cloudinary(buf.tobytes())
    #     print(f"✅ 圖片已上傳: {image_url[:50]}...")
    # except Exception as e:
    #     print(f"⚠️  圖片上傳失敗（將使用 base64）: {e}")
    
    # Step 4: AI 分析（含 RAG）
    result = None
    raw_json = ""
    rag_metadata = {
        "rag_query": "",
        "rag_results_count": 0,
        "rag_results": []
    }
    
    try:
        result, raw_json, rag_metadata = analyze_image_with_gemini(
            image_base64=b64_image,
            location_type=cam["safety_location_type"] or "未指定",
            custom_prompt=cam.get("safety_prompt_custom") or "",
            use_rag=True
        )
    except Exception as e:
        print(f"❌ AI 分析失敗: {e}")
        # import traceback
        # traceback.print_exc()
        # result = {
        #     "error": str(e),
        #     "safety_score": 0,
        #     "safety_level": "Error",
        #     "summary": "AI 分析失敗",
        #     "issues": [],
        #     "suggestions": ["請稍後重試或聯繫系統管理員"],
        #     "legal_refs": [],
        #     "scene_analysis": {},
        #     "merged_compliance_detail": ""
        # }
        # raw_json = json.dumps(result, ensure_ascii=False)
    
    # Step 5: 準備要儲存的資料（確保所有欄位都有值）
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 確保所有必要欄位都存在
    safety_score = result.get("safety_score", 0) if result else 0
    safety_level = result.get("safety_level", "Unknown") if result else "Unknown"
    summary = result.get("summary", "分析失敗") if result else "分析失敗"
    
    # JSON 欄位 - 確保格式正確
    issues_json = json.dumps(result.get("issues", []), ensure_ascii=False) if result else "[]"
    legal_refs_json = json.dumps(result.get("legal_refs", []), ensure_ascii=False) if result else "[]"
    suggestions_json = json.dumps(result.get("suggestions", []), ensure_ascii=False) if result else "[]"
    scene_analysis_json = json.dumps(result.get("scene_analysis", {}), ensure_ascii=False) if result else "{}"
    rag_results_json = json.dumps(rag_metadata["rag_results"], ensure_ascii=False)
    
    # 其他欄位
    # image_url_final = image_url or ""
    rag_query = rag_metadata["rag_query"] or ""
    merged_compliance = result.get("merged_compliance_detail", "") if result else ""
    
    # 顯示將要儲存的資料摘要
    print(f"\n📊 準備儲存資料:")
    print(f"   - safety_score: {safety_score}")
    print(f"   - safety_level: {safety_level}")
    print(f"   - summary: {summary[:50]}...")
    print(f"   - issues 數量: {len(result.get('issues', []))} 項")
    print(f"   - legal_refs 數量: {len(result.get('legal_refs', []))} 條")
    print(f"   - suggestions 數量: {len(result.get('suggestions', []))} 項")
    print(f"   - scene_analysis: {'有' if result.get('scene_analysis') else '無'}")
    print(f"   - rag_query: {rag_query[:50]}..." if rag_query else "   - rag_query: (空)")
    print(f"   - rag_results 數量: {len(rag_metadata['rag_results'])} 條")
    print(f"   - merged_compliance_detail: {'有' if merged_compliance else '無'}")
    # print(f"   - image_url: {'有' if image_url_final else '使用 base64'}")
    
    # Step 6: 寫入資料庫 - 完整版 SQL
    try:
        sql = """
            INSERT INTO safety_reports (
                camera_id,
                safety_score,
                safety_level,
                summary,
                issues,
                legal_refs,
                suggestions,
                scene_analysis,
                raw_ai_response,
                image_base64,
                location_type,
                location_custom,
                rag_query,
                rag_results,
                merged_compliance_detail
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        
        values = (
            cam_id,                          # camera_id
            safety_score,                    # safety_score
            safety_level,                    # safety_level
            summary,                         # summary
            issues_json,                     # issues (JSON)
            legal_refs_json,                 # legal_refs (JSON)
            suggestions_json,                # suggestions (JSON)
            scene_analysis_json,             # scene_analysis (JSON)
            raw_json,                        # raw_ai_response (JSON)
            # image_url_final,                 # image_url
            b64_image,                       # image_base64
            cam["safety_location_type"],     # location_type
            cam.get("safety_location_custom") or "",  # location_custom
            rag_query,                       # rag_query
            rag_results_json,                # rag_results (JSON)
            merged_compliance                # merged_compliance_detail
        )
        
        cur.execute(sql, values)
        conn.commit()
        
        # 取得剛插入的記錄 ID
        report_id = cur.lastrowid
        print(f"✅ 報告已儲存到資料庫（ID: {report_id}）")
        
        # 驗證儲存（可選）
        cur.execute("""
            SELECT id, safety_score, safety_level, 
                   JSON_LENGTH(issues) as issues_count,
                   JSON_LENGTH(legal_refs) as legal_refs_count,
                   JSON_LENGTH(suggestions) as suggestions_count,
                   LENGTH(scene_analysis) as scene_length,
                   LENGTH(rag_query) as rag_query_length,
                   JSON_LENGTH(rag_results) as rag_results_count,
                   LENGTH(merged_compliance_detail) as merged_length
            FROM safety_reports
            WHERE id = %s
        """, (report_id,))
        
        verify = cur.fetchone()
        if verify:
            print(f"\n✅ 資料庫驗證:")
            print(f"   - 記錄 ID: {verify[0]}")
            print(f"   - 安全分數: {verify[1]}")
            print(f"   - 安全等級: {verify[2]}")
            print(f"   - issues 數量: {verify[3]}")
            print(f"   - legal_refs 數量: {verify[4]}")
            print(f"   - suggestions 數量: {verify[5]}")
            print(f"   - scene_analysis 長度: {verify[6]} bytes")
            print(f"   - rag_query 長度: {verify[7]} bytes")
            print(f"   - rag_results 數量: {verify[8]}")
            print(f"   - merged_compliance 長度: {verify[9]} bytes")
        
    except Exception as e:
        print(f"❌ 資料庫寫入失敗: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()
    
    return True


# =============================================
# 主排程器（與原版相同）
# =============================================
def run_safety_scheduler():
    """
    安全分析排程器
    
    執行邏輯:
    1. 啟動時先對所有啟用攝影機執行一次分析
    2. 然後進入排程模式，依照各攝影機的 interval 定期執行
    """
    print("\n" + "="*70)
    print("🚀 Safety Analyzer Scheduler 啟動")
    print("="*70)
    
    # 等待攝影機連線穩定
    print("\n⏳ 等待攝影機連線穩定（20秒）...")
    time.sleep(20)
    
    # -----------------------------------------
    # 1️⃣ 啟動時 → 先對所有攝影機執行一次分析
    # -----------------------------------------
    try:
        print("\n" + "="*70)
        print("🔄 執行初始安全分析")
        print("="*70)
        
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT *
            FROM cameras
            WHERE safety_analysis_enabled = 1
            ORDER BY camera_id
        """)
        cameras = cur.fetchall()
        cur.close()
        conn.close()
        
        print(f"\n找到 {len(cameras)} 台啟用的攝影機\n")
        
        # 初次分析
        success_count = 0
        for cam in cameras:
            try:
                if run_single_safety_analysis(cam):
                    success_count += 1
                time.sleep(5)  # 避免 API 過載
            except Exception as e:
                print(f"❌ Camera {cam['camera_id']} 分析失敗: {e}")
        
        print(f"\n✅ 初始分析完成: {success_count}/{len(cameras)} 成功")
        
        # 初次分析後 → 設定下一次執行時間
        print("\n⏱️  設定排程時間...")
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
        
        print("✅ 排程設定完成\n")
        
    except Exception as e:
        print(f"❌ 初始分析錯誤: {e}")
        import traceback
        traceback.print_exc()
    
    # -----------------------------------------
    # 2️⃣ 進入排程模式
    # -----------------------------------------
    print("\n" + "="*70)
    print("🔁 進入排程模式（每 60 秒檢查一次）")
    print("="*70 + "\n")
    
    while True:
        try:
            # 查詢所有啟用的攝影機
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
                cam_id = cam["camera_id"]
                next_run = cam["safety_next_run"]
                interval = cam["safety_analysis_interval"] or 30
                
                # 如果沒有 next_run，設定下一次執行時間
                if not next_run:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE cameras
                        SET safety_next_run = NOW() + INTERVAL %s MINUTE
                        WHERE camera_id = %s
                    """, (interval, cam_id))
                    conn.commit()
                    cur.close()
                    conn.close()
                    print(f"⏱️  Camera {cam_id} 排程已設定（{interval} 分鐘後執行）")
                    continue
                
                # 檢查是否到達執行時間
                if now_ts < next_run.timestamp():
                    continue
                
                # ⭐ 到達執行時間 → 執行分析
                print(f"\n⏰ Camera {cam_id} 排程時間到，執行分析...")
                
                try:
                    run_single_safety_analysis(cam)
                except Exception as e:
                    print(f"❌ Camera {cam_id} 分析失敗: {e}")
                
                # 設定下一次執行時間
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE cameras
                    SET safety_next_run = NOW() + INTERVAL %s MINUTE
                    WHERE camera_id = %s
                """, (interval, cam_id))
                conn.commit()
                cur.close()
                conn.close()
                
                print(f"✅ Camera {cam_id} 下次執行時間: {interval} 分鐘後\n")
        
        except Exception as e:
            print(f"❌ 排程器錯誤: {e}")
            import traceback
            traceback.print_exc()
        
        # 每 60 秒檢查一次
        time.sleep(60)


# =============================================
# 啟動排程器（供 main.py 呼叫）
# =============================================
def start_scheduler():
    """
    在背景執行緒啟動排程器
    """
    scheduler_thread = threading.Thread(
        target=run_safety_scheduler,
        daemon=True,
        name="SafetyScheduler"
    )
    scheduler_thread.start()
    print("✅ Safety Scheduler 已在背景啟動\n")
    return scheduler_thread


# =============================================
# 測試用
# =============================================
if __name__ == "__main__":
    print("🧪 直接執行 safety_scheduler.py（測試模式）\n")
    
    # 測試單一攝影機
    print("請選擇測試模式:")
    print("1. 完整排程器測試")
    print("2. 單一攝影機測試")
    
    choice = input("請輸入選項 (1/2): ").strip()
    
    if choice == "2":
        # 單一攝影機測試
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT * FROM cameras
            WHERE safety_analysis_enabled = 1
            LIMIT 1
        """)
        cam = cur.fetchone()
        cur.close()
        conn.close()
        
        if cam:
            print(f"\n測試攝影機: {cam['camera_id']}")
            run_single_safety_analysis(cam)
        else:
            print("❌ 找不到啟用的攝影機")
    else:
        # 完整排程器
        run_safety_scheduler()