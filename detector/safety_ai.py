# safety_ai.py — 改進版（移除寫死法規，完全使用 RAG）
import json
from service_utils import call_gemini_api, call_gemma_local, call_with_fallback
from detector.legal.rag_system import LawVectorDatabase

# ==================== RAG 系統初始化 ====================

ALLOWED_LAWS = {
    "車站大廳": ["建築技術規則", "消防", "捷運", "公共場所", "通道淨寬", "逃生", "無障礙"],
    "商場通道": ["建築技術規則", "消防", "公共場所", "商場安全", "消保法"],
    "住宅走廊": ["公寓大廈管理條例", "走廊淨空", "消防", "避難", "通道"],
    "停車場": ["建築技術規則", "消防", "停車場管理", "通風", "避難"],
    "校園": ["建築技術規則", "消防", "校園安全", "逃生"],
    "醫院": ["醫療機構", "無障礙", "消防", "建築技術規則"],
    "大樓大廳": ["建築技術規則", "消防", "公共場所"],
    "樓梯間": ["樓梯", "扶手", "避難", "消防"],
    "工地": ["營造", "安衛法", "施工安全"],
    "倉庫": ["倉庫", "堆置", "危險物", "消防"],
    "工廠": ["工廠", "職安", "機械", "危險作業"],
    "公園": ["公園", "遊戲設施", "公共場所"],
    "超市": ["商場", "公共場所", "消防"],
    "電梯前室": ["電梯", "前室", "避難", "消防"],
    "旅館": ["旅館", "旅宿", "消防"]
}
_rag_system = None

def get_rag_system():
    """單例模式獲取 RAG 系統"""
    global _rag_system
    if _rag_system is None:
        print("🔧 初始化 RAG 法規搜尋系統...")
        _rag_system = LawVectorDatabase(
            db_path="./legal_vector_db",
            model_name="shibing624/text2vec-base-chinese"
        )
        print("✅ RAG 系統就緒\n")
    return _rag_system


# ==================== 問題類型到查詢關鍵字的智能擴展 ====================

def build_rag_query(scene_data, location_type, custom_prompt):
    """
    根據場景理解結果構建最優化的 RAG 查詢
    
    Args:
        scene_data: Gemini 場景理解結果
        location_type: 場域類型
        custom_prompt: 使用者自訂提示
    
    Returns:
        優化後的查詢字串
    """
    
    # 基礎查詢元素
    query_parts = [location_type]
    
    # 場景摘要
    if scene_data.get("scene_summary"):
        query_parts.append(scene_data["scene_summary"])
    
    # 安全關鍵字
    if scene_data.get("safety_keywords"):
        query_parts.extend(scene_data["safety_keywords"][:5])  # 取前5個關鍵字
    
    # 潛在風險
    if scene_data.get("potential_risks"):
        query_parts.extend(scene_data["potential_risks"][:3])  # 取前3個風險
    
    # 使用者自訂
    if custom_prompt:
        query_parts.append(custom_prompt)
    
    # 智能關鍵字擴展
    query_text = " ".join(query_parts)
    
    # 根據關鍵字自動擴展
    expansions = {
        "走廊": "走廊 通道 堆置 雜物 公寓大廈管理條例",
        "堆積": "堆置 障礙物 阻塞 占用 妨礙通行",
        "鋼筋": "鋼筋外露 營造安全 施工安全 護套",
        "樓梯": "樓梯 扶手 防滑 緊急逃生",
        "濕滑": "濕滑 防滑 地面 跌倒",
        "消防": "消防 滅火器 逃生 避難",
        "照明": "照明 亮度 安全 採光"
    }
    
    for key, expansion in expansions.items():
        if key in query_text:
            query_text = f"{query_text} {expansion}"
            break
    
    return query_text


# ==================== 主要分析函數 ====================

def analyze_image_with_gemini(image_base64, location_type, custom_prompt="", use_rag=True):
    """
    完整安全分析流程（Gemini 主、Gemma 備援）
    
    流程:
    1. Gemini 場景理解
    2. RAG 法規檢索（移除寫死法規）
    3. Gemini 深度分析（生成完整報告）
    
    Returns:
        (result_dict, raw_json_str, rag_metadata)
    """
    
    rag = get_rag_system()
    
    # ===============================
    # Step 1: 場景理解（Gemini/Gemma fallback）
    # ===============================
    scene_prompt = f"""
你是台灣公共安全專家，請分析這張圖片的場景。

**只輸出純 JSON（不要 markdown 標記）:**
{{
  "scene_summary": "場景的簡短描述（1-2句話）",
  "safety_keywords": ["關鍵詞1", "關鍵詞2", "關鍵詞3"],
  "potential_risks": ["可能風險1", "可能風險2"]
}}

**場景類型:** {location_type}
**使用者補充:** {custom_prompt or "無"}
"""
    
    print("📸 [Step 1/3] 場景理解中...")
    raw_scene = call_with_fallback(scene_prompt, image_base64)
    text_scene = raw_scene["candidates"][0]["content"]["parts"][0]["text"]
    
    try:
        scene_data = json.loads(
            text_scene.replace("```json", "").replace("```", "").strip()
        )
        print(f"   ✅ 場景: {scene_data.get('scene_summary', 'N/A')[:50]}...")
    except json.JSONDecodeError as e:
        print(f"   ⚠️ 場景解析失敗: {e}")
        scene_data = {
            "scene_summary": "無法解析場景",
            "safety_keywords": [],
            "potential_risks": []
        }
    
    # ===============================
    # Step 2: RAG 法規檢索（動態檢索，不再寫死）
    # ===============================
    rag_results = []
    rag_query = ""
    
    if use_rag:
        print("🔍 [Step 2/3] RAG 法規檢索中...")
        
        # 構建智能查詢
        rag_query = build_rag_query(scene_data, location_type, custom_prompt)
        print(f"   查詢: {rag_query[:100]}...")
        
        # 混合搜尋（關鍵字 + 向量）
        rag_results = rag.search(
            query=rag_query,
            mode="hybrid",
            scene_filter=location_type if location_type != "其他" else None,
            top_k=10,
            vector_weight=0.2  # 關鍵字權重 80%
        )
        
        print(f"   ✅ 找到 {len(rag_results)} 條相關法規")
        allowed_keywords = ALLOWED_LAWS.get(location_type, [])
        if allowed_keywords:
            filtered_results = []
            for law in rag_results:
                if any(kw in law["law"] or kw in law["content"] for kw in allowed_keywords):
                    filtered_results.append(law)
            rag_results = filtered_results

        print(f"   🎯 白名單過濾後剩 {len(rag_results)} 條法規")
        blocked_keywords = [
            "道路交通管理處罰條例",
            "臨時停車", "違規停車", "停車",
            "慢車", "汽車駕駛", "駕駛人",
            "車道", "路邊", "行車"
        ]

        rag_results = [
            law for law in rag_results
            if not any(b in law["law"] or b in law["content"] for b in blocked_keywords)
        ]

        print(f"   🚫 交通法規過濾後剩 {len(rag_results)} 條")
        # 顯示前3條法規
        for i, law in enumerate(rag_results[:3], 1):
            print(f"      {i}. {law['law']} (分數: {law.get('final_score', 0):.3f})")
    else:
        print("⚠️ RAG 已停用，將使用一般安全原則評估")
    
    # ===============================
    # Step 3: Gemini 深度安全分析
    # ===============================
    print("🤖 [Step 3/3] 生成安全報告...")
    
    # 組織法規上下文（完整格式）
    if rag_results:
        laws_context = "\n".join([
            f"""
【法規 {i+1}】{law['law']}
  ├─ 相關度: {law.get('final_score', law.get('similarity', 0)):.3f}
  ├─ 適用場景: {', '.join(law.get('scenes', []))}
  ├─ 嚴重程度: {law.get('severity', 'unknown')}
  └─ 條文內容: {law['content']}
"""
            for i, law in enumerate(rag_results[:8])
        ])
        
        law_instruction = f"""
=== 📋 相關法規依據（共 {len(rag_results)} 條）===
{laws_context}

**請嚴格依據上述法規評估圖片中的環境安全狀況。**
"""
    else:
        law_instruction = f"""
=== ⚠️ 法規檢索結果 ===
場域: {location_type}
RAG 系統未找到直接相關法規，請依照台灣一般安全法規與常識進行評估。

使用者補充: {custom_prompt or "無"}
"""
    
    # 最終分析提示詞
    final_prompt = f"""
你是台灣職安與公共安全專家，請評估圖片中的「環境安全」狀況。

=== 🔍 場景理解結果 ===
場景描述: {scene_data.get('scene_summary', '未知場景')}
安全關鍵字: {', '.join(scene_data.get('safety_keywords', []))}
可能風險: {', '.join(scene_data.get('potential_risks', []))}

{law_instruction}

=== 📊 評估規則 ===
1. **評估範圍**: 只評估「環境、設施、設備」的風險，不評估人為行為
2. **評分標準**:
   - 0-39分: 重大風險（通道完全阻塞、設施嚴重損壞、明顯違規）
   - 40-59分: 中度問題（多項輕微問題累積）
   - 60-79分: 輕微問題（1-2項不影響通行的小問題）
   - 80-100分: 安全良好（符合安全標準）

3. **禁止列為問題**:
    ❌ 旅客攜帶行李箱、背包（這是正常行為）
    ❌ 正常人流通行
    ❌ 短暫停留、排隊等候

4. **legal_refs 格式要求**:
   - 必須列出所有相關法規（不只是違反的）
   - compliance_status 三種狀態: "compliant"（符合）、"violated"（違反）、"unknown"（待確認）
   - 每條法規都要說明 relevance（為何相關）

=== 📝 輸出格式 ===
請輸出純 JSON（不要包含 markdown 標記）:

{{
  "safety_score": 85,
  "safety_level": "Excellent | Good | Fair | Poor",
  "summary": "一句話總結環境安全狀況",
  "issues": [
    {{
      "name": "問題名稱",
      "description": "具體描述此問題的現況",
      "severity": "high | medium | low",
      "law": "違反的具體法規名稱",
      "suggested_action": "建議的改善措施"
    }}
  ],
  "suggestions": [
    "改善建議1",
    "改善建議2"
  ],
  "legal_refs": [
    {{
      "law": "完整法規名稱（如：公寓大廈管理條例 §16）",
      "relevance": "說明此法規為何與圖片場景相關",
      "compliance_status": "compliant | violated | unknown",
      "content_summary": "法規內容重點摘要（1-2句話）",
      "source_url": ""
    }}
  ]
}}

**重要提醒:**
- 如果環境安全良好，issues 可以是空陣列 []
- legal_refs 要包含所有相關法規，不只是違反的
- 評分要客觀，避免過度嚴格或過度寬鬆
"""
    
    raw_final = call_with_fallback(final_prompt, image_base64)
    text_fin = raw_final["candidates"][0]["content"]["parts"][0]["text"]
    
    try:
        final_data = json.loads(
            text_fin.replace("```json", "").replace("```", "").strip()
        )
        print(f"   ✅ 安全分數: {final_data.get('safety_score', 'N/A')}")
    except json.JSONDecodeError as e:
        print(f"   ⚠️ 分析結果解析失敗: {e}")
        final_data = {
            "error": f"JSON 解析失敗: {str(e)}",
            "raw_response": text_fin,
            "safety_score": 0,
            "safety_level": "Error",
            "summary": "AI 分析失敗",
            "issues": [],
            "suggestions": ["請稍後重試或聯繫系統管理員"],
            "legal_refs": []
        }
    
    # ===============================
    # Step X: 補 RAG 法規進 legal_refs（加入法規名 + 條號 + 全文）
    # ===============================

    if not final_data.get("legal_refs"):
        final_data["legal_refs"] = []

    for law in rag_results[:8]:
        # law.law = "建築技術規則 第77條" 這種格式
        import re
        law_full = law.get("law", "")
        
        article_match = re.search(r"(第?\s*\d+\s*條|§\s*\d+)", law_full)
        article = article_match.group(0) if article_match else ""

        # 法規名稱：把條號移除後的前半段
        law_name = law_full.replace(article, "").strip()
        # 條文內容（你 RAG 資料庫有 content / content_summary）
        full_content = law.get("content", "") or law.get("content_summary", "")

        final_data["legal_refs"].append({
            "law": law_full,                # 全名
            "law_name": law_name,           # 法規名稱
            "article": article,             # 第幾條
            "full_content": full_content,   # 條文全文
            "content_summary": law.get("content_summary", ""),
            "source_url": law.get("source_url", ""),
            "relevance": f"{law.get('final_score', 0):.3f}",
            "compliance_status": law.get("compliance_status", "unknown")
        })

        # 補充場景分析
        final_data["scene_analysis"] = scene_data
    # ===============================
    # Step 4.5: AI 合併合規詳情（content_summary → 一段文字）
    # ===============================

    content_list = [law.get("content_summary", "") for law in final_data["legal_refs"] if law.get("content_summary")]

    if content_list:
        merge_prompt = f"""
    你是台灣職安與公共安全法規專家。
    以下是多條法規的重點摘要，請你整合成一段 3～5 句自然語句的合規詳情敘述：

    {content_list}

    請避免條列式，只輸出一段自然語句。
    """

        merged_text_raw = call_gemini_api(merge_prompt, image_base64)
        merged_text = (
            merged_text_raw.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )

        final_data["merged_compliance_detail"] = merged_text
    else:
        final_data["merged_compliance_detail"] = ""
    # ===============================
    # Step 5: 準備回傳資料（含 RAG metadata）
    # ===============================
    rag_metadata = {
        "rag_query": rag_query,
        "rag_results_count": len(rag_results),
        "rag_results": [
            {
                "law": law["law"],
                "content": law["content"],
                "similarity": law.get("final_score", law.get("similarity", 0)),
                "scenes": law.get("scenes", []),
                "severity": law.get("severity", "unknown")
            }
            for law in rag_results[:10]
        ]
    }
    
    # 生成格式化的 JSON 字串
    result_json = json.dumps(final_data, ensure_ascii=False, indent=2)
    
    print("✅ 分析完成\n")
    
    return final_data, result_json, rag_metadata


# ==================== 測試用 ====================

if __name__ == "__main__":
    """
    測試範例
    """
    import base64
    
    print("="*70)
    print("🧪 safety_ai.py 測試模式（RAG 動態法規版）")
    print("="*70)
    
    try:
        # 測試圖片路徑
        image_path = input("\n請輸入測試圖片路徑: ").strip()
        
        if not image_path:
            print("⚠️ 未提供圖片，結束測試")
            exit()
        
        # 讀取圖片
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        
        # 執行分析
        result, json_str, rag_meta = analyze_image_with_gemini(
            image_base64=image_data,
            location_type="住宅走廊",
            custom_prompt="請特別注意消防安全",
            use_rag=True
        )
        
        # ==================== 顯示結果 ====================
        print("\n" + "="*70)
        print("📊 分析結果")
        print("="*70)
        
        print(f"\n🎯 安全評估")
        print(f"   分數: {result.get('safety_score', 'N/A')} / 100")
        print(f"   等級: {result.get('safety_level', 'N/A')}")
        print(f"   總結: {result.get('summary', 'N/A')}")
        
        # 顯示問題
        issues = result.get('issues', [])
        print(f"\n⚠️ 發現 {len(issues)} 個問題:")
        for i, issue in enumerate(issues, 1):
            print(f"\n   {i}. {issue['name']} ({issue['severity']})")
            print(f"      描述: {issue['description']}")
            print(f"      違反法規: {issue.get('law', '無')}")
            print(f"      建議: {issue.get('suggested_action', '無')}")
        
        # 顯示改善建議
        suggestions = result.get('suggestions', [])
        print(f"\n💡 改善建議 ({len(suggestions)} 項):")
        for i, sug in enumerate(suggestions, 1):
            print(f"   {i}. {sug}")
        
        # 顯示法規參考
        legal_refs = result.get('legal_refs', [])
        print(f"\n📚 法規參考 ({len(legal_refs)} 條):")
        for i, ref in enumerate(legal_refs[:5], 1):  # 只顯示前5條
            status_emoji = {
                "compliant": "✅",
                "violated": "❌",
                "unknown": "❓"
            }.get(ref.get('compliance_status', 'unknown'), "❓")
            
            print(f"\n   {i}. {status_emoji} {ref.get('law', 'N/A')}")
            print(f"      相關性: {ref.get('relevance', 'N/A')}")
            print(f"      摘要: {ref.get('content_summary', 'N/A')[:80]}...")
        
        # 顯示 RAG 檢索資訊
        print(f"\n🔍 RAG 檢索資訊:")
        print(f"   查詢字串: {rag_meta['rag_query'][:100]}...")
        print(f"   找到法規: {rag_meta['rag_results_count']} 條")
        
        print("\n" + "="*70)
        print("✅ 測試完成")
        print("="*70)
        
    except FileNotFoundError:
        print(f"❌ 找不到圖片檔案: {image_path}")
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()