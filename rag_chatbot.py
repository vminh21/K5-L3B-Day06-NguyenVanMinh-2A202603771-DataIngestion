#!/usr/bin/env python3
"""Interactive RAG Chatbot CLI for Manifesto of the Communist Party.

Components:
- Embedding: Ollama local 'embeddinggemma' (768 dimensions)
- Vector Store: PostgreSQL + pgvector (local port 55433)
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

# Thêm thư mục starter vào sys.path để tái sử dụng module có sẵn
STARTER_DIR = Path(__file__).resolve().parent / "starter"
if str(STARTER_DIR) not in sys.path:
    sys.path.insert(0, str(STARTER_DIR))

try:
    from src.embeddings import MyEmbedder
    from src.store import PgVectorStore
except ImportError as err:
    print(f"❌ Lỗi import module pipeline: {err}")
    print("Vui lòng kích hoạt virtualenv: `source starter/.venv/bin/activate` trước khi chạy.")
    sys.exit(1)

# Cấu hình kết nối
DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab",
)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = "embeddinggemma"
DEFAULT_LLM_MODEL = "qwen3:1.7b"

# Mã màu ANSI terminal
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_CYAN = "\033[96m"
C_GRAY = "\033[90m"


class RagChatbot:
    def __init__(
        self,
        llm_model: str = DEFAULT_LLM_MODEL,
        embedding_model: str = EMBEDDING_MODEL,
        database_url: str = DB_URL,
        ollama_url: str = OLLAMA_BASE_URL,
    ) -> None:
        self.llm_model = llm_model
        self.ollama_url = ollama_url
        self.database_url = database_url
        self.strategy = "B"  # Mặc định dùng Strategy B (Paragraph-aware)
        self.top_k = 3

        print(f"{C_CYAN}⚙️  Đang khởi tạo các kết nối thành phần...{C_RESET}")
        self.embedder = MyEmbedder(model_name=embedding_model, base_url=ollama_url)
        self.store = PgVectorStore(database_url=database_url, dimensions=self.embedder.dimensions)
        self.last_retrieved_chunks: list[dict] = []
        print(f"{C_GREEN}✅ Đã kết nối PgVectorStore (dim={self.embedder.dimensions}) và Ollama ({self.llm_model})!{C_RESET}")

    def retrieve(self, query: str, metadata_filter: dict | None = None) -> list[dict]:
        """Truy xuất các chunk liên quan nhất từ pgvector."""
        t0 = time.perf_counter()
        query_vec = self.embedder.embed_query(query)
        hits = self.store.search(
            strategy=self.strategy,
            query_vector=query_vec,
            top_k=self.top_k,
            filters=metadata_filter,
        )
        elapsed = time.perf_counter() - t0
        self.last_retrieved_chunks = hits
        return hits, elapsed

    def build_prompt(self, query: str, chunks: list[dict]) -> str:
        """Ghép Context vào Prompt chuẩn Grounded RAG."""
        context_blocks = []
        for i, c in enumerate(chunks, 1):
            meta = c.get("metadata", {})
            chapter = meta.get("chapter", "Không rõ")
            section = meta.get("section", "Không rõ")
            page = c.get("page", "?")
            context_blocks.append(
                f"[ĐOẠN TRÍCH {i}] - Trang {page} (Chương: {chapter} | Mục: {section})\n"
                f"{c.get('text', '').strip()}"
            )

        context_str = "\n\n".join(context_blocks)

        prompt = f"""Bạn là một học giả và trợ lý AI am hiểu sâu sắc về tác phẩm kinh điển "Tuyên ngôn của Đảng Cộng sản" (Manifesto of the Communist Party) của Karl Marx và Frederick Engels.

Dưới đây là các đoạn văn bản trích xuất trực tiếp từ tác phẩm gốc để bạn làm căn cứ trả lời:
================================================================================
{context_str}
================================================================================

YÊU CẦU TRẢ LỜI:
1. Dựa CHỦ YẾU vào các thông tin trong các đoạn trích dẫn ở trên để trả lời câu hỏi của người dùng.
2. Trả lời bằng tiếng Việt một cách rõ ràng, chuẩn xác, đúng tinh thần học thuật triết học - chính trị của Marx & Engels.
3. LUÔN trích dẫn rõ số trang nguồn và tên chương (ví dụ: "[Trang 3, Chương I]") nơi chứa bằng chứng.
4. Nếu trong các đoạn trích trên không có thông tin để trả lời, hãy thành thật nêu rõ: "Trong các đoạn trích xuất từ tài liệu không có thông tin trực tiếp về vấn đề này."

[CÂU HỎI]: {query}

[CÂU TRẢ LỜI]:"""
        return prompt

    def stream_generate(self, prompt: str) -> str:
        """Gửi prompt tới Ollama và stream từng token ra màn hình terminal."""
        payload = json.dumps({
            "model": self.llm_model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        full_response = []
        is_thinking = False

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                for line in resp:
                    if not line:
                        continue
                    chunk_data = json.loads(line.decode("utf-8"))
                    
                    # Một số mô hình suy nghĩ như DeepSeek/Qwen3 có thinking tags
                    thinking_chunk = chunk_data.get("thinking", "")
                    if thinking_chunk:
                        # Có thể bỏ qua hoặc in nhạt để không làm rối người dùng
                        continue

                    token = chunk_data.get("response", "")
                    if token:
                        sys.stdout.write(token)
                        sys.stdout.flush()
                        full_response.append(token)

                    if chunk_data.get("done", False):
                        break
        except urllib.error.URLError as e:
            print(f"\n{C_RED}❌ Lỗi kết nối Ollama API ({self.ollama_url}): {e}{C_RESET}")
            return ""

        print()  # Dòng trống kết thúc stream
        return "".join(full_response)

    def print_sources(self, hits: list[dict]) -> None:
        """Hiển thị tóm tắt các nguồn tham khảo đã trích xuất."""
        print(f"\n{C_GRAY}{'─' * 65}")
        print(f"📚 NGUỒN TRÍCH DẪN (Top-{len(hits)} Cosine Similarity):")
        for i, h in enumerate(hits, 1):
            meta = h.get("metadata", {})
            page = h.get("page")
            chapter = meta.get("chapter", "N/A")
            score = h.get("score", 0.0)
            chunk_id = h.get("chunk_id", "")
            preview = h.get("text", "")[:90].replace("\n", " ").strip()
            print(f"  [{i}] Trang {page:<2} | {chapter:<12} | Điểm: {score:.4f} | ID: {chunk_id[-12:]}")
            print(f"      {C_GRAY}\"{preview}...\"{C_RESET}")
        print(f"{'─' * 65}{C_RESET}\n")


def print_banner(bot: RagChatbot) -> None:
    print(f"{C_BOLD}{C_RED}")
    print("=" * 70)
    print("☭  RAG CHATBOT — TUYÊN NGÔN CỦA ĐẢNG CỘNG SẢN (1848)  ☭")
    print("=" * 70 + C_RESET)
    print(f"{C_CYAN}Mô hình LLM   :{C_RESET} {bot.llm_model} (Ollama Local)")
    print(f"{C_CYAN}Embedding     :{C_RESET} {bot.embedder.model_name} ({bot.embedder.dimensions} dimensions)")
    print(f"{C_CYAN}Vector Store  :{C_RESET} PostgreSQL + pgvector (Table: doc_chunks)")
    print(f"{C_CYAN}Chiến lược RAG:{C_RESET} Strategy {bot.strategy} (Paragraph-aware max 1000) | Top-K: {bot.top_k}")
    print(f"{C_YELLOW}Lệnh hỗ trợ   :{C_RESET} gõ {C_BOLD}/help{C_RESET} để xem các lệnh cấu hình hoặc {C_BOLD}/exit{C_RESET} để thoát.")
    print("-" * 70 + "\n")


def main() -> None:
    try:
        bot = RagChatbot()
    except Exception as e:
        print(f"\n{C_RED}❌ Không thể khởi tạo Chatbot: {e}{C_RESET}")
        print("Kiểm tra lại:")
        print("  1. Docker PostgreSQL: `docker compose -p day6_student_starter up -d`")
        print("  2. Ollama Server: `ollama list` và kiểm tra `qwen3:1.7b` & `embeddinggemma`")
        sys.exit(1)

    print_banner(bot)

    while True:
        try:
            user_input = input(f"{C_BOLD}{C_GREEN}Bạn hỏi 💬: {C_RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C_YELLOW}Tạm biệt đồng chí! Hẹn gặp lại.{C_RESET}")
            break

        if not user_input:
            continue

        # Các lệnh tiện ích
        if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
            print(f"{C_YELLOW}Tạm biệt đồng chí!{C_RESET}")
            break

        if user_input.lower() == "/help":
            print(f"\n{C_YELLOW}DANH SÁCH LỆNH:{C_RESET}")
            print("  /strategy A     - Chuyển sang Strategy A (Fixed 500, overlap 50)")
            print("  /strategy B     - Chuyển sang Strategy B (Paragraph-aware)")
            print("  /strategy C     - Chuyển sang Strategy C (Paragraph + Filter)")
            print("  /topk <số>      - Thay đổi số lượng chunks truy xuất (ví dụ /topk 4)")
            print("  /model <tên>    - Đổi mô hình Ollama (ví dụ /model qwen3:1.7b)")
            print("  /sources        - Xem chi tiết toàn văn các chunks vừa truy xuất")
            print("  /exit           - Thoát chương trình\n")
            continue

        if user_input.lower().startswith("/strategy"):
            parts = user_input.split()
            if len(parts) >= 2 and parts[1].upper() in ("A", "B", "C"):
                bot.strategy = parts[1].upper()
                print(f"{C_CYAN}✔ Đã đổi sang Strategy {bot.strategy}!{C_RESET}\n")
            else:
                print(f"{C_RED}Cú pháp không hợp lệ. Dùng: /strategy A hoặc /strategy B hoặc /strategy C{C_RESET}\n")
            continue

        if user_input.lower().startswith("/topk"):
            parts = user_input.split()
            if len(parts) >= 2 and parts[1].isdigit():
                bot.top_k = int(parts[1])
                print(f"{C_CYAN}✔ Đã đổi Top-K = {bot.top_k}!{C_RESET}\n")
            else:
                print(f"{C_RED}Cú pháp không hợp lệ. Dùng: /topk 3 hoặc /topk 5{C_RESET}\n")
            continue

        if user_input.lower().startswith("/model"):
            parts = user_input.split()
            if len(parts) >= 2:
                bot.llm_model = parts[1]
                print(f"{C_CYAN}✔ Đã đổi sang mô hình Ollama: {bot.llm_model}!{C_RESET}\n")
            continue

        if user_input.lower() == "/sources":
            if not bot.last_retrieved_chunks:
                print(f"{C_YELLOW}Chưa có lượt truy xuất nào gần đây.{C_RESET}\n")
            else:
                print(f"\n{C_BOLD}CHI TIẾT TOÀN VĂN CÁC CHUNKS VỪA TRUY XUẤT:{C_RESET}")
                for i, h in enumerate(bot.last_retrieved_chunks, 1):
                    print(f"\n--- [CHUNK {i}] (Trang {h.get('page')}, Score: {h.get('score'):.4f}) ---")
                    print(h.get("text", "").strip())
                print()
            continue

        # Thực thi truy xuất RAG
        print(f"{C_GRAY}🔍 [1/2] Đang embed câu hỏi & truy vấn top-{bot.top_k} (Strategy {bot.strategy})...{C_RESET}", end="\r")
        hits, ret_time = bot.retrieve(user_input)
        print(f"{C_GRAY}🔍 [1/2] Đã truy xuất {len(hits)} chunks từ pgvector trong {ret_time:.2f}s!{C_RESET}     ")

        if not hits:
            print(f"{C_RED}Không tìm thấy đoạn trích phù hợp trong CSDL.{C_RESET}\n")
            continue

        # Sinh câu trả lời với LLM
        prompt = bot.build_prompt(user_input, hits)
        print(f"\n{C_BOLD}{C_RED}🤖 Trả lời ({bot.llm_model}):{C_RESET} ")
        bot.stream_generate(prompt)

        # In nguồn trích dẫn
        bot.print_sources(hits)


if __name__ == "__main__":
    main()
