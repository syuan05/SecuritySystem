# safety_ai.py
import json
from service_utils import call_gemini_api

# 固定場景的法規資料（可隨時擴充）
SCENE_LAWS = {
    "車站大廳": [
        {"law": "大眾運輸系統無障礙設施設置辦法 §9", 
         "reason": "出入口及動線需設置無障礙斜坡、扶手、通道寬度、地面材質等，保障行動不便者安全通行"},
        {"law": "大眾運輸系統無障礙設施設置辦法 §11", 
         "reason": "需設置清楚標示、導盲設施、反光標示等以維護通行安全"},
        {"law": "建築技術規則 §161", 
         "reason": "群眾集散空間需確保通行寬度與防滑安全"},
        {"law": "消防法 §9", 
         "reason": "公共場域需設置明確逃生指示與消防設備"},
        {"law": "高風險場所管理辦法", 
         "reason": "人流密集場所需保持出入口暢通，不得堆放雜物"}
    ],

    "樓梯口": [
        {"law": "建築技術規則 §178", 
         "reason": "樓梯需設置扶手、防滑措施，避免跌倒"},
        {"law": "職安法 §6", 
         "reason": "通道不得堆放物品阻礙行走與逃生"},
        {"law": "消防避難規範", 
         "reason": "樓梯不得作為儲放區，必須保持逃生動線暢通"}
    ],

    "施工場地": [
        {"law": "營造安全衛生設施標準 §5", 
         "reason": "暴露鋼筋、鋼材等應加裝護套、彎折或加蓋以防止刺傷"},
        {"law": "營造安全衛生設施標準 §19", 
         "reason": "2 公尺以上作業需設置護欄、安全網、防墜落設備"},
        {"law": "職業安全衛生法 §12", 
         "reason": "施工區域需設置警示、圍籬及防止誤入措施"},
        {"law": "營造安全衛生設施標準 §306", 
         "reason": "施工動線應防止墜落、滑倒、物體打擊"},
        {"law": "危險物管理辦法", 
         "reason": "工具材料應妥善固定、分類存放，避免傾倒"}
    ],

    "住宅走廊": [
        {"law": "公寓大廈管理條例 §16", 
         "reason": "不得在樓梯間、走廊、防火巷堆置雜物或設置門柵阻礙通行"},
        {"law": "建築物公共安全管理 §8", 
         "reason": "公共通道需保持照明及通行順暢"},
        {"law": "消防法 §9", 
         "reason": "逃生路線不可堆放物品阻礙避難"},
        {"law": "建築技術規則 §159", 
         "reason": "走廊寬度需符合規範，維持安全通行"}
    ],

    "公共廁所": [
        {"law": "無障礙設施設計規範 §63", 
         "reason": "需設置扶手、防滑地面、足夠空間讓行動不便者使用"},
        {"law": "公共衛生場所管理辦法", 
         "reason": "地面需保持乾燥並確保排水良好"},
        {"law": "職安法 §6", 
         "reason": "若地面濕滑需設置明顯警示標誌"}
    ]
}


def analyze_image_with_gemini(image_base64, location_type, custom_prompt=""):

    # 如果使用者選了已知場景
    laws = SCENE_LAWS.get(location_type, None)

    if laws:
        # ⭐ 已知場景：使用固定法規
        laws_text = "\n".join(
            [f"- {item['law']}: {item['reason']}" for item in laws]
        )
        law_prompt = f"此場域應遵守的法規如下：\n{laws_text}\n請嚴格依據上述法規進行評估。"
    else:
        # ⭐ 使用者輸入自訂場景
        law_prompt = f"""
    此場域為使用者自行輸入的「其他」類型。
    請根據圖片與使用者補充資訊推斷應適用的安全法規並進行評估。
    使用者補充資訊：{custom_prompt}
    """

    prompt = f"""
    你是一位台灣職安與公共安全領域的專家。
    請根據圖片內容進行「環境安全」評估，只能評估由環境、設備、設施造成的風險，不得評估個人行為造成的短暫現象。

    場域類型：{location_type}

    {law_prompt}

    ---

    ⚠【強制量化安全評分規則（僅由環境決定，不得由人為行為決定）】

    必須遵守下列打分規則：

    1. 若圖片中環境或設備存在「重大風險」或「明顯違規」，Safety Score 必須落在 0~39。
    重大風險包含：通道被固定物品阻塞、設施設置錯誤、明顯濕滑積水、緊急出口被固定物品遮蔽等。

    2. 若環境中存在「中度安全問題」或「多項輕微問題」，Safety Score 必須落在 40~59。

    3. 若環境僅有 1~2 項輕微問題且不影響通行，Safety Score 必須落在 60~79。

    4. 若環境整潔、動線清楚、無安全風險（即使有人潮、有人拖行李箱），Safety Score 必須落在 80~100。

    ❗ 若圖片中的唯一問題來自「人為行為」而非環境，則 Safety Score 必須 ≥ 80（不可扣分）。

    ---

    ⚠【禁止產生的問題類型】

    以下狀況屬正常人為行為，完全不能列為安全問題（issues）：

    - 旅客拖行李箱、推推車、背包、攜帶行李
    - 旅客短暫停留、排隊、走動
    - 人潮正常通行（只要沒有明顯擁擠或阻塞）
    - 個人行李箱停留於身旁
    - 因人為行為造成的「暫時性視覺阻擋」

    ❗ 若 hazard 與「行李箱」有直接關聯，該問題一律忽略，不得列出。

    只有在以下情況行李箱才可列為 hazard：
    - 行李箱是「無人使用且被放置」於主要通道
    - 並且明顯造成持續阻礙或遮擋設施
    - 若無法確認是否為長時間放置，請視為正常行李箱使用，不得視為問題。

    ---

    ⚠【安全問題產出規則（環境限定）】

    只列出「由環境、設備、設施」造成的風險，例如：
    - 通道被固定物品阻擋
    - 設備損壞
    - 地板濕滑
    - 標示不清楚
    - 動線錯誤
    - 雜物堆放

    不得將任何「人為行為」列為安全問題。

    ---

    ⚠【改善建議產出規則】

    請提供 3~6 項具體、可執行的改善建議，且不得與 issues 重複。

    ---

    ⚠【輸出格式要求】

    請務必只輸出「純 JSON」，不要包含 ```json 或 ``` 等字串。

    JSON 請依下列格式，不可新增或刪除欄位：

    {{
        "safety_score": 0,
        "safety_level": "Excellent | Good | Fair | Poor",
        "summary": "一句話總結安全狀態",
        "issues": [
            {{
                "name": "問題名稱（依圖片判斷）",
                "description": "具體描述（依圖片判斷）",
                "law": "若有適用法規則填寫，否則空字串"
            }}
        ],
        "suggestions": [
            "具體改善建議（3~6項）"
        ],
        "image_url": ""
    }}
    """



    # 呼叫 Gemini API
    raw = call_gemini_api(prompt, image_base64)

    try:
        result_text = raw["candidates"][0]["content"]["parts"][0]["text"]

        # ⭐ 移除 Gemini 常加的包裝：```json ... ```
        cleaned = (
            result_text
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        # ⭐ 嘗試解析 JSON
        parsed = json.loads(cleaned)
        if "legal_refs" not in parsed:
            parsed["legal_refs"] = []

        return parsed, cleaned

    except Exception as e:
        print("❌ Gemini JSON parse error:", e)
        print("🔍 Raw Gemini text:", result_text if 'result_text' in locals() else raw)
        return None, json.dumps(raw)
