# rag_system.py — 改良版法規向量資料庫搜尋系統
import os
import json
import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional

class LawVectorDatabase:
    """改良版法規向量資料庫 - 支援混合搜尋"""

    def __init__(self, db_path="./legal_vector_db",
                 model_name="shibing624/text2vec-base-chinese"):
        print("🔧 初始化法規向量資料庫...")

        # ChromaDB persistent DB
        self.client = chromadb.PersistentClient(path=db_path)

        # 取得集合
        self.collection = self.client.get_or_create_collection(
            name="taiwan_safety_laws"
        )

        # 載入 embedding 模型
        print("📥 載入 embedding 模型...")
        self.encoder = SentenceTransformer(model_name)

        # 檢查資料庫狀態
        count = self.collection.count()
        print(f"✅ RAG 系統初始化完成 | 資料庫共有 {count} 筆法規\n")

    def diagnose_database(self, keywords: List[str], limit=500):
        """診斷資料庫內容 - 檢查是否包含特定關鍵字"""
        print(f"🔍 診斷資料庫：檢查關鍵字 {keywords}")
        
        sample = self.collection.get(limit=limit)
        found_laws = []

        for meta in sample["metadatas"]:
            content = meta.get("content", "")
            law_name = meta.get("law_name", "")
            article = meta.get("article", "")
            
            # 檢查是否包含任一關鍵字
            matched_keywords = [kw for kw in keywords if kw in content or kw in law_name]
            
            if matched_keywords:
                found_laws.append({
                    "law": f"{law_name} {article}",
                    "content": content,
                    "matched_keywords": matched_keywords
                })

        if found_laws:
            print(f"✅ 找到 {len(found_laws)} 筆相關法規\n")
            for i, law in enumerate(found_laws[:10], 1):
                print(f"{i}. {law['law']}")
                print(f"   匹配關鍵字: {', '.join(law['matched_keywords'])}")
                print(f"   內容預覽: {law['content'][:80]}...\n")
        else:
            print(f"❌ 資料庫前 {limit} 筆中未找到包含 {keywords} 的法規\n")
            print("💡 建議：")
            print("   1. 檢查原始資料是否包含相關法規")
            print("   2. 確認資料建立流程是否正確")
            print("   3. 嘗試使用更廣泛的關鍵字\n")
        
        return found_laws

    def vector_search(self, query: str, scene_filter: Optional[str] = None, 
                     top_k: int = 5, min_similarity: float = 0.4):
        """純向量搜尋（帶領域擴展）"""
        
        # 🔥 精準的領域關鍵字擴展
        DOMAIN_EXPANSION = {
            "走廊": "走廊 通道 公寓大廈管理條例 堆置物品 避難逃生 防火巷 樓梯間 共用空間",
            "堆積": "堆置 雜物 障礙物 通道阻塞 占用 違建 共用部分 物品放置",
            "雜物": "雜物 廢棄物 堆置 障礙 阻塞 占用 妨礙通行",
            "鋼筋": "鋼筋外露 裸露鋼筋 保護層 鋼筋混凝土 施工品質 結構安全 鋼筋護套 營造安全",
            "滑倒": "滑倒 濕滑 地面積水 防滑 地板材質 止滑 跌倒 地面濕滑",
            "消防": "消防 滅火器 逃生指示 防火避難 消防法 火警 避難設備",
            "樓梯": "樓梯 階梯 扶手 樓梯間 緊急逃生 避難通道",
        }
        
        # 建立擴展查詢
        expanded = query
        for key, extra in DOMAIN_EXPANSION.items():
            if key in query:
                expanded = f"{query} {extra}"
                break
        
        # 如果沒有匹配到特定領域，加上通用擴展
        if expanded == query:
            expanded += " 安全 建築 法規 條文 違規"
        
        print(f"🔍 向量搜尋：{query}")
        print(f"   擴展查詢：{expanded}\n")
        
        # 查詢向量資料庫
        result = self.collection.query(
            query_texts=[expanded],
            n_results=top_k * 3
        )

        if not result["documents"]:
            print("⚠️ 查無資料")
            return []

        # 整理結果
        regulations = []
        for doc, meta, dist in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0]
        ):
            sim = round(1 - dist, 3)
            
            # 過濾低相似度結果
            if sim < min_similarity:
                continue
            
            scenes = json.loads(meta.get("scenes", "[]"))
            
            regulations.append({
                "law": f"{meta.get('law_name', '')} {meta.get('article', '')}",
                "content": meta.get("content", ""),
                "similarity": sim,
                "scenes": scenes,
                "severity": meta.get("severity", "unknown"),
            })

        # 場景過濾
        if scene_filter:
            filtered = [x for x in regulations if scene_filter in x["scenes"]]
            if filtered:
                return sorted(filtered, key=lambda x: x["similarity"], reverse=True)[:top_k]

        # 按相似度排序
        return sorted(regulations, key=lambda x: x["similarity"], reverse=True)[:top_k]

    def keyword_search(self, query: str, top_k: int = 10, search_limit: int = 2000):
        """關鍵字全文搜尋（增強版）"""
        # 拆解查詢為字級別（因為中文分詞可能不準）
        keywords = list(query)  # 字級搜尋
        # 同時保留詞級搜尋
        if ' ' in query:
            keywords.extend(query.split())
        else:
            # 嘗試常見的雙字詞組合
            for i in range(len(query) - 1):
                keywords.append(query[i:i+2])
        
        keywords = list(set(keywords))  # 去重
        all_data = self.collection.get(limit=search_limit)
        
        keyword_results = []
        for meta in all_data["metadatas"]:
            content = meta.get("content", "")
            law_name = meta.get("law_name", "")
            article = meta.get("article", "")
            
            # 計算關鍵字匹配度
            match_count = sum(1 for kw in keywords if kw in content or kw in law_name)
            
            if match_count > 0:
                keyword_results.append({
                    "law": f"{law_name} {article}",
                    "content": content,
                    "keyword_score": match_count / len(keywords),
                    "match_count": match_count,
                    "scenes": json.loads(meta.get("scenes", "[]")),
                    "severity": meta.get("severity", "unknown")
                })
        
        # 按匹配度排序
        return sorted(keyword_results, key=lambda x: x["match_count"], reverse=True)[:top_k]

    def hybrid_search(self, query: str, scene_filter: Optional[str] = None, 
                     top_k: int = 5, vector_weight: float = 0.1):
        """混合搜尋：向量搜尋 + 關鍵字搜尋（關鍵字權重 90%）"""
        print(f"🔍 混合搜尋：{query}")
        print(f"   向量權重: {vector_weight} | 關鍵字權重: {1-vector_weight}\n")
        
        # 1. 向量搜尋
        vector_results = self.vector_search(query, scene_filter=scene_filter, 
                                           top_k=top_k*2, min_similarity=0.3)
        
        # 2. 關鍵字搜尋
        keyword_results = self.keyword_search(query, top_k=top_k*2)
        
        # 3. 合併結果
        combined = {}
        
        # 向量搜尋結果
        for r in vector_results:
            law_key = r["law"]
            combined[law_key] = {
                **r,
                "vector_score": r["similarity"],
                "keyword_score": 0,
                "final_score": r["similarity"] * vector_weight
            }
        
        # 關鍵字搜尋結果
        keyword_weight = 1 - vector_weight
        for r in keyword_results:
            law_key = r["law"]
            if law_key in combined:
                combined[law_key]["keyword_score"] = r["keyword_score"]
                combined[law_key]["final_score"] += r["keyword_score"] * keyword_weight
            else:
                combined[law_key] = {
                    **r,
                    "vector_score": 0,
                    "similarity": 0,
                    "final_score": r["keyword_score"] * keyword_weight
                }
        
        # 場景過濾
        if scene_filter:
            filtered = {k: v for k, v in combined.items() if scene_filter in v.get("scenes", [])}
            if filtered:
                combined = filtered
        
        # 按最終分數排序
        results = sorted(combined.values(), key=lambda x: x["final_score"], reverse=True)
        return results[:top_k]

    def search(self, query: str, mode: str = "keyword", **kwargs):
        """統一搜尋介面（預設純關鍵字）"""
        if mode == "vector":
            return self.vector_search(query, **kwargs)
        elif mode == "hybrid":
            return self.hybrid_search(query, **kwargs)
        else:  # keyword (預設)
            return self.keyword_search(query, **kwargs)


# ==================== 使用範例 ====================

if __name__ == "__main__":
    # 初始化資料庫
    db = LawVectorDatabase(
        db_path="./legal_vector_db",
        model_name="shibing624/text2vec-base-chinese"
    )

    print("=" * 60)
    print("步驟 1: 診斷資料庫內容")
    print("=" * 60)
    
    # 診斷資料庫
    db.diagnose_database(
        keywords=["走廊", "堆積", "雜物", "通道", "公寓大廈"],
        limit=500
    )

    print("\n" + "=" * 60)
    print("步驟 2: 測試不同搜尋模式")
    print("=" * 60)

    test_queries = [
        "走廊堆積雜物",
        "鋼筋外露",
        "樓梯間堆放物品",
        "消防通道阻塞"
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"查詢: {query}")
        print(f"{'='*60}")
        
        # 混合搜尋
        results = db.search(query, mode="hybrid", top_k=3)
        
        if results:
            for i, r in enumerate(results, 1):
                print(f"\n{i}. {r['law']}")
                print(f"   最終分數: {r.get('final_score', 0):.3f} "
                      f"(向量: {r.get('vector_score', 0):.3f}, "
                      f"關鍵字: {r.get('keyword_score', 0):.3f})")
                print(f"   場景: {', '.join(r.get('scenes', []))}")
                print(f"   內容: {r['content'][:100]}...")
        else:
            print("   ❌ 無相關結果")
            print("\n   💡 可能原因：")
            print("      1. 資料庫中沒有相關法規")
            print("      2. 關鍵字太具體或太模糊")
            print("      3. embedding 模型無法理解查詢語義")

    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)