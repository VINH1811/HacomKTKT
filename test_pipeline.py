import os
import sys
from file_ingester import FileIngester
from normalizer import Normalizer
from comparison_engine import ComparisonEngine
from report_builder import ReportBuilder

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def test():
    folder = r"d:\Thực tập Halcom\code\5. Tong hop chao gia 11.12.2025"
    contractor_files = {
        "Linh Anh": "1. 2025.12.08 Chao gia ME Hacom Mall Linh Anh V2.xlsx",
        "Trí Trung - Văn Lang": "2. 2025.12.09 Chao gia ME Hacom Mall Van Lang Tri Trung V2.xlsx",
        "Searefico": "3. 2025.12.08 Chao gia ME Hacom Mall Searefico V2.xlsx",
        "Vân Khánh": "4. 2025.12.08 Chao gia ME Hacom Mall Van Khanh V2.xlsx"
    }
    
    ingester = FileIngester()
    normalizer = Normalizer()
    engine = ComparisonEngine()
    builder = ReportBuilder()
    
    contractor_data = {}
    
    for name, filename in contractor_files.items():
        path = os.path.join(folder, filename)
        print(f"Ingesting & Normalizing {name} from {filename}...")
        
        # Ingest
        raw_data = ingester.ingest_file(path)
        print(f"  Sheets loaded: {list(raw_data.keys())}")
        
        # Normalize
        normalized = normalizer.normalize(name, raw_data)
        print(f"  Total items extracted: {len(normalized)}")
        
        contractor_data[name] = normalized
        
    print("\nRunning Comparison Engine...")
    results = engine.compare_bids(contractor_data)
    
    print("\nComparison completed successfully!")
    print(f"Total Flags found: {len(results['flags'])}")
    
    print("\n=== Automated Comments preview ===")
    print(results['comments'])
    
    print("\nBuilding Report...")
    out_path = "so_sanh_nhap.xlsx"
    builder.generate_report(results, out_path)
    print(f"Consolidated Excel report saved to {out_path}")
    
    # Assert ranking exists
    assert len(results['summary_data']) > 0, "Summary data is empty!"
    print("\nAll pipeline tests PASSED!")

if __name__ == "__main__":
    test()
