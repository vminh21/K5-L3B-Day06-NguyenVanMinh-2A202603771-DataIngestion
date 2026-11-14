"""Streamlit Web UI for RAG Chatbot — Tuyên ngôn của Đảng Cộng sản (1848).

Mô hình:
- Embedding: Ollama local 'embeddinggemma' (768 dimensions)
- Vector Store: PostgreSQL + pgvector (Local port 55433)
- LLM: Ollama local 'qwen3:1.7b'
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Generator

import streamlit as st

# Setup sys.path để import các module từ starter/src
CURRENT_DIR = Path(__file__).resolve().parent
STARTER_DIR = CURRENT_DIR / "starter"
if str(STARTER_DIR) not in sys.path:
    sys.path.insert(0, str(STARTER_DIR))

try:
    from src.embeddings import MyEmbedder
    from src.store import PgVectorStore
except ImportError as err:
    st.error(f"❌ Không thể nạp module pipeline: {err}")
    st.stop()

# Cấu hình mặc định
DEFAULT_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab",
)
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Thiết lập trang Streamlit
st.set_page_config(
    page_title="RAG Chatbot — Tuyên ngôn Đảng Cộng sản",
    page_icon="☭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS cho phong cách học thuật hiện đại
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        color: #b71c1c;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #555;
        margin-bottom: 1.5rem;
    }
    .citation-box {
        background-color: #f8f9fa;
        border-left: 4px solid #b71c1c;
        padding: 10px 14px;
        margin-top: 8px;
        border-radius: 4px;
        font-size: 0.92rem;
    }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-page { background-color: #e3f2fd; color: #0d47a1; }
    .badge-chapter { background-color: #fbe9e7; color: #b71c1c; }
    .badge-score { background-color: #e8f5e9; color: #1b5e20; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_embedder_and_store(db_url: str, ollama_url: str):
    """Khởi tạo và cache kết nối Embedder + PgVectorStore."""
    embedder = MyEmbedder(model_name="embeddinggemma", base_url=ollama_url)
    store = PgVectorStore(database_url=db_url, dimensions=embedder.dimensions)
    return embedder, store


def check_ollama_status(ollama_url: str) -> bool:
    """Kiểm tra server Ollama có đang hoạt động không."""
    try:
        req = urllib.request.Request(f"{ollama_url}/api/tags")
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


def stream_ollama_response(prompt: str, model_name: str, ollama_url: str) -> Generator[str, None, None]:
    """Stream token phản hồi từ Ollama API."""
    payload = json.dumps({
        "model": model_name,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            for line in resp:
                if not line:
                    continue
                data = json.loads(line.decode("utf-8"))
                
                # Bỏ qua thinking tag của reasoning models nếu có
                if data.get("thinking"):
                    continue

                token = data.get("response", "")
                if token:
                    yield token

                if data.get("done", False):
                    break
    except Exception as e:
        yield f"\n\n❌ **Lỗi gọi Ollama:** {e}"


def build_rag_prompt(query: str, hits: list[dict]) -> str:
    """Ghép ngữ cảnh tài liệu vào Prompt chuẩn RAG."""
    context_blocks = []
    for i, c in enumerate(hits, 1):
        meta = c.get("metadata", {})
        chapter = meta.get("chapter", "Không rõ")
        section = meta.get("section", "Không rõ")
        page = c.get("page", "?")
        context_blocks.append(
            f"[ĐOẠN TRÍCH {i}] - Trang {page} (Chương: {chapter} | Mục: {section})\n"
            f"{c.get('text', '').strip()}"
        )

    context_str = "\n\n".join(context_blocks)

    return f"""Bạn là học giả và trợ lý AI am hiểu sâu sắc tác phẩm kinh điển "Tuyên ngôn của Đảng Cộng sản" (Manifesto of the Communist Party) của Karl Marx và Frederick Engels.

Dưới đây là các đoạn văn bản trích xuất trực tiếp từ tác phẩm gốc:
================================================================================
{context_str}
================================================================================

YÊU CẦU:
1. Trả lời câu hỏi bằng tiếng Việt rõ ràng, chuẩn xác dựa CHỦ YẾU trên ngữ cảnh trên.
2. LUÔN ghi rõ số trang và chương nơi chứa bằng chứng (ví dụ: "[Trang 3, Chương I]").
3. Nếu ngữ cảnh không có thông tin, hãy nói rõ là tài liệu không đề cập trực tiếp.

[CÂU HỎI]: {query}

[CÂU TRẢ LỜI]:"""


# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/d/d4/Karl_Marx_001.jpg", width=120)
    st.title("⚙️ Cấu hình RAG")

    ollama_ok = check_ollama_status(DEFAULT_OLLAMA_URL)
    if ollama_ok:
        st.success("🟢 Ollama Server: Đang chạy")
    else:
        st.error("🔴 Ollama Server: Không kết nối được")

    st.markdown("---")
    llm_model = st.selectbox(
        "Mô hình LLM (Ollama)",
        ["qwen3:1.7b", "embeddinggemma:latest", "llama3.2:3b"],
        index=0,
        help="Mô hình local Ollama sinh câu trả lời.",
    )

    strategy = st.radio(
        "Chiến lược Chunking",
        ["B (Paragraph max 1000)", "A (Fixed 500, overlap 50)", "C (Paragraph + Metadata Filter)"],
        index=0,
        help="A = Fixed sliding window | B = Đoạn văn tự nhiên | C = B có lọc metadata",
    )
    strat_key = strategy[0]

    top_k = st.slider("Số lượng Chunks truy xuất (Top-K)", min_value=1, max_value=6, value=3)

    # Bộ lọc nếu chọn Strategy C
    selected_chapter = None
    if strat_key == "C":
        selected_chapter = st.selectbox(
            "Lọc theo Chương (Metadata Filter)",
            ["Tất cả", "Preamble", "Chapter I", "Chapter II", "Chapter III", "Chapter IV", "Appendix"],
            index=0,
        )
        if selected_chapter == "Tất cả":
            selected_chapter = None

    st.markdown("---")
    st.markdown(
        """
        **Thông số hệ thống:**
        - **Embedding:** `embeddinggemma` (768d)
        - **Vector DB:** PostgreSQL + `pgvector` (55433)
        - **Corpus:** 43 trang nội dung hợp lệ
        """
    )

    if st.button("🗑️ Xóa lịch sử trò chuyện", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# --- MAIN CHAT INTERFACE ---
st.markdown('<div class="main-header">☭ RAG Chatbot — Tuyên ngôn của Đảng Cộng sản</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Trợ lý học thuật hỏi đáp dựa trên toàn văn tác phẩm kinh điển của Karl Marx & Frederick Engels (1848). Dữ liệu được truy xuất trực tiếp từ <code>pgvector</code>.</div>',
    unsafe_allow_html=True,
)

# Kết nối database & embedder
try:
    embedder, store = get_embedder_and_store(DEFAULT_DB_URL, DEFAULT_OLLAMA_URL)
except Exception as e:
    st.error(f"❌ Không thể kết nối cơ sở dữ liệu pgvector: {e}")
    st.info("Hãy kiểm tra container Docker: `docker compose -p day6_student_starter up -d`")
    st.stop()

# Khởi tạo session state lưu tin nhắn
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Xin chào đồng chí! Tôi là trợ lý RAG về tác phẩm **Tuyên ngôn của Đảng Cộng sản** (1848). Đồng chí có thể hỏi bất kỳ vấn đề nào về các luận điểm giai cấp, cương lĩnh 10 biện pháp, hoặc các lời tựa lịch sử!",
            "citations": [],
        }
    ]

# Gợi ý câu hỏi nhanh (Quick Question Pills)
st.markdown("**💡 Câu hỏi gợi ý nhanh:**")
col1, col2, col3, col4 = st.columns(4)
quick_q = None
if col1.button("📜 Lịch sử các xã hội là gì?", use_container_width=True):
    quick_q = "Lịch sử của tất cả các xã hội từ trước đến nay là lịch sử của cái gì?"
if col2.button("🔟 10 biện pháp cách mạng?", use_container_width=True):
    quick_q = "10 biện pháp cách mạng cụ thể của giai cấp vô sản ở các nước tiên tiến là gì?"
if col3.button("🏭 Vai trò của giai cấp tư sản?", use_container_width=True):
    quick_q = "Giai cấp tư sản đã đóng vai trò cách mạng như thế nào trong lịch sử?"
if col4.button("📢 Khẩu hiệu kết thúc?", use_container_width=True):
    quick_q = "Khẩu hiệu nổi tiếng kết thúc Chương IV của Tuyên ngôn là gì?"

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations"):
            with st.expander(f"📚 Xem {len(msg['citations'])} đoạn trích dẫn nguồn từ CSDL:"):
                for idx, c in enumerate(msg["citations"], 1):
                    meta = c.get("metadata", {})
                    p = c.get("page", "?")
                    ch = meta.get("chapter", "N/A")
                    sec = meta.get("section", "N/A")
                    sc = c.get("score", 0.0)
                    st.markdown(
                        f"""<div class="citation-box">
                        <span class="badge badge-page">Trang {p}</span>
                        <span class="badge badge-chapter">{ch} — {sec}</span>
                        <span class="badge badge-score">Cosine Similarity: {sc:.4f}</span>
                        <p style="margin-top:6px; color:#222;">{c.get('text', '').strip()}</p>
                        </div>""",
                        unsafe_allow_html=True,
                    )

# Xử lý input người dùng
user_prompt = st.chat_input("Nhập câu hỏi của bạn về Tuyên ngôn của Đảng Cộng sản...")
if quick_q:
    user_prompt = quick_q

if user_prompt:
    # 1. Hiển thị câu hỏi của user
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # 2. Truy xuất RAG từ pgvector
    with st.chat_message("assistant"):
        with st.status("🔍 Đang nhúng vector câu hỏi & tìm kiếm trên PostgreSQL (pgvector)...", expanded=False) as status:
            t0 = time.perf_counter()
            q_vec = embedder.embed_query(user_prompt)
            
            meta_filter = {"chapter": selected_chapter} if (strat_key == "C" and selected_chapter) else None
            hits = store.search(
                strategy=strat_key,
                query_vector=q_vec,
                top_k=top_k,
                filters=meta_filter,
            )
            t_ret = time.perf_counter() - t0
            status.update(label=f"✅ Đã tìm thấy {len(hits)} đoạn trích liên quan trong {t_ret:.2f} giây!", state="complete")

        # 3. Tạo prompt và stream câu trả lời từ LLM
        prompt = build_rag_prompt(user_prompt, hits)
        response_stream = stream_ollama_response(prompt, llm_model, DEFAULT_OLLAMA_URL)
        full_response = st.write_stream(response_stream)

        # 4. Hiển thị citations
        if hits:
            with st.expander(f"📚 Xem {len(hits)} đoạn trích dẫn nguồn từ CSDL:"):
                for idx, c in enumerate(hits, 1):
                    meta = c.get("metadata", {})
                    p = c.get("page", "?")
                    ch = meta.get("chapter", "N/A")
                    sec = meta.get("section", "N/A")
                    sc = c.get("score", 0.0)
                    st.markdown(
                        f"""<div class="citation-box">
                        <span class="badge badge-page">Trang {p}</span>
                        <span class="badge badge-chapter">{ch} — {sec}</span>
                        <span class="badge badge-score">Cosine Similarity: {sc:.4f}</span>
                        <p style="margin-top:6px; color:#222;">{c.get('text', '').strip()}</p>
                        </div>""",
                        unsafe_allow_html=True,
                    )

        # Lưu vào lịch sử chat
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "citations": hits,
        })

