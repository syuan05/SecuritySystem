# ==========================================
# 完整的法規爬蟲 + RAG 整合系統
# ==========================================
import json
from pathlib import Path
from typing import List, Dict
import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import os
import sys

# 假設你已經用前面的爬蟲下載了法規資料
# 這個腳本負責建立向量資料庫並整合到分析系統


class LawVectorDatabase:
    """法規向量資料庫管理系統"""
    
    def __init__(
        self, 
        db_path="./legal_vector_db",
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ):
        print("🔧 初始化向量資料庫...")
        
        # 初始化 ChromaDB
        self.client = chromadb.PersistentClient(path=db_path)
        
        # 建立或取得集合
        self.collection = self.client.get_or_create_collection(
            name="taiwan_safety_laws",
            metadata={"description": "台灣職安與公共安全法規向量資料庫"}
        )
        
        # 初始化中文嵌入模型
        print("📥 載入語言模型...")
        self.encoder = SentenceTransformer(model_name)
        print("✅ 初始化完成")
    
    def load_and_index_laws(self, json_file: str):
        """
        從 JSON 檔載入法規並建立向量索引
        
        Args:
            json_file: 爬蟲產出的 JSON 檔案路徑
        """
        print(f"\n📂 載入法規資料: {json_file}")
        
        with open(json_file, 'r', encoding='utf-8') as f:
            regulations = json.load(f)
        
        print(f"✅ 載入 {len(regulations)} 條法規")
        
        # 批次處理
        batch_size = 100
        total_batches = (len(regulations) + batch_size - 1) // batch_size
        
        print("\n🔄 開始建立向量索引...")
        
        for batch_idx in tqdm(range(0, len(regulations), batch_size), 
                             total=total_batches,
                             desc="索引進度"):
            batch = regulations[batch_idx:batch_idx + batch_size]
            
            documents = []
            metadatas = []
            ids = []
            
            for reg in batch:
                # 組合完整文本用於向量化
                doc_text = f"{reg['law_name']} {reg['article']}: {reg['content']}"
                documents.append(doc_text)
                
                # 準備元資料
                metadatas.append({
                    "law_name": reg["law_name"],
                    "article": reg["article"],
                    "content": reg["content"],
                    "pcode": reg.get("pcode", ""),
                    "category": reg.get("category", ""),
                    "scenes": json.dumps(reg.get("applicable_scenes", []), ensure_ascii=False),
                    "keywords": json.dumps(reg.get("keywords", []), ensure_ascii=False),
                    "severity": reg.get("severity", "medium"),
                    "source_url": reg.get("source_url", "")
                })
                
                ids.append(reg["law_id"])
            
            # 加入到向量資料庫
            try:
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
            except Exception as e:
                print(f"⚠️ 批次 {batch_idx//batch_size + 1} 處理失敗: {e}")
        
        print(f"\n✅ 向量索引建立完成！共 {self.collection.count()} 條法規")
    
    def search(
        self, 
        query: str,
        scene_filter: str = None,
        severity_filter: str = None,
        top_k: int = 5,
        min_score: float = 0.3
    ) -> List[Dict]:
        """
        語意搜尋法規
        
        Args:
            query: 查詢文本（場景描述、問題描述）
            scene_filter: 場景過濾（如 "車站大廳"）
            severity_filter: 嚴重程度過濾 ("high", "medium", "low")
            top_k: 返回前 k 條結果
            min_score: 最低相似度門檻
        
        Returns:
            相關法規列表
        """
        # 建構過濾條件
        where_filter = {}
        if severity_filter:
            where_filter["severity"] = severity_filter
        
        # 執行搜尋
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k * 2,  # 多取一些再過濾
            where=where_filter if where_filter else None
        )
        
        # 處理結果
        regulations = []
        
        if results['distances'][0]:
            for doc, meta, distance in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                similarity = 1 - distance
                
                # 場景過濾
                if scene_filter:
                    scenes = json.loads(meta.get('scenes', '[]'))
                    if scene_filter not in scenes and "一般場所" not in scenes:
                        continue
                
                # 相似度過濾
                if similarity < min_score:
                    continue
                
                regulations.append({
                    "law": f"{meta['law_name']} {meta['article']}",
                    "content": meta['content'],
                    "similarity_score": round(similarity, 3),
                    "severity": meta['severity'],
                    "applicable_scenes": json.loads(meta['scenes']),
                    "keywords": json.loads(meta.get('keywords', '[]')),
                    "source_url": meta.get('source_url', '')
                })
                
                if len(regulations) >= top_k:
                    break
        
        return regulations
    
    def get_stats(self) -> Dict:
        """取得資料庫統計資訊"""
        count = self.collection.count()
        
        # 取樣分析
        sample = self.collection.get(limit=min(1000, count))
        
        stats = {
            "total_regulations": count,
            "severity_distribution": {},
            "scene_distribution": {}
        }
        
        for meta in sample['metadatas']:
            # 統計嚴重程度
            severity = meta.get('severity', 'unknown')
            stats["severity_distribution"][severity] = \
                stats["severity_distribution"].get(severity, 0) + 1
            
            # 統計場景
            scenes = json.loads(meta.get('scenes', '[]'))
            for scene in scenes:
                stats["scene_distribution"][scene] = \
                    stats["scene_distribution"].get(scene, 0) + 1
        
        return stats


# ==========================================
# 整合到安全分析系統
# ==========================================
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from service_utils import call_gemini_api

class RAGSafetyAnalyzer:
    """基於 RAG 的環境安全分析系統"""
    
    def __init__(self, law_db: LawVectorDatabase):
        self.law_db = law_db
    
    def analyze(
        self,
        image_base64: str,
        location_type: str,
        custom_prompt: str = ""
    ) -> Dict:
        """
        完整分析流程
        
        1. Gemini 場景理解
        2. RAG 法規檢索
        3. Gemini 深度安全分析
        """
        
        print(f"\n🔍 開始分析: {location_type}")
        
        # === Step 1: 場景理解 ===
        print("  [1/3] 場景理解中...")
        scene_prompt = f"""
        請分析這張圖片的場景，輸出 JSON 格式（不要包含 ```json）：
        {{
            "scene_summary": "場景簡述（1-2句話）",
            "safety_keywords": ["關鍵詞1", "關鍵詞2", ...],
            "potential_risks": ["可能風險1", "可能風險2", ...]
        }}
        
        場域類型：{location_type}
        """
        
        scene_result = call_gemini_api(scene_prompt, image_base64)
        scene_text = scene_result["candidates"][0]["content"]["parts"][0]["text"]
        
        try:
            scene_data = json.loads(
                scene_text.replace("```json", "").replace("```", "").strip()
            )
        except:
            scene_data = {
                "scene_summary": "無法解析場景",
                "safety_keywords": [],
                "potential_risks": []
            }
        
        # === Step 2: RAG 法規檢索 ===
        print("  [2/3] 檢索相關法規...")
        
        query = " ".join([
            location_type,
            scene_data.get("scene_summary", ""),
            custom_prompt,
            " ".join(scene_data.get("safety_keywords", []))
        ])
        
        relevant_laws = self.law_db.search(
            query=query,
            scene_filter=location_type if location_type != "其他" else None,
            top_k=10,
            min_score=0.35
        )
        
        print(f"    找到 {len(relevant_laws)} 條相關法規")
        
        # === Step 3: 深度安全分析 ===
        print("  [3/3] 生成安全報告...")
        
        # 組織法規上下文
        if relevant_laws:
            laws_context = "\n".join([
                f"【法規 {i+1}】{law['law']}（相關度：{law['similarity_score']}）\n"
                f"  內容：{law['content']}\n"
                f"  嚴重程度：{law['severity']}"
                for i, law in enumerate(relevant_laws[:8])
            ])
            law_instruction = f"""
=== 相關法規依據 ===
{laws_context}

請依據上述法規評估圖片中的環境安全狀況。
"""
        else:
            law_instruction = f"""
場域：{location_type}
RAG 系統未找到直接相關法規，請依常識與一般安全原則評估。
使用者補充：{custom_prompt}
"""
        
        # 最終分析
        final_prompt = f"""
你是台灣職安與公共安全專家，請評估圖片中的「環境安全」。

=== 場景理解結果 ===
{scene_data.get('scene_summary', '')}
可能風險：{', '.join(scene_data.get('potential_risks', []))}

{law_instruction}

=== 評估規則 ===
1. 只評估「環境、設施、設備」的風險，不評估人為行為
2. 評分標準：
   - 0-39分：重大風險（通道阻塞、設施損壞、明顯違規）
   - 40-59分：中度問題（多項輕微問題）
   - 60-79分：輕微問題（1-2項不影響通行）
   - 80-100分：安全良好

3. 禁止列為問題：
   - 旅客攜帶行李、背包
   - 正常人流通行
   - 短暫停留、排隊

輸出純 JSON（不要包含 ```json）：
{{
    "safety_score": 0,
    "safety_level": "Excellent | Good | Fair | Poor",
    "summary": "一句話總結",
    "issues": [
        {{
            "name": "問題名稱",
            "description": "具體描述",
            "law": "違反法規（若有）",
            "severity": "high|medium|low",
            "suggested_action": "建議措施"
        }}
    ],
    "suggestions": ["改善建議1", "改善建議2", ...],
    "legal_refs": [
        {{
            "law": "法規名稱",
            "relevance": "相關性說明",
            "compliance_status": "compliant|violated|unknown"
        }}
    ]
}}
"""
        
        result = call_gemini_api(final_prompt, image_base64)
        result_text = result["candidates"][0]["content"]["parts"][0]["text"]
        
        try:
            analysis = json.loads(
                result_text.replace("```json", "").replace("```", "").strip()
            )
            
            # 補充 RAG 檢索到的法規
            if not analysis.get("legal_refs"):
                analysis["legal_refs"] = [
                    {
                        "law": law["law"],
                        "relevance": f"RAG 相關度 {law['similarity_score']}",
                        "compliance_status": "unknown",
                        "source_url": law.get("source_url", "")
                    }
                    for law in relevant_laws[:5]
                ]
            
            # 補充場景理解資訊
            analysis["scene_analysis"] = scene_data
            
            return analysis
            
        except Exception as e:
            print(f"❌ 解析失敗: {e}")
            return {
                "error": str(e),
                "raw_response": result_text
            }


# ==========================================
# 完整使用範例
# ==========================================
def setup_complete_system():
    """
    完整系統建置流程
    
    步驟：
    1. 執行法規爬蟲（使用 law_crawler_system.py）
    2. 建立向量資料庫
    3. 測試 RAG 檢索
    """
    
    print("=" * 70)
    print("🏗️  建置 RAG 法規分析系統")
    print("=" * 70)
    
    # Step 1: 初始化向量資料庫
    law_db = LawVectorDatabase(
        db_path="./legal_vector_db",
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    
    # Step 2: 載入爬蟲產出的法規資料
    json_file = "./law_database/safety_regulations_rag.json"
    
    if Path(json_file).exists():
        law_db.load_and_index_laws(json_file)
    else:
        print(f"❌ 找不到法規資料檔: {json_file}")
        print("   請先執行 law_crawler_system.py 下載法規資料")
        return None
    
    # Step 3: 顯示統計資訊
    stats = law_db.get_stats()
    print("\n" + "=" * 70)
    print("📊 資料庫統計")
    print("=" * 70)
    print(f"總法規數: {stats['total_regulations']}")
    print("\n嚴重程度分布:")
    for severity, count in stats['severity_distribution'].items():
        print(f"  {severity}: {count}")
    print("\n場景分布 (前10):")
    for scene, count in sorted(
        stats['scene_distribution'].items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:10]:
        print(f"  {scene}: {count}")
    
    # Step 4: 測試檢索
    print("\n" + "=" * 70)
    print("🧪 測試 RAG 檢索")
    print("=" * 70)
    
    test_queries = [
        ("車站大廳有行李箱堆放", "車站大廳"),
        ("樓梯沒有扶手", "樓梯口"),
        ("施工現場鋼筋外露", "施工場地")
    ]
    
    for query, scene in test_queries:
        print(f"\n查詢: {query} (場景: {scene})")
        results = law_db.search(query, scene_filter=scene, top_k=3)
        
        for i, law in enumerate(results, 1):
            print(f"  [{i}] {law['law']} (相關度: {law['similarity_score']})")
            print(f"      {law['content'][:60]}...")
    
    print("\n✅ 系統建置完成！")
    return law_db


def test_analysis(law_db: LawVectorDatabase, image_base64: str):
    """測試完整分析流程"""
    
    analyzer = RAGSafetyAnalyzer(law_db)
    
    result = analyzer.analyze(
        image_base64=image_base64,
        location_type="車站大廳",
        custom_prompt="尖峰時段，人潮較多"
    )
    
    print("\n" + "=" * 70)
    print("📋 分析結果")
    print("=" * 70)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # 建置系統
    law_db = setup_complete_system()
    
    # 測試分析（需要提供圖片 base64）
    # test_analysis(law_db, your_image_base64)
