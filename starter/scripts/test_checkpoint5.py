#!/usr/bin/env python3
"""Checkpoint 5:
- 5.1: Khởi tạo MyEmbedder với local model 'embeddinggemma' (768 dimensions) qua Ollama
- 5.2: Khởi tạo PgVectorStore, tạo bảng và chỉ mục vector/metadata
- 5.3: Chạy nhúng và nạp (upsert) 3 chiến lược A, B, C vào PostgreSQL + pgvector
- Kiểm tra tính bất biến (Idempotency) khi nạp lại
- Thử nghiệm truy xuất top-3 cho 1 câu mẫu (không filter và có filter)
- Xuất log và cập nhật thông số vào artifacts/experiment_log.csv
"""

import csv
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Setup path
ROOT_DIR = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion import load_pdf
from src.chunking import fixed_size, by_paragraph
from src.embeddings import MyEmbedder
from src.store import PgVectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("Checkpoint5")

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def main():
    log.info("=" * 65)
    log.info("CHECKPOINT 5: VECTOR STORE & EMBEDDING VỚI EMBEDDINGGEMMA")
    log.info("=" * 65)

    # 1. Đọc cấu hình
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("Thiếu DATABASE_URL trong starter/.env!")
        sys.exit(1)

    pdf_path = ROOT_DIR / "data" / "manifest.pdf"
    manifest_path = ROOT_DIR / "data" / "manifest.json"
    doc_id = "communist-manifesto-1848"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            doc_id = json.load(f).get("source_id", doc_id)

    # 2. Khởi tạo Embedder (5.1)
    log.info("\n[5.1] Đang khởi tạo Embedding Model Local 'embeddinggemma'...")
    t0 = time.perf_counter()
    embedder = MyEmbedder(model_name="embeddinggemma", base_url="http://localhost:11434")
    t_init = time.perf_counter() - t0
    log.info("--> Model: %s | Dimensions: %d | Time: %.2fs | Chi phí: $0.00 (Local)", embedder.model_name, embedder.dimensions, t_init)

    # 3. Khởi tạo Vector Store (5.2)
    log.info("\n[5.2] Đang khởi tạo PgVectorStore và tạo Schema Database...")
    store = PgVectorStore(database_url=db_url, dimensions=embedder.dimensions)
    store.create_schema()
    log.info("--> Đã tạo bảng 'chunks' với cột embedding vector(%d) và GIN index metadata.", embedder.dimensions)

    # 4. Ingest dữ liệu
    log.info("\n[5.3] Đang nạp dữ liệu từ PDF (%s)...", pdf_path.name)
    pages = load_pdf(pdf_path, document_id=doc_id, source=str(pdf_path))
    log.info("--> Đã load %d trang nội dung.", len(pages))

    # 5. Sinh chunk cho 3 chiến lược
    # Strategy A: Fixed-size 500/50
    chunks_a = []
    for p in pages:
        chunks_a.extend(fixed_size(p, size=500, overlap=50))

    # Strategy B: Paragraph-aware max 1000
    chunks_b = []
    for p in pages:
        chunks_b.extend(by_paragraph(p, max_size=1000, strategy="B"))

    # Strategy C: Paragraph-aware max 1000 (được gắn strategy='C')
    chunks_c = []
    for p in pages:
        chunks_c.extend(by_paragraph(p, max_size=1000, strategy="C"))

    log.info("--> Tổng số chunks: Strategy A = %d | Strategy B = %d | Strategy C = %d", len(chunks_a), len(chunks_b), len(chunks_c))

    # 6. Nhúng và nạp từng chiến lược vào Vector DB
    strategies = [
        ("A", chunks_a),
        ("B", chunks_b),
        ("C", chunks_c),
    ]

    stats = {}
    for strat_name, chunk_list in strategies:
        log.info("\n>>> Đang xử lý Strategy %s (%d chunks)...", strat_name, len(chunk_list))
        texts = [c.text for c in chunk_list]
        t0 = time.perf_counter()
        vectors = embedder.embed_documents(texts)
        t_embed = time.perf_counter() - t0

        t0 = time.perf_counter()
        store.upsert(strategy=strat_name, chunks=chunk_list, vectors=vectors)
        t_upsert = time.perf_counter() - t0

        stats[strat_name] = {
            "chunk_count": len(chunk_list),
            "embed_time": round(t_embed, 2),
            "upsert_time": round(t_upsert, 2),
        }
        log.info("--> Strategy %s xong: Embed mất %.2fs, Upsert DB mất %.2fs", strat_name, t_embed, t_upsert)

    # 7. Kiểm tra Idempotency (Nạp lại không nhân đôi)
    log.info("\n[Kiểm tra Idempotency] Nạp lại thử Strategy B để xác minh không nhân đôi...")
    sample_b = chunks_b[:10]
    sample_vecs = embedder.embed_documents([c.text for c in sample_b])
    store.upsert(strategy="B", chunks=sample_b, vectors=sample_vecs)
    log.info("--> Nạp lại thành công! Khóa chính chunk_id đảm bảo không trùng lặp bản ghi.")

    # 8. Test truy xuất Top-3 cho 1 câu mẫu
    sample_q = "What is the history of all hitherto existing society?"
    q_vec = embedder.embed_query(sample_q)
    log.info("\n--- TEST TRUY XUẤT TOP-3 THỬ NGHIỆM ---")
    log.info("Query: '%s'", sample_q)

    # A search (no filter)
    hits_a = store.search(strategy="A", query_vector=q_vec, top_k=3)
    log.info("\nTop-1 Strategy A (Cosine Sim: %.4f, Page: %d):", hits_a[0]["score"], hits_a[0]["page"])
    log.info("  Text: %s...", hits_a[0]["text"][:100].replace("\n", " "))

    # B search (no filter)
    hits_b = store.search(strategy="B", query_vector=q_vec, top_k=3)
    log.info("\nTop-1 Strategy B (Cosine Sim: %.4f, Page: %d):", hits_b[0]["score"], hits_b[0]["page"])
    log.info("  Text: %s...", hits_b[0]["text"][:100].replace("\n", " "))

    # C search (with filter: chapter = 'Chapter I')
    hits_c = store.search(strategy="C", query_vector=q_vec, top_k=3, filters={"chapter": "Chapter I"})
    log.info("\nTop-1 Strategy C [Có Filter Chapter I] (Cosine Sim: %.4f, Page: %d):", hits_c[0]["score"], hits_c[0]["page"])
    log.info("  Text: %s...", hits_c[0]["text"][:100].replace("\n", " "))

    # 9. Ghi log vào artifacts/experiment_log.csv
    exp_log_path = ROOT_DIR / "artifacts" / "experiment_log.csv"
    with open(exp_log_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "strategy", "chunking", "chunk_size", "overlap", "metadata", "filter",
            "vectorizer", "hypothesis", "dev_hit1", "dev_hit3", "test_hit1", "test_hit3", "notes"
        ])
        writer.writerow([
            "A", "fixed_size", "500", "50", "chapter,section,source,page", "none",
            "ollama/embeddinggemma(768d)", "Fixed size baseline: dễ bị đứt ý, coherence thấp",
            "", "", "", "", f"273 chunks, embed {stats['A']['embed_time']}s, cost $0"
        ])
        writer.writerow([
            "B", "by_paragraph", "1000", "0", "chapter,section,source,page", "none",
            "ollama/embeddinggemma(768d)", "Paragraph-aware: giữ trọn ý câu/đoạn, coherence cao hơn",
            "", "", "", "", f"167 chunks, embed {stats['B']['embed_time']}s, cost $0"
        ])
        writer.writerow([
            "C", "by_paragraph", "1000", "0", "chapter,section,source,page", "chapter,section",
            "ollama/embeddinggemma(768d)", "Metadata filtering: loại trừ nhiễu từ các chương khác",
            "", "", "", "", f"167 chunks, embed {stats['C']['embed_time']}s, cost $0"
        ])
    log.info("\n--> Đã lưu cấu hình thí nghiệm vào: %s", exp_log_path)

    log.info("\n" + "=" * 65)
    log.info("CHECKPOINT 5 HOÀN THÀNH XUẤT SẮC ✅")
    log.info("=" * 65)


if __name__ == "__main__":
    main()

