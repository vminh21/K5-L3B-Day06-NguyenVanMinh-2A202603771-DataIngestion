"""Chunking strategies — Strategy A (fixed-size) và Strategy B/C (paragraph-aware).

Kỹ thuật:
- Strategy A: Sliding window cố định (500 ký tự, overlap 50)
  · Đơn giản, predictable chunk size
  · Có thể cắt giữa câu/ý → coherence thấp hơn
  · Phù hợp làm baseline

- Strategy B/C: Paragraph-aware chunking
  · Tách theo double newline (\n\n) — ranh giới paragraph tự nhiên
  · Nối các đoạn ngắn vào nhau cho đến max_size
  · Cắt đoạn quá dài theo câu (dấu chấm) thay vì giữa từ
  · Coherence cao hơn vì giữ trọn ý

Metadata kế thừa từ DocumentPage:
- document_id, source, page (bắt buộc)
- chapter, section (trường filter bổ sung)
- chunk_index, strategy (truy vết)
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

try:
    from .models import Chunk, DocumentPage
except (ImportError, ValueError):
    try:
        from src.models import Chunk, DocumentPage
    except ImportError:
        from models import Chunk, DocumentPage


# ---------------------------------------------------------------------------
# Strategy A — Fixed-size sliding window
# ---------------------------------------------------------------------------

def fixed_size(
    page: DocumentPage,
    size: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """Chia text thành các window cố định với overlap, giữ metadata trang.

    Args:
        page: DocumentPage đã chuẩn hóa.
        size: Độ dài mỗi chunk (ký tự).
        overlap: Số ký tự overlap giữa chunk liền kề.

    Returns:
        Danh sách Chunk với chunk_id duy nhất và metadata đầy đủ.
    """
    text = page.text
    if not text:
        return []

    chunks: list[Chunk] = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + size, len(text))
        chunk_text = text[start:end].strip()

        if chunk_text:
            chunk_id = _make_chunk_id(page.document_id, page.page, "A", idx)
            chunks.append(Chunk(
                chunk_id=chunk_id,
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=chunk_text,
                metadata={
                    **page.metadata,          # kế thừa chapter, section, char_count
                    "strategy": "A",
                    "chunk_index": idx,
                    "chunk_char_count": len(chunk_text),
                },
            ))
            idx += 1

        # Nếu đã tới cuối string, dừng
        if end == len(text):
            break

        # Slide forward: start mới = end - overlap
        start = end - overlap

    return chunks


# ---------------------------------------------------------------------------
# Strategy B/C — Paragraph-aware chunking
# ---------------------------------------------------------------------------

def by_paragraph(
    page: DocumentPage,
    max_size: int = 1000,
    strategy: Literal["B", "C"] = "B",
) -> list[Chunk]:
    """Chia theo paragraph, nối đoạn ngắn, cắt đoạn quá dài theo câu.

    Args:
        page: DocumentPage đã chuẩn hóa.
        max_size: Kích thước tối đa mỗi chunk (ký tự).
        strategy: "B" hoặc "C" (C thêm filter, xử lý giống B, filter áp dụng lúc search).

    Returns:
        Danh sách Chunk với metadata đầy đủ.
    """
    text = page.text
    if not text:
        return []

    # Tách paragraph tại double newline
    raw_paragraphs = [p.strip() for p in re.split(r"\n{2,}", text)]
    raw_paragraphs = [p for p in raw_paragraphs if p]  # bỏ đoạn rỗng

    # Nhóm paragraph ngắn, cắt đoạn quá dài
    grouped: list[str] = _group_paragraphs(raw_paragraphs, max_size)

    chunks: list[Chunk] = []
    for idx, chunk_text in enumerate(grouped):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            continue

        chunk_id = _make_chunk_id(page.document_id, page.page, strategy, idx)
        chunks.append(Chunk(
            chunk_id=chunk_id,
            document_id=page.document_id,
            source=page.source,
            page=page.page,
            text=chunk_text,
            metadata={
                **page.metadata,          # kế thừa chapter, section, char_count
                "strategy": strategy,
                "chunk_index": idx,
                "chunk_char_count": len(chunk_text),
            },
        ))

    return chunks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _group_paragraphs(paragraphs: list[str], max_size: int) -> list[str]:
    """Nối paragraph ngắn, cắt paragraph quá dài.

    Logic:
    1. Nếu paragraph hiện tại + buffer chưa vượt max_size → nối vào buffer
    2. Nếu vượt → flush buffer thành chunk, bắt đầu buffer mới
    3. Paragraph đơn vượt max_size → cắt theo câu
    """
    result: list[str] = []
    buffer = ""

    for para in paragraphs:
        # Paragraph đơn quá lớn → cắt theo câu trước
        if len(para) > max_size:
            # flush buffer hiện tại trước
            if buffer.strip():
                result.append(buffer.strip())
                buffer = ""
            # cắt paragraph dài theo câu
            result.extend(_split_by_sentence(para, max_size))
            continue

        # Nối vào buffer nếu còn chỗ
        tentative = (buffer + "\n\n" + para).strip() if buffer else para
        if len(tentative) <= max_size:
            buffer = tentative
        else:
            # flush và bắt đầu buffer mới
            if buffer.strip():
                result.append(buffer.strip())
            buffer = para

    if buffer.strip():
        result.append(buffer.strip())

    return result


def _split_by_sentence(text: str, max_size: int) -> list[str]:
    """Cắt text dài theo ranh giới câu (dấu . ! ?) thay vì giữa từ.

    Nếu câu đơn vẫn vượt max_size → hard-cut tại max_size.
    """
    # Tokenize theo câu: tách tại ". " hoặc "! " hoặc "? "
    sentences = re.split(r"(?<=[.!?])\s+", text)

    result: list[str] = []
    buffer = ""

    for sent in sentences:
        tentative = (buffer + " " + sent).strip() if buffer else sent
        if len(tentative) <= max_size:
            buffer = tentative
        else:
            if buffer.strip():
                result.append(buffer.strip())
            # Câu đơn quá dài → hard-cut
            if len(sent) > max_size:
                for i in range(0, len(sent), max_size):
                    result.append(sent[i:i + max_size].strip())
                buffer = ""
            else:
                buffer = sent

    if buffer.strip():
        result.append(buffer.strip())

    return result


def _make_chunk_id(document_id: str, page: int, strategy: str, idx: int) -> str:
    """Tạo chunk_id duy nhất và stable (hash-based, không random).

    Format: {doc_id}_p{page}_{strategy}_{idx:04d}
    Dùng thêm hash 6 ký tự để đảm bảo uniqueness khi upsert.
    """
    raw = f"{document_id}|{page}|{strategy}|{idx}"
    h = hashlib.md5(raw.encode()).hexdigest()[:6]
    return f"{document_id}_p{page:04d}_{strategy}_{idx:04d}_{h}"

