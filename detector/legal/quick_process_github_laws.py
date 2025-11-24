import json
from pathlib import Path

# ========== 你的資料結構（依你上傳的版本） ==========
INDEX_PATH = "./mojLawSplitJSON/index.json"
LAW_SOURCE_PATH = "./mojLawSplitJSON/FalVMingLing"
OUTPUT_PATH = "./law_database"

SAFETY_KEYWORDS = [
    "職業安全", "職安", "營造安全", "施工安全", "勞工安全",
    "建築技術", "建築法", "建築管理", "無障礙", "公寓大廈",
    "消防", "火災", "逃生", "避難", "滅火",
    "公共安全", "大眾運輸", "電梯", "升降",
    "護欄", "扶手", "通道", "樓梯", "衛生管理",
    "危險物", "高處作業", "墜落", "防護"
]


def process_laws():
    print("🔍 掃描法規資料...")

    # --- index.json 是 list，不是 dict ---
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)

    print(f"總共 {len(index)} 條法規")

    all_regulations = []
    safety_laws = []

    # =====================================================
    # ★ 正確方式：遍歷 list，而不是 index.items()
    # =====================================================
    for item in index:
        pcode = item.get("PCode")
        law_name = item.get("name", "")

        if not pcode:
            continue

        # 篩選安全法規
        if not any(kw in law_name for kw in SAFETY_KEYWORDS):
            continue

        safety_laws.append(law_name)
        print(f"  ✓ {law_name}")

        # 正確法規檔案路徑
        law_file = Path(LAW_SOURCE_PATH) / f"{pcode}.json"
        if not law_file.exists():
            continue

        with open(law_file, "r", encoding="utf-8") as f:
            law = json.load(f)

        # ================================
        # ★ 你的法規內容在「法規內容」
        # ================================
        articles = law.get("法規內容", [])

        for idx, article in enumerate(articles, 1):

            # 條號（中文）
            article_no = (
                article.get("條號")
                or f"第{idx}條"
            )

            # 條文內容（中文）
            content = (
                article.get("條文內容")
                or ""
            )

            if len(content.strip()) < 5:
                continue

            all_regulations.append({
                "law_id": f"{pcode}_{idx}",
                "law_name": law_name,
                "article": article_no,
                "content": content,
                "pcode": pcode,
                "source_url": f"https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode={pcode}",
            })

    # ================================
    # 輸出 RAG 資料
    # ================================
    Path(OUTPUT_PATH).mkdir(exist_ok=True)
    out = Path(OUTPUT_PATH) / "safety_regulations_rag.json"

    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_regulations, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 找到 {len(safety_laws)} 條安全法規")
    print(f"✅ 處理 {len(all_regulations)} 條條文")
    print(f"✅ 已儲存: {out}")


if __name__ == "__main__":
    process_laws()
