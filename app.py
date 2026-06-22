import streamlit as st
import pandas as pd
import io
import os
import re
from file_ingester import FileIngester
from normalizer import Normalizer
from comparison_engine import ComparisonEngine
from report_builder import ReportBuilder

# Page configuration
st.set_page_config(
    page_title="Hacom Mall BOQ Bid Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject custom CSS for premium aesthetics
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Title container */
.title-container {
    background: linear-gradient(135deg, #1F4E78 0%, #2E75B6 100%);
    padding: 2rem 2.5rem;
    border-radius: 12px;
    color: white;
    margin-bottom: 2rem;
    box-shadow: 0 4px 20px rgba(31, 78, 120, 0.15);
}
.title-container h1 {
    margin: 0;
    font-size: 2.2rem;
    font-weight: 700;
    color: #ffffff;
}
.title-container p {
    margin: 0.5rem 0 0 0;
    font-size: 1.1rem;
    opacity: 0.9;
}

/* Metric Cards */
.metric-card {
    background-color: #f8f9fa;
    border-radius: 8px;
    padding: 1.2rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    border-left: 5px solid #1F4E78;
    margin-bottom: 1rem;
}
.metric-rank {
    font-size: 0.85rem;
    font-weight: 600;
    color: #2E75B6;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.metric-name {
    font-size: 1.25rem;
    font-weight: 700;
    color: #2c3e50;
    margin-top: 0.2rem;
}
.metric-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1F4E78;
    margin-top: 0.4rem;
}
.metric-diff {
    font-size: 0.85rem;
    font-weight: 500;
    color: #7f8c8d;
    margin-top: 0.2rem;
}

/* Badges */
.badge {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
}
.badge-high {
    background-color: #FFC7CE;
    color: #9C0006;
}
.badge-warning {
    background-color: #FFEB9C;
    color: #9C6500;
}
.badge-info {
    background-color: #C6EFCE;
    color: #006100;
}
</style>
""", unsafe_allow_html=True)

def guess_contractor_name(filename):
    """Guesses the contractor name from the uploaded filename."""
    filename_lower = filename.lower()
    if "linh anh" in filename_lower:
        return "Linh Anh"
    elif "van lang" in filename_lower or "tri trung" in filename_lower:
        return "Trí Trung - Văn Lang"
    elif "searefico" in filename_lower:
        return "Searefico"
    elif "van khanh" in filename_lower or "vân khánh" in filename_lower:
        return "Vân Khánh"
    else:
        # Fallback: Clean up filename without extension
        base = os.path.splitext(filename)[0]
        base = re.sub(r'^\d+\.?\s*', '', base) # remove leading digits (e.g., 1.)
        base = re.sub(r'^\d{4}\.\d{2}\.\d{2}\s*', '', base) # remove leading date codes (e.g., 2025.12.08)
        return base.strip()

# Initialize session state for caching comparison results
if "comparison_results" not in st.session_state:
    st.session_state.comparison_results = None
if "report_bytes" not in st.session_state:
    st.session_state.report_bytes = None

# Custom Premium Header
st.markdown("""
<div class="title-container">
    <h1>Hệ thống So sánh & Phân tích Đấu thầu BOQ</h1>
    <p>Giải pháp phân tích tự động, đối chiếu khối lượng, đơn giá và phát hiện sai sót kỹ thuật từ nhà thầu (V1 MVP)</p>
</div>
""", unsafe_allow_html=True)

# Sidebar - Configuration and File Upload
st.sidebar.header("📁 Tải Hồ Sơ HSDT")
uploaded_files = st.sidebar.file_uploader(
    "Tải lên các file Excel HSDT của nhà thầu (tối thiểu 2 file):",
    type=["xlsx"],
    accept_multiple_files=True
)

selected_contractors = {}

if uploaded_files:
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Thiết lập nhà thầu")
    st.sidebar.info("Vui lòng tích chọn nhà thầu muốn đưa vào so sánh:")
    
    for f in uploaded_files:
        default_name = guess_contractor_name(f.name)
        
        # Checkbox to include file
        is_selected = st.sidebar.checkbox(f.name, value=True, key=f"check_{f.name}")
        
        if is_selected:
            # Text input to customize Contractor Name
            contractor_name = st.sidebar.text_input(
                f"Tên nhà thầu ({f.name}):",
                value=default_name,
                key=f"name_{f.name}"
            )
            selected_contractors[contractor_name] = f

st.sidebar.markdown("---")
st.sidebar.caption("Phiên bản V1 MVP - Hacom Mall Project")

# Main Content Area
if len(selected_contractors) < 2:
    st.warning("⚠️ Vui lòng tải lên và tích chọn ít nhất **2 nhà thầu** ở bảng điều khiển bên trái để tiến hành so sánh.")
    st.session_state.comparison_results = None
    st.session_state.report_bytes = None
else:
    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        run_analysis = st.button("🚀 Bắt đầu phân tích", type="primary", use_container_width=True)
    with col_info:
        st.markdown(f"Đang chọn **{len(selected_contractors)} nhà thầu**: " + ", ".join([f"`{name}`" for name in selected_contractors.keys()]))

    # Execute Pipeline
    if run_analysis:
        st.session_state.comparison_results = None
        st.session_state.report_bytes = None
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            ingester = FileIngester()
            normalizer = Normalizer()
            engine = ComparisonEngine()
            builder = ReportBuilder()
            
            contractor_data = {}
            total_steps = len(selected_contractors) + 2
            current_step = 0
            
            # Ingestion & Normalization
            for name, uploaded_file in selected_contractors.items():
                current_step += 1
                progress_val = int((current_step / total_steps) * 100)
                progress_bar.progress(progress_val)
                status_text.info(f"Đang xử lý nhà thầu **{name}**...")
                
                # Copy file into memory BytesIO stream
                file_bytes = io.BytesIO(uploaded_file.getvalue())
                raw_data = ingester.ingest_file(file_bytes)
                normalized = normalizer.normalize(name, raw_data)
                
                contractor_data[name] = normalized
                
            # Run comparison engine
            current_step += 1
            progress_bar.progress(int((current_step / total_steps) * 100))
            status_text.info("Đang chạy đối chiếu thuật toán căn chỉnh...")
            
            results = engine.compare_bids(contractor_data)
            
            # Generate Report
            current_step += 1
            progress_bar.progress(int((current_step / total_steps) * 100))
            status_text.info("Đang sinh báo cáo tổng hợp Excel...")
            
            report_stream = builder.generate_report(results)
            
            # Save results in session state
            st.session_state.comparison_results = results
            st.session_state.report_bytes = report_stream.getvalue()
            
            progress_bar.empty()
            status_text.success("🎉 Phân tích so sánh hoàn thành thành công!")
            
        except Exception as e:
            progress_bar.empty()
            status_text.error(f"❌ Đã xảy ra lỗi trong quá trình phân tích: {str(e)}")
            st.exception(e)

    # Render Results if available in Session State
    if st.session_state.comparison_results is not None:
        results = st.session_state.comparison_results
        contractors = results['contractors']
        summary_data = results['summary_data']
        flags = results['flags']
        canonical_b = results['canonical_b']
        
        # Compute total costs and rank
        totals = {}
        for c in contractors:
            totals[c] = sum(row[f'{c}_TổngCộng'] for row in summary_data)
        
        sorted_ranks = sorted(totals.items(), key=lambda x: x[1])
        min_total = sorted_ranks[0][1]
        
        st.markdown("### 🏆 Bảng Xếp Hạng Giá Chào Thầu (Trước VAT)")
        
        # Display Premium Rank Cards side-by-side
        cols = st.columns(len(sorted_ranks))
        for rank_idx, (c_name, c_tot) in enumerate(sorted_ranks):
            diff_text = ""
            if rank_idx == 0:
                diff_text = "Thấp nhất (Thầu chính + Phát sinh)"
            else:
                pct_diff = ((c_tot - min_total) / min_total) * 100.0 if min_total > 0 else 0
                diff_text = f"+{pct_diff:.2f}% so với giá thấp nhất"
                
            cols[rank_idx].markdown(f"""
            <div class="metric-card">
                <div class="metric-rank">Hạng {rank_idx + 1}</div>
                <div class="metric-name">{c_name}</div>
                <div class="metric-value">{c_tot:,.0f} VNĐ</div>
                <div class="metric-diff">{diff_text}</div>
            </div>
            """, unsafe_allow_html=True)
            
        # Download consolidated report section
        st.markdown("---")
        st.subheader("📥 Tải Báo Cáo Kết Quả")
        st.download_button(
            label="📊 Tải Báo Cáo Excel Tổng Hợp (.xlsx)",
            data=st.session_state.report_bytes,
            file_name="Bao_cao_so_sanh_BOQ_HacomMall.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
        
        # Dynamic tabs for granular insights
        st.markdown("---")
        st.subheader("🔍 Kết Quả Đối Chiếu Chi Tiết")
        
        tab_comments, tab_summary, tab_missing, tab_arising, tab_qty, tab_price = st.tabs([
            "📝 Nhận xét tự động",
            "📊 Tổng hợp hệ thống",
            "⚠️ Hạng mục thiếu",
            "➕ Phát sinh ngoài BOQ",
            "⚖️ Sai lệch khối lượng",
            "💰 Sai lệch đơn giá"
        ])
        
        # Tab 1: Automated Comments
        with tab_comments:
            st.markdown(results['comments'])
            
        # Tab 2: System breakdown
        with tab_summary:
            st.markdown("#### Bảng giá trị chào thầu theo từng hệ thống cơ điện (VND)")
            df_sum = pd.DataFrame(summary_data)
            df_sum.set_index('Hệ thống', inplace=True)
            
            # Format numbers to make it readable in stream
            st.dataframe(
                df_sum.style.format("{:,.0f}"),
                use_container_width=True
            )
            
        # Helper to render preview tables with 100 row limit to maintain fast DOM
        def render_preview_table(title, data, columns, mapping_keys):
            if not data:
                st.info(f"Không phát hiện {title.lower()} nào.")
                return
                
            st.markdown(f"**Danh sách {title.lower()} (Hiển thị tối đa 100 dòng đầu tiên):**")
            
            df_preview = pd.DataFrame(data[:100])
            df_display = df_preview[mapping_keys].copy()
            df_display.columns = columns
            
            # Formatting numeric columns if they exist
            for col in df_display.columns:
                if col in ["Độ lệch (abs)", "Lượng chênh (abs)", "Khối lượng chào", "Đơn giá chào", "Thành tiền chào"]:
                    df_display[col] = df_display[col].apply(lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) else x)
                elif col in ["Độ lệch (%)", "Lượng chênh (%)"]:
                    df_display[col] = df_display[col].apply(lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) else x)
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            if len(data) > 100:
                st.warning(f"⚠️ Chỉ hiển thị 100 trên tổng số {len(data)} dòng. Vui lòng tải báo cáo Excel để xem toàn bộ danh sách.")
                
        # Tab 3: Missing Items
        with tab_missing:
            missing_flags = [f for f in flags if f['type'] == 'ITEM_MISSING']
            render_preview_table(
                "Hạng mục thiếu/bỏ sót",
                missing_flags,
                ["Nhà thầu", "Hệ thống", "STT", "Diễn giải hạng mục", "Nội dung cảnh báo"],
                ["contractor", "system", "stt", "description", "message"]
            )
            
        # Tab 4: Arising Items
        with tab_arising:
            arising_list = []
            for c_item in canonical_b:
                if c_item['row_type'] != 'priced':
                    continue
                for contractor, bid in c_item['bids'].items():
                    qty_bid = bid.get('qty_bid')
                    price = bid.get('price')
                    total = bid.get('total')
                    if qty_bid or price or total:
                        arising_list.append({
                            'contractor': contractor,
                            'system': c_item['system'],
                            'stt': c_item['stt'],
                            'code': c_item['code'],
                            'description': c_item['description'],
                            'unit': c_item['unit'],
                            'qty_bid': qty_bid,
                            'price': price,
                            'total': total if total else (qty_bid * price if qty_bid and price else 0)
                        })
            render_preview_table(
                "Hạng mục phát sinh ngoài",
                arising_list,
                ["Nhà thầu", "Hệ thống", "STT", "Mã hiệu", "Diễn giải hạng mục", "Đơn vị", "Khối lượng chào", "Đơn giá chào", "Thành tiền chào"],
                ["contractor", "system", "stt", "code", "description", "unit", "qty_bid", "price", "total"]
            )
            
        # Tab 5: Quantity deviations
        with tab_qty:
            qty_flags = [f for f in flags if f['type'] in ['QTY_OVER', 'QTY_UNDER']]
            render_preview_table(
                "Sai khác khối lượng chào thầu",
                qty_flags,
                ["Nhà thầu", "Hệ thống", "STT", "Diễn giải hạng mục", "Cảnh báo đối chiếu", "Độ lệch (abs)", "Độ lệch (%)"],
                ["contractor", "system", "stt", "description", "message", "delta_abs", "delta_pct"]
            )
            
        # Tab 6: Price deviations
        with tab_price:
            price_flags = [f for f in flags if f['type'] in ['PRICE_HIGH', 'PRICE_LOW']]
            render_preview_table(
                "Hạng mục có chênh lệch đơn giá lớn (>25% so với Median)",
                price_flags,
                ["Nhà thầu", "Hệ thống", "STT", "Diễn giải hạng mục", "Cảnh báo đối chiếu", "Lượng chênh (abs)", "Lượng chênh (%)"],
                ["contractor", "system", "stt", "description", "message", "delta_abs", "delta_pct"]
            )
