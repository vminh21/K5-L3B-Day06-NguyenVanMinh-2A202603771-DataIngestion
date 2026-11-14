"""Evaluation and tracing for retrieval benchmarks.

Metrics:
- Hit@1: The top-1 chunk is from the gold page and contains the gold evidence.
- Evidence Hit@3: At least one chunk in top-3 contains the gold evidence from the gold page.
- Reports ratios n/N separately for dev and test splits.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)


def _normalize_text_for_match(text: str) -> str:
    """Loại bỏ ký tự đặc biệt và chuẩn hóa khoảng trắng để so khớp evidence."""
    # Hạ chữ thường
    text = text.lower()
    # Thay thế các loại dấu gạch ngang (em-dash, en-dash, hyphens) thành space
    text = re.sub(r"[—–\-_]", " ", text)
    # Loại bỏ dấu câu
    text = re.sub(r"[^\w\s]", "", text)
    # Gộp khoảng trắng
    return re.sub(r"\s+", " ", text).strip()


def is_evidence_in_chunk(evidence_quote: str, chunk_text: str) -> bool:
    """Kiểm tra xem evidence_quote có nằm trong chunk_text không."""
    if not evidence_quote or not chunk_text:
        return False

    norm_quote = _normalize_text_for_match(evidence_quote)
    norm_chunk = _normalize_text_for_match(chunk_text)

    # 1. So khớp trực tiếp substring
    if norm_quote in norm_chunk:
        return True

    # 2. Nếu evidence dài, kiểm tra các cụm từ khóa liên tục (70% token match)
    quote_tokens = norm_quote.split()
    if len(quote_tokens) >= 5:
        # Lấy 60% token đầu hoặc giữa
        core_len = max(4, int(len(quote_tokens) * 0.7))
        for start_idx in range(len(quote_tokens) - core_len + 1):
            sub_phrase = " ".join(quote_tokens[start_idx : start_idx + core_len])
            if sub_phrase in norm_chunk:
                return True

    return False


def evaluate_query(
    question: dict[str, Any],
    hits: list[dict[str, Any]],
    strategy: str = "",
) -> dict[str, Any]:
    """Đánh giá kết quả truy xuất cho 1 câu hỏi đối chiếu với gold evidence.

    Returns:
        dict trace đầy đủ thông tin truy xuất và nhãn hit@1, hit@3.
    """
    gold_page = question.get("gold_page")
    evidence_quote = question.get("evidence_quote", "")
    q_id = question.get("id")
    split = question.get("split", "dev")

    evaluated_hits: list[dict[str, Any]] = []
    has_hit_at_1 = False
    has_hit_at_3 = False

    for rank, hit in enumerate(hits, start=1):
        hit_page = hit.get("page")
        chunk_text = hit.get("text", "")
        chunk_id = hit.get("chunk_id", "")
        score = hit.get("score", 0.0)
        metadata = hit.get("metadata", {})

        # Điều kiện hit: đúng trang (hoặc trang liền kề) VÀ chứa evidence quote
        page_match = (hit_page == gold_page)
        evidence_match = is_evidence_in_chunk(evidence_quote, chunk_text)

        is_hit = bool(page_match and evidence_match)

        if rank == 1 and is_hit:
            has_hit_at_1 = True
        if rank <= 3 and is_hit:
            has_hit_at_3 = True

        evaluated_hits.append({
            "rank": rank,
            "chunk_id": chunk_id,
            "page": hit_page,
            "score": round(float(score), 4),
            "page_match": page_match,
            "evidence_match": evidence_match,
            "is_hit": is_hit,
            "text_snippet": chunk_text[:200] + ("..." if len(chunk_text) > 200 else ""),
            "metadata": metadata,
        })

    trace = {
        "question_id": q_id,
        "split": split,
        "type": question.get("type", "direct"),
        "question": question.get("question", ""),
        "expected_answer": question.get("expected_answer", ""),
        "gold_page": gold_page,
        "evidence_quote": evidence_quote,
        "filter": question.get("filter"),
        "strategy": strategy,
        "hit_at_1": has_hit_at_1,
        "hit_at_3": has_hit_at_3,
        "hits": evaluated_hits,
    }

    return trace


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Tổng hợp chỉ số Hit@1 và Evidence Hit@3 theo dev và test split."""
    dev_traces = [t for t in traces if t.get("split") == "dev"]
    test_traces = [t for t in traces if t.get("split") == "test"]

    def calc_split_metrics(split_list: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(split_list)
        if n == 0:
            return {"hit1": "0/0", "hit1_pct": 0.0, "hit3": "0/0", "hit3_pct": 0.0, "count": 0}

        hit1_count = sum(1 for t in split_list if t.get("hit_at_1"))
        hit3_count = sum(1 for t in split_list if t.get("hit_at_3"))

        return {
            "hit1": f"{hit1_count}/{n}",
            "hit1_count": hit1_count,
            "hit1_pct": round(hit1_count / n * 100, 1),
            "hit3": f"{hit3_count}/{n}",
            "hit3_count": hit3_count,
            "hit3_pct": round(hit3_count / n * 100, 1),
            "total_questions": n,
        }

    return {
        "dev": calc_split_metrics(dev_traces),
        "test": calc_split_metrics(test_traces),
        "overall": calc_split_metrics(traces),
    }
