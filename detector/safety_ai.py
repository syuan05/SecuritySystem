# safety_ai.py
import json
from service_utils import call_gemini_api

# 固定場景的法規資料（可隨時擴充）
SCENE_LAWS = {
    "車站大廳": [
        {"law": "建築技術規則 §161", "reason": "群眾集散空間需確保通行寬度與防滑設施"},
        {"law": "消防法 §9", "reason": "公共場域需設置明確逃生指示與消防設備"},
        {"law": "高風險場所管理辦法", "reason": "人流密集場所需保持出入口暢通"}
    ],
    "樓梯口": [
        {"law": "建築技術規則 §178", "reason": "樓梯需設置扶手、防滑措施"},
        {"law": "職安法 §6", "reason": "通道不得堆放物品阻礙行走"},
        {"law": "消防避難規範", "reason": "樓梯不得作為儲物空間，必須保持逃生動線暢通"}
    ],
    "施工場地": [
        {"law": "職業安全衛生法 §12", "reason": "施工區需確保標示、圍籬完整"},
        {"law": "營造安全衛生設施標準 §306", "reason": "施工動線需防止墜落與打擊"},
        {"law": "危險物管理辦法", "reason": "工具與材料應固定並妥善存放"}
    ],
    "住宅走廊": [
        {"law": "建築物公共安全管理 §8", "reason": "走道不得堆放雜物並需保持照明"},
        {"law": "消防法 §9", "reason": "公共通道需確保逃生路線順暢"},
        {"law": "建築技術規則 §159", "reason": "走廊寬度需符合規定，以維持通行安全"}
    ],
    "公共廁所": [
        {"law": "無障礙設施設計規範 §63", "reason": "廁所需設置扶手與防滑地面"},
        {"law": "公共衛生場所管理辦法", "reason": "地面需保持乾燥避免滑倒風險"},
        {"law": "職安法 §6", "reason": "地面濕滑應有警示標誌"}
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

    # ========= PROMPT 最終版本（強化固定格式，保證返回 JSON） =========
    prompt = f"""
    你是一位台灣職安與公共安全領域的場域安全專家。
    請分析此圖片的安全風險，並依照以下「安全程度評分（越安全分數越高）」標準評估。

    場域類型：{location_type}

    {law_prompt}

    ---

    ⚠【強制安全評分規則（越安全分數越高）】

    請依下列標準給出 Safety Score：

    - 80 ~ 100：Excellent（安全性極佳，無顯著風險）
    - 60 ~ 79：Good（安全性良好，僅有可忽略或輕微問題）
    - 40 ~ 59：Fair（有明顯安全問題，需要改善）
    - 0 ~ 39：Poor（不安全，存在重大危險或違反法規）

    務必以圖片中可觀察到的條件進行評估，不可留白。

    ---

    ⚠【輸出格式要求】  
    請務必只生成「純 JSON」，不可包含 ```json 或 ```。

    JSON 格式請完全依照下列範例，不可新增或移除欄位：

    {{
    "safety_score": 0,
    "safety_level": "Excellent | Good | Fair | Poor",
    "summary": "一句話總結安全狀態",
    "issues": [
        {{"name": "問題名稱", "severity": "Low|Medium|High", "description": "具體描述"}}
    ],
    "legal_refs": [
        {{"law": "適用法規名稱", "reason": "違規或適用原因"}}
    ],
    "suggestions": ["改善建議1", "改善建議2"]
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
        return parsed, cleaned

    except Exception as e:
        print("❌ Gemini JSON parse error:", e)
        print("🔍 Raw Gemini text:", result_text if 'result_text' in locals() else raw)
        return None, json.dumps(raw)
