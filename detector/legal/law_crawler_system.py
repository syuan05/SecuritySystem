# ==========================================
# 全國法規資料庫爬蟲系統 (修正版)
# 使用政府資料開放平台的資料集
# ==========================================
import requests
import json
import time
import re
import zipfile
import io
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import xml.etree.ElementTree as ET

class TaiwanLawCrawler:
    """
    台灣全國法規資料庫爬蟲 (修正版)
    資料來源：政府資料開放平台 data.gov.tw
    """
    
    def __init__(self, output_dir="./law_data"):
        # 政府資料開放平台的法規資料集
        self.law_dataset_url = "https://law.moj.gov.tw/Law/LawSearchResult.aspx?ty=ONEBAR&kw="
        
        # 使用政府開放資料平台的下載連結
        self.datasets = {
            "law": "https://data.moj.gov.tw/opendata/GetFile?FileId=A14001",  # 法律
            "rule": "https://data.moj.gov.tw/opendata/GetFile?FileId=A14002"  # 命令
        }
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def download_laws_from_opendata(self, data_type="law") -> List[Dict]:
        """
        從政府資料開放平台下載法規資料
        
        Args:
            data_type: "law" (法律) 或 "rule" (命令)
        """
        print(f"📥 開始下載{data_type}類法規資料...")
        
        url = self.datasets.get(data_type)
        if not url:
            print(f"❌ 未知的資料類型: {data_type}")
            return []
        
        try:
            # 下載 ZIP 檔
            print(f"  下載中: {url}")
            response = requests.get(url, timeout=300, stream=True)
            response.raise_for_status()
            
            # 解壓縮
            laws_data = []
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                # 解壓所有檔案
                extract_path = self.output_dir / "raw" / data_type
                extract_path.mkdir(parents=True, exist_ok=True)
                z.extractall(extract_path)
                
                print(f"✅ 解壓縮完成: {extract_path}")
                
                # 讀取 JSON 檔案
                json_files = list(extract_path.glob("*.json"))
                
                if json_files:
                    for json_file in json_files:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            try:
                                data = json.load(f)
                                if isinstance(data, list):
                                    laws_data.extend(data)
                                else:
                                    laws_data.append(data)
                            except json.JSONDecodeError as e:
                                print(f"⚠️ JSON 解析失敗: {json_file.name}, {e}")
                
                print(f"✅ 成功載入 {len(laws_data)} 條法規")
                return laws_data
                
        except Exception as e:
            print(f"❌ 下載失敗: {e}")
            return []
    
    def download_all_laws(self) -> Dict[str, List]:
        """下載所有類型的法規"""
        all_laws = {
            "law": self.download_laws_from_opendata("law"),
            "rule": self.download_laws_from_opendata("rule")
        }
        
        total = sum(len(laws) for laws in all_laws.values())
        print(f"\n✅ 總共下載 {total} 條法規")
        print(f"  - 法律: {len(all_laws['law'])} 條")
        print(f"  - 命令: {len(all_laws['rule'])} 條")
        
        return all_laws
    
    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """
        使用全國法規資料庫的搜尋功能
        (備用方案，如果 API 失效可用網頁爬蟲)
        """
        print(f"🔍 搜尋關鍵字: {keyword}")
        
        # 這裡可以實作網頁爬蟲
        # 但建議優先使用 download_laws_from_opendata
        
        return []


class SafetyLawProcessor:
    """
    安全相關法規處理器
    """
    
    # 安全相關關鍵字
    SAFETY_KEYWORDS = [
        # 職業安全
        "職業安全", "職安", "勞工安全", "工作安全",
        "營造安全", "施工安全", "作業安全",
        
        # 建築安全
        "建築技術", "建築管理", "建築法", "建築設計",
        "無障礙", "公寓大廈", 
        
        # 消防安全
        "消防法", "火災", "逃生", "避難", "滅火",
        "消防設備", "防火",
        
        # 公共安全
        "公共安全", "公共衛生", "衛生管理",
        "大眾運輸", "交通安全", 
        
        # 設施設備
        "電梯", "升降", "機械", "電氣",
        "護欄", "扶手", "通道", "樓梯",
        
        # 危險管理
        "危險物", "高風險", "高處作業",
        "墜落", "倒塌", "爆炸"
    ]
    
    def __init__(self, crawler: TaiwanLawCrawler):
        self.crawler = crawler
        self.safety_laws = []
    
    def extract_safety_laws(self, all_laws: Dict[str, List]) -> List[Dict]:
        """從所有法規中篩選出安全相關法規"""
        print("\n🔍 開始篩選安全相關法規...")
        
        safety_laws = []
        
        for law_type, laws in all_laws.items():
            print(f"  處理 {law_type} 類法規...")
            
            for law in laws:
                # 取得法規名稱
                law_name = law.get("法規名稱") or law.get("LawName") or ""
                
                # 檢查是否包含安全關鍵字
                if any(keyword in law_name for keyword in self.SAFETY_KEYWORDS):
                    law["law_type"] = law_type
                    safety_laws.append(law)
        
        self.safety_laws = safety_laws
        print(f"✅ 找到 {len(safety_laws)} 條安全相關法規")
        return safety_laws
    
    def process_law_to_rag_format(self, law: Dict) -> List[Dict]:
        """
        將法規轉換為 RAG 格式
        每一條文拆成獨立的文件單元
        """
        regulations = []
        
        # 提取基本資訊
        law_name = law.get("法規名稱") or law.get("LawName") or ""
        pcode = law.get("法規編號") or law.get("PCode") or ""
        law_category = law.get("法規類別") or law.get("LawCategory") or ""
        
        # 解析條文內容
        # 根據實際資料格式調整
        articles_text = law.get("法規內容") or law.get("LawArticles") or ""
        
        # 如果是字串，嘗試按條文分割
        if isinstance(articles_text, str):
            articles = self._parse_articles_from_text(articles_text)
        elif isinstance(articles_text, list):
            articles = articles_text
        else:
            articles = []
        
        for idx, article in enumerate(articles, 1):
            if isinstance(article, dict):
                article_no = article.get("條號") or article.get("ArticleNo") or f"第{idx}條"
                content = article.get("條文內容") or article.get("ArticleContent") or ""
            else:
                # 如果是字串，嘗試解析
                article_no = f"第{idx}條"
                content = str(article)
            
            # 清理內容
            content = self._clean_text(content)
            
            if not content or len(content) < 10:
                continue
            
            # 生成唯一 ID
            law_id = f"{pcode}_{idx}" if pcode else f"{law_name}_{idx}"
            law_id = re.sub(r'[^\w\-]', '_', law_id)
            
            # 提取關鍵字
            keywords = self._extract_keywords(content)
            
            # 判斷適用場景
            scenes = self._infer_applicable_scenes(law_name, content)
            
            # 判斷嚴重程度
            severity = self._infer_severity(content)
            
            regulations.append({
                "law_id": law_id,
                "law_name": law_name,
                "article": article_no,
                "content": content,
                "pcode": pcode,
                "category": law_category,
                "applicable_scenes": scenes,
                "keywords": keywords,
                "severity": severity,
                "source_url": f"https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode={pcode}" if pcode else ""
            })
        
        return regulations
    
    def _parse_articles_from_text(self, text: str) -> List[str]:
        """從文本中解析條文"""
        # 嘗試按「第XX條」分割
        pattern = r'第[\d一二三四五六七八九十百千]+條'
        articles = re.split(pattern, text)
        
        # 移除空白和過短的片段
        articles = [a.strip() for a in articles if len(a.strip()) > 10]
        
        return articles
    
    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除多餘空白
        text = re.sub(r'\s+', ' ', text)
        # 移除特殊字元但保留中文標點
        text = re.sub(r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\w\s.,;:()、，。；：「」『』（）]', '', text)
        return text.strip()
    
    def _extract_keywords(self, content: str) -> List[str]:
        """從內容中提取關鍵字"""
        keywords = set()
        
        keyword_patterns = [
            r'(護欄|扶手|欄杆|圍籬|防護網)',
            r'(通道|走廊|樓梯|階梯|斜坡)',
            r'(標示|標誌|警示|指示)',
            r'(照明|燈光|採光)',
            r'(電梯|升降機|手扶梯)',
            r'(防滑|止滑|防護)',
            r'(防墜|防墜落|墜落)',
            r'(消防|滅火|逃生|避難)',
            r'(安全帽|安全帶|防護具)',
            r'(施工|工地|營造)',
            r'(公共場所|公共空間)',
            r'(廁所|盥洗室)',
            r'(車站|機場|港口)',
            r'(鋼筋|鋼材|尖銳)',
            r'(高處作業|高度)',
            r'(堆置|堆放|雜物)',
            r'(積水|濕滑|漏水)'
        ]
        
        for pattern in keyword_patterns:
            matches = re.findall(pattern, content)
            keywords.update(matches)
        
        return list(keywords)[:10]
    
    def _infer_applicable_scenes(self, law_name: str, content: str) -> List[str]:
        """推斷適用場景"""
        scenes = []
        
        scene_mapping = {
            "車站大廳": ["車站", "大廳", "候車", "運輸系統"],
            "樓梯口": ["樓梯", "階梯", "扶手"],
            "施工場地": ["施工", "營造", "工地", "作業"],
            "住宅走廊": ["住宅", "公寓", "走廊", "通道"],
            "公共廁所": ["廁所", "盥洗", "衛生"],
            "公共空間": ["公共場所", "集會"],
            "電梯": ["電梯", "升降"],
            "停車場": ["停車"],
            "高處作業": ["高處", "高度"]
        }
        
        combined_text = law_name + content
        
        for scene, keywords in scene_mapping.items():
            if any(kw in combined_text for kw in keywords):
                scenes.append(scene)
        
        return scenes if scenes else ["一般場所"]
    
    def _infer_severity(self, content: str) -> str:
        """推斷嚴重程度"""
        high_risk_keywords = [
            "死亡", "重傷", "墜落", "倒塌", "爆炸",
            "禁止", "不得", "嚴禁", "必須", "應設置"
        ]
        
        medium_risk_keywords = [
            "危險", "風險", "注意", "應", "需"
        ]
        
        if any(kw in content for kw in high_risk_keywords):
            return "high"
        elif any(kw in content for kw in medium_risk_keywords):
            return "medium"
        else:
            return "low"


# ==========================================
# 主要執行流程
# ==========================================
def main():
    """完整的法規爬取與處理流程"""
    
    print("=" * 60)
    print("🏛️  台灣安全法規資料庫建置系統")
    print("=" * 60)
    
    # 初始化爬蟲
    crawler = TaiwanLawCrawler(output_dir="./law_database")
    processor = SafetyLawProcessor(crawler)
    
    # Step 1: 下載所有法規
    print("\n[步驟 1/4] 下載法規資料...")
    all_laws = crawler.download_all_laws()
    
    if not all_laws or (not all_laws.get("law") and not all_laws.get("rule")):
        print("❌ 無法下載法規資料")
        print("\n💡 替代方案:")
        print("1. 手動下載: https://data.gov.tw/dataset/18289")
        print("2. 或使用 GitHub 開源專案: https://github.com/kong0107/mojLawSplitJSON")
        return
    
    # Step 2: 篩選安全相關法規
    print("\n[步驟 2/4] 篩選安全相關法規...")
    safety_laws = processor.extract_safety_laws(all_laws)
    
    # 儲存篩選結果
    output_list = "./law_database/safety_laws_list.json"
    with open(output_list, "w", encoding="utf-8") as f:
        json.dump(safety_laws, f, ensure_ascii=False, indent=2)
    print(f"✅ 篩選結果已儲存: {output_list}")
    
    # Step 3: 處理詳細內容
    print("\n[步驟 3/4] 處理法規條文...")
    all_regulations = []
    
    for i, law in enumerate(safety_laws, 1):
        law_name = law.get("法規名稱") or law.get("LawName") or "未知法規"
        print(f"  [{i}/{len(safety_laws)}] 處理: {law_name}")
        
        regulations = processor.process_law_to_rag_format(law)
        all_regulations.extend(regulations)
    
    print(f"✅ 共處理 {len(all_regulations)} 條法規條文")
    
    # Step 4: 儲存結果
    print("\n[步驟 4/4] 儲存結果...")
    output_file = "./law_database/safety_regulations_rag.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_regulations, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 法規資料已儲存至: {output_file}")
    
    # 生成統計報告
    print("\n" + "=" * 60)
    print("📊 處理統計")
    print("=" * 60)
    print(f"總法規數: {len(safety_laws)}")
    print(f"已處理條文數: {len(all_regulations)}")
    
    # 場景分布
    scene_count = {}
    for reg in all_regulations:
        for scene in reg["applicable_scenes"]:
            scene_count[scene] = scene_count.get(scene, 0) + 1
    
    print("\n場景分布:")
    for scene, count in sorted(scene_count.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  - {scene}: {count} 條")
    
    print("\n✨ 完成! 可以開始建立 RAG 向量資料庫了")


if __name__ == "__main__":
    main()
