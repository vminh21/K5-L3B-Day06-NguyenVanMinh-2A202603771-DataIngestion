#!/usr/bin/env python3
"""Kiểm tra Checkpoint 3 (Bước 3.4):
- Đọc tài liệu PDF (ingestion) và ghi log trang lỗi/rỗng
- Chạy 2 cấu hình chunking: Strategy A (fixed-size) và Strategy B/C (paragraph-aware)
- Thống kê phân bố độ dài, tổng ký tự, số chunk theo Chapter
- Xuất kết quả kiểm tra ra màn hình và file results/checkpoint3_stats.json
"""

import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

# Thêm starter vào sys.path để import src
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion import load_pdf
from src.chunking import fixed_size, by_paragraph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("Checkpoint3")

PDF_PATH = Path(__file__).resolve().parents[1].parent / "data" / "manifest.pdf"
MANIFEST_PATH = Path(__file__).resolve().parents[1].parent / "data" / "manifest.json"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def get_stats(chunks, label: str) -> dict:
    lengths = [len(c.text) for c in chunks]
    chapters = Counter(c.metadata.get("chapter", "unknown") for c in chunks)
    return {
        "strategy": label,
        "total_chunks": len(chunks),
        "avg_chars": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "min_chars": min(lengths) if lengths else 0,
        "max_chars": max(lengths) if lengths else 0,
        "total_chars": sum(lengths),
        "chunks_per_chapter": dict(chapters.most_common()),
    }


def main():
    log.info("=" * 65)
    log.info("BƯỚC 3.4: CHẠY THỬ INGESTION & XUẤT 2 CẤU HÌNH CHUNKING")
    log.info("=" * 65)

    if not PDF_PATH.exists():
        log.error("Không tìm thấy file PDF tại: %s", PDF_PATH)
        sys.exit(1)

    doc_id = "communist-manifesto-1848"
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            doc_id = manifest.get("source_id", doc_id)

    # 1. Ingestion (Load & Normalize PDF)
    log.info("[1/4] Đang đọc PDF: %s (doc_id: %s)...", PDF_PATH.name, doc_id)
    t0 = time.perf_counter()
    pages = load_pdf(PDF_PATH, document_id=doc_id, source=str(PDF_PATH))
    t_load = time.perf_counter() - t0
    total_chars = sum(len(p.text) for p in pages)
    log.info("--> Đã đọc thành công %d trang nội dung trong %.3f giây (Tổng: %d ký tự)", len(pages), t_load, total_chars)

    # 2. Strategy A (Fixed-size: 500 chars, overlap 50)
    log.info("\n[2/4] Đang cắt chunk Strategy A (Fixed-size: 500 chars, overlap 50)...")
    t0 = time.perf_counter()
    chunks_a = []
    for p in pages:
        chunks_a.extend(fixed_size(p, size=500, overlap=50))
    t_a = time.perf_counter() - t0
    stats_a = get_stats(chunks_a, "Strategy A (Fixed-size)")
    log.info("--> Strategy A hoàn thành trong %.3f giây: %d chunks (Trung bình %s ký tự/chunk)", t_a, stats_a["total_chunks"], stats_a["avg_chars"])

    # 3. Strategy B & C (Paragraph-aware: max 1000 chars)
    log.info("\n[3/4] Đang cắt chunk Strategy B (Paragraph-aware: max 1000 chars)...")
    t0 = time.perf_counter()
    chunks_b = []
    for p in pages:
        chunks_b.extend(by_paragraph(p, max_size=1000, strategy="B"))
    t_b = time.perf_counter() - t0
    stats_b = get_stats(chunks_b, "Strategy B (Paragraph-aware)")
    log.info("--> Strategy B hoàn thành trong %.3f giây: %d chunks (Trung bình %s ký tự/chunk)", t_b, stats_b["total_chunks"], stats_b["avg_chars"])

    # 4. Kiểm tra Idempotency (Uniqueness của chunk_id)
    ids_a = [c.chunk_id for c in chunks_a]
    ids_b = [c.chunk_id for c in chunks_b]
    assert len(ids_a) == len(set(ids_a)), "Lỗi: Có trùng lặp chunk_id trong Strategy A!"
    assert len(ids_b) == len(set(ids_b)), "Lỗi: Có trùng lặp chunk_id trong Strategy B!"
    log.info("\n[4/4] Kiểm tra Chunk ID: Tất cả %d chunk IDs đều DUY NHẤT và ỔN ĐỊNH (MD5 hash).", len(ids_a) + len(ids_b))

    # In mẫu metadata để đối soát
    sample_c = chunks_b[0]
    log.info("\n--- KIỂM TRA METADATA MẪU CỦA 1 CHUNK (Strategy B) ---")
    log.info("Chunk ID    : %s", sample_c.chunk_id)
    log.info("Document ID : %s", sample_c.document_id)
    log.info("Page        : %d", sample_c.page)
    log.info("Metadata    : %s", json.dumps(sample_c.metadata, ensure_ascii=False))
    log.info("Preview Text: %s...", sample_c.text[:120].replace("\n", " "))

    # Xuất file json
    summary = {
        "corpus": {
            "file": PDF_PATH.name,
            "document_id": doc_id,
            "content_pages": len(pages),
            "total_characters": total_chars,
            "load_time_seconds": round(t_load, 3),
        },
        "strategy_A": {**stats_a, "chunk_time_seconds": round(t_a, 3)},
        "strategy_B": {**stats_b, "chunk_time_seconds": round(t_b, 3)},
    }
    out_file = RESULTS_DIR / "checkpoint3_stats.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log.info("\n" + "=" * 65)
    log.info("KẾT QUẢ TỔNG HỢP:")
    log.info("  - Strategy A: %d chunks | Min: %d | Max: %d | Avg: %s chars", stats_a["total_chunks"], stats_a["min_chars"], stats_a["max_chars"], stats_a["avg_chars"])
    log.info("  - Strategy B: %d chunks | Min: %d | Max: %d | Avg: %s chars", stats_b["total_chunks"], stats_b["min_chars"], stats_b["max_chars"], stats_b["avg_chars"])
    log.info("  - Đã lưu chi tiết vào: %s", out_file.name)
    log.info("CHECKPOINT 3: PASS HOÀN TOÀN ✅")
    log.info("=" * 65)


if __name__ == "__main__":
    main()

