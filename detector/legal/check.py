# test_rag.py
from rag_system import LawVectorDatabase

db = LawVectorDatabase(db_path="./legal_vector_db")

# 測試搜尋
results = db.search("走廊堆積雜物", mode="keyword", top_k=3)

print("測試結果:")
for i, r in enumerate(results, 1):
    print(f"{i}. {r['law']}")
    print(f"   分數: {r.get('keyword_score', 0):.3f}")
    print()

# 預期結果：第一名應該是「公寓大廈管理條例 第 16 條」