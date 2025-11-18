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
    你是一位台灣職安與公共安全領域的專家。
    請根據圖片內容評估實際可觀察到的安全風險（不可猜測不可虛構），並提供具體的問題與改善建議。

    場域類型：{location_type}

    {law_prompt}

    ---

    ⚠【安全評分標準（越安全分數越高）】

    請依下列標準給出 Safety Score：

    - 80 ~ 100：Excellent（安全性極佳，無顯著風險）
    - 60 ~ 79：Good（安全性良好，僅有輕微問題）
    - 40 ~ 59：Fair（有明顯安全問題，需改善）
    - 0 ~ 39：Poor（不安全，存在重大危險或明顯違規情形）

    請務必根據「圖片中確實可看到的內容」進行評估，不可加入推測或無法驗證的假設。

    ---

    ⚠【安全問題產出規則】

    請從圖片中辨識可能的危害，例如（僅作示例，不得寫死）：
    - 地板濕滑
    - 堆置雜物
    - 通道被阻擋
    - 動線混亂
    - 逃生出口不明顯
    - 照明不足
    - 設備損壞
    - 群眾擁擠

    每一項問題都必須為「圖片可觀察到」的事實。

    若此問題涉及法規，請在該問題的 `law` 欄位寫出法規名稱（例如：建築技術規則 §159）。
    若沒有則留空字串 ""。

    ---

    ⚠【改善建議產出規則】

    請提供 3~6 項具體的改善建議（單一陣列，不分法規/一般）。
    每項建議需具體可行，不可與 issues 重複，不可太籠統（例如「改善環境」）。

    ---

    ⚠【輸出格式要求】

    請務必只輸出「純 JSON」，不要包含 ```json、``` 或其他多餘內容。

    JSON 格式如下，不可增刪欄位：

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
