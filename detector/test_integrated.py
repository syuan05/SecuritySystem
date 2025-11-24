# test_integrated.py
from detector.safety_ai import analyze_image_with_gemini
import base64

# 讀取測試圖片
with open(f"C:\\Users\\syuan\\Pictures\\Screenshots\\1.png", "rb") as f:
    image_data = base64.b64encode(f.read()).decode()

# 執行分析
result, json_str = analyze_image_with_gemini(
    image_base64=image_data,
    location_type="施工場地",
    custom_prompt="",
    use_rag=True  # 啟用 RAG
)

# 顯示結果
if result:
    print("\n" + "="*70)
    print("📊 分析結果")
    print("="*70)
    print(f"\n安全分數: {result.get('safety_score', 'N/A')}")
    print(f"安全等級: {result.get('safety_level', 'N/A')}")
    print(f"總結: {result.get('summary', 'N/A')}")
    
    issues = result.get('issues', [])
    print(f"\n發現 {len(issues)} 個問題：")
    
    for i, issue in enumerate(issues, 1):
        print(f"\n{i}. {issue['name']}")
        print(f"   描述: {issue['description']}")
        
        # 顯示 RAG 找到的法規
        if issue.get('related_laws'):
            print(f"   相關法規 ({issue.get('law_count', 0)} 條):")
            for j, law in enumerate(issue['related_laws'], 1):
                print(f"      {j}. {law['law']}")
                print(f"         {law['content'][:100]}...")
                print(f"         相關度: {law['relevance']:.3f}")
    
    print("\n改善建議:")
    for i, suggestion in enumerate(result.get('suggestions', []), 1):
        print(f"   {i}. {suggestion}")
else:
    print("❌ 分析失敗")