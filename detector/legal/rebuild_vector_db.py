import os
import json
import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm


# ============================
# 重新建立向量資料庫
# ============================
class LawVectorBuilder:
    def __init__(self, db_path="./legal_vector_db",
                 model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):

        print("🔧 初始化 Chroma 資料庫（清空並重建）")

        # 刪除舊的 vector DB
        if os.path.exists(db_path):
            import shutil
            shutil.rmtree(db_path)
            print("🗑️ 舊資料庫已清除")

        # 建立新 DB
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name="taiwan_safety_laws"
        )

        print("📥 載入 embedding 模型...")
        self.encoder = SentenceTransformer(model_name)
        print("✅ 初始化完成\n")

    def rebuild_from_json(self, json_path):
        print(f"📄 讀取法規 JSON：{json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            laws = json.load(f)

        print(f"📦 法規數量：{len(laws)}\n")

        batch_size = 100

        for i in tqdm(range(0, len(laws), batch_size)):
            batch = laws[i:i+batch_size]

            documents = []
            metadatas = []
            ids = []

            for item in batch:
                doc_text = f"{item['law_name']} {item['article']}: {item['content']}"
                documents.append(doc_text)

                metadatas.append({
                    "law_name": item["law_name"],
                    "article": item["article"],
                    "content": item["content"],
                    "scenes": json.dumps(item.get("applicable_scenes", []), ensure_ascii=False),
                    "keywords": json.dumps(item.get("keywords", []), ensure_ascii=False),
                    "severity": item.get("severity", "medium"),
                    "source_url": item.get("source_url", "")
                })

                ids.append(item["law_id"])

            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

        print("\n🎉 向量資料庫重建完成")
        print(f"📊 目前共有 {self.collection.count()} 條法規被索引")


# ============================
# 主程式入口
# ============================
if __name__ == "__main__":
    builder = LawVectorBuilder(
        db_path="./legal_vector_db",
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    builder.rebuild_from_json("./law_database/safety_regulations_rag.json")