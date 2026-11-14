"""Read and normalize source documents.

Kỹ thuật:
- Đọc PDF bằng pypdf (text-based, không cần OCR với Cambridge Handbook 2025)
- Chuẩn hóa Unicode NFC (unicodedata) để đồng nhất encoding
- Giữ cấu trúc paragraph bằng cách preserve double newline, collapse single newline
- Trích metadata từ nội dung trang: chapter, section heading
- Ghi log trang rỗng/lỗi ra stderr
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

try:
    from .models import DocumentPage
except (ImportError, ValueError):
    try:
        from src.models import DocumentPage
    except ImportError:
        from models import DocumentPage

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Section/chapter detection from Manifesto of the Communist Party
# ---------------------------------------------------------------------------

# Cấu hình phân chia dữ liệu Raw theo từng Chương (Chapter-level Partitions)
CHAPTER_SPECS = [
    {
        "id": "01_Preamble",
        "chapter": "Preamble",
        "title": "Introduction / Preamble",
        "pages": [2],
        "file": "01_Preamble.txt",
    },
    {
        "id": "02_Chapter_I",
        "chapter": "Chapter I",
        "title": "Bourgeois and Proletarians",
        "pages": list(range(3, 13)),
        "file": "02_Chapter_I_Bourgeois_and_Proletarians.txt",
    },
    {
        "id": "03_Chapter_II",
        "chapter": "Chapter II",
        "title": "Proletarians and Communists",
        "pages": list(range(13, 22)),
        "file": "03_Chapter_II_Proletarians_and_Communists.txt",
    },
    {
        "id": "04_Chapter_III",
        "chapter": "Chapter III",
        "title": "Socialist and Communist Literature",
        "pages": list(range(22, 31)),
        "file": "04_Chapter_III_Socialist_and_Communist_Literature.txt",
    },
    {
        "id": "05_Chapter_IV",
        "chapter": "Chapter IV",
        "title": "Position of the Communists in Relation to Opposition Parties",
        "pages": [31, 32],
        "file": "05_Chapter_IV_Position_of_the_Communists.txt",
    },
    {
        "id": "06_Appendix",
        "chapter": "Appendix",
        "title": "Prefaces to Various Editions (1872-1893)",
        "pages": list(range(33, 45)),
        "file": "06_Appendix_Prefaces.txt",
    },
]

COVER_SPEC = {
    "id": "00_Cover",
    "chapter": "Cover_and_Metadata",
    "title": "Title & Publication Information",
    "pages": [1],
    "file": "00_Cover_and_Metadata.txt",
}

# Ánh xạ nhanh trang -> Chương
_PAGE_TO_CHAPTER = {
    p: spec["chapter"] for spec in CHAPTER_SPECS for p in spec["pages"]
}

# Trang bìa bị loại khỏi nội dung tính điểm
_EXCLUDED_PAGES = {1}

# Ánh xạ section theo mục lục và trang xuất hiện
_PAGE_TO_SECTION = {
    2: "Preamble",
    3: "Bourgeois and Proletarians",
    13: "Proletarians and Communists",
    22: "1. Reactionary Socialism",
    23: "1. Reactionary Socialism",
    24: "1. Reactionary Socialism",
    25: "1. Reactionary Socialism",
    26: "1. Reactionary Socialism",
    27: "2. Conservative or Bourgeois Socialism",
    28: "2. Conservative or Bourgeois Socialism",
    29: "3. Critical-Utopian Socialism and Communism",
    30: "3. Critical-Utopian Socialism and Communism",
    31: "Position of the Communists in Relation to Opposition Parties",
    32: "Position of the Communists in Relation to Opposition Parties",
    33: "The 1872 German Edition",
    34: "The 1882 Russian Edition",
    35: "The 1883 German Edition",
    36: "The 1888 English Edition",
    37: "The 1888 English Edition",
    38: "The 1888 English Edition",
    39: "The 1890 German Edition",
    40: "The 1890 German Edition",
    41: "The 1890 German Edition",
    42: "The 1892 Polish Edition",
    43: "The 1893 Italian Edition",
    44: "The 1893 Italian Edition",
}


def _detect_section(page_num: int) -> str | None:
    """Lấy tên section heading theo trang."""
    return _PAGE_TO_SECTION.get(page_num, _PAGE_TO_CHAPTER.get(page_num))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    min_chars: int = 50,
    save_raw: bool = True,
    raw_dir: Path | None = None,
) -> list[DocumentPage]:
    """Đọc từng trang PDF, tách lưu dữ liệu raw theo từng CHƯƠNG (Bronze layer), chuẩn hóa text, gắn metadata.

    Args:
        path: Đường dẫn tới file PDF.
        document_id: ID định danh tài liệu (dùng trong manifest).
        source: URL hoặc path gốc (truy vết nguồn).
        min_chars: Trang có ít hơn số ký tự này bị coi là rỗng/lỗi.
        save_raw: Nếu True, xuất các file raw chia theo CHƯƠNG và manifest_raw.json.
        raw_dir: Thư mục lưu dữ liệu raw (mặc định: `path.parent / "raw"`).

    Returns:
        Danh sách DocumentPage cho các trang nội dung (đã loại bìa/TOC/index).
        Trang rỗng/lỗi được ghi log nhưng không trả về.
    """
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pypdf import PdfReader
            reader = PdfReader(str(path))
    except ImportError as exc:
        raise RuntimeError("pypdf is required: pip install 'pypdf>=5,<7'") from exc

    total = len(reader.pages)
    log.info("Opened %s — %d physical pages", path.name, total)

    target_raw_dir = raw_dir or (path.parent / "raw")
    if save_raw:
        target_raw_dir.mkdir(parents=True, exist_ok=True)

    pages: list[DocumentPage] = []
    empty_pages: list[int] = []
    excluded_pages: list[int] = []
    raw_by_page: dict[int, str] = {}
    normalized_by_page: dict[int, str] = {}

    for i, pdf_page in enumerate(reader.pages):
        page_num = i + 1  # 1-indexed, matches PDF page number

        # Extract raw text nguyên bản 100% từ PDF
        try:
            raw = pdf_page.extract_text() or ""
        except Exception as exc:
            log.warning("Page %d: extract_text() failed — %s", page_num, exc)
            empty_pages.append(page_num)
            raw = ""

        raw_by_page[page_num] = raw

        is_excluded = page_num in _EXCLUDED_PAGES
        if is_excluded:
            excluded_pages.append(page_num)
            continue

        normalized = normalize_text(raw)
        normalized_by_page[page_num] = normalized

        # Ghi log trang rỗng
        if len(normalized) < min_chars:
            log.warning("Page %d: too short (%d chars) — marked as empty", page_num, len(normalized))
            empty_pages.append(page_num)
            continue

        # Metadata: chapter và section từ TOC + nội dung trang
        chapter = _PAGE_TO_CHAPTER.get(page_num, "unknown")
        section = _detect_section(page_num)

        # Tìm tên file raw của chương chứa trang này
        chapter_spec = next((spec for spec in CHAPTER_SPECS if page_num in spec["pages"]), None)
        raw_chapter_file = chapter_spec["file"] if chapter_spec else "unknown"

        metadata = {
            "chapter": chapter,
            "section": section,  # None nếu không tìm thấy heading
            "char_count": len(normalized),
            "raw_char_count": len(raw),
            "raw_chapter_file": raw_chapter_file,
        }

        pages.append(DocumentPage(
            document_id=document_id,
            source=source,
            page=page_num,
            text=normalized,
            metadata=metadata,
        ))

    # XUẤT CÁC FILE RAW CHIA THEO CHƯƠNG (Partition raw layer by chapter)
    chapter_manifest_records: list[dict] = []
    if save_raw:
        # Xóa các file page_*.txt cũ nếu có để data/raw hoàn toàn sạch chia theo chương
        for old_f in target_raw_dir.glob("page_*.txt"):
            try:
                old_f.unlink()
            except Exception:
                pass

        all_specs = [COVER_SPEC] + CHAPTER_SPECS
        for spec in all_specs:
            spec_pages = spec["pages"]
            chapter_file_path = target_raw_dir / spec["file"]

            page_range_str = f"{spec_pages[0]}" if len(spec_pages) == 1 else f"{spec_pages[0]}–{spec_pages[-1]}"
            header_banner = (
                f"{'=' * 80}\n"
                f"MANIFESTO OF THE COMMUNIST PARTY — RAW EXTRACT\n"
                f"CHƯƠNG: {spec['title'].upper()} (Trang {page_range_str})\n"
                f"{'=' * 80}\n\n"
            )

            sections_content = []
            total_raw_chars = 0
            total_clean_chars = 0

            for p in spec_pages:
                raw_text_p = raw_by_page.get(p, "")
                clean_text_p = normalized_by_page.get(p, "")
                total_raw_chars += len(raw_text_p)
                total_clean_chars += len(clean_text_p)

                sections_content.append(
                    f"--- [TRANG VẬT LÝ {p}] ---\n"
                    f"{raw_text_p.strip()}\n"
                )

            full_chapter_content = header_banner + "\n\n".join(sections_content) + "\n"
            chapter_file_path.write_text(full_chapter_content, encoding="utf-8")

            chapter_manifest_records.append({
                "chapter_id": spec["id"],
                "chapter_name": spec["chapter"],
                "title": spec["title"],
                "file": spec["file"],
                "page_range": page_range_str,
                "page_count": len(spec_pages),
                "pages": spec_pages,
                "is_content_chapter": spec["id"] != "00_Cover",
                "char_count_raw": total_raw_chars,
                "char_count_clean": total_clean_chars,
            })

        # Lưu manifest_raw.json với thông tin phân chia theo chương
        import json
        manifest_raw_file = target_raw_dir / "manifest_raw.json"
        manifest_raw_file.write_text(
            json.dumps({
                "document_id": document_id,
                "source": source,
                "partition_strategy": "by_chapter",
                "total_physical_pages": total,
                "content_pages_count": len(pages),
                "excluded_pages": excluded_pages,
                "empty_pages": empty_pages,
                "raw_files_directory": str(target_raw_dir),
                "chapters_count": len(CHAPTER_SPECS),
                "chapters": chapter_manifest_records,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Saved raw partitions by chapter to: %s", target_raw_dir)

    # Summary log
    log.info(
        "load_pdf done | content pages: %d | excluded (cover/toc/index): %s | empty/error: %s",
        len(pages),
        excluded_pages,
        empty_pages if empty_pages else "none",
    )
    if empty_pages:
        log.warning("Empty/error pages (not ingested): %s", empty_pages)

    return pages


# Pattern loại bỏ running header cố định ở đầu mỗi trang PDF:
# "Manifesto of the Communist Party \n Karl Marx and Frederick Engels \n Marxists Internet Archive (marxists.org) 2005"
_HEADER_PATTERN = re.compile(
    r"^\s*Manifesto\s+of\s+the\s+Communist\s+Party\s*\n\s*Karl\s+Marx\s+and\s+Frederick\s+Engels\s*(\n\s*|\s+)Marxists\s+Internet\s+Archive\s*\(marxists\.org\)\s*2005\s*",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Chuẩn hóa Unicode, loại bỏ header rác và whitespace, giữ cấu trúc paragraph.

    Kỹ thuật:
    1. Bóc bỏ running header lặp lại ở đầu trang (Manifesto of the Communist Party... 2005)
    2. NFC normalization — đồng nhất ký tự Unicode tổ hợp
    3. Loại ký tự điều khiển (ASCII < 32) trừ \n và \t
    4. Chuẩn hóa dấu xuống dòng (Windows \r\n, Mac \r → \n)
    5. Giữ double newline (\n\n) phân cách đoạn văn
    6. Thu gọn whitespace thừa trong từng dòng
    """
    # 1. Bóc bỏ running header rác ở đầu mỗi trang
    text = _HEADER_PATTERN.sub("", text)

    # 2. Unicode NFC
    text = unicodedata.normalize("NFC", text)

    # 3. Loại ký tự điều khiển (ASCII < 32) trừ \n và \t
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)

    # 4. Normalize line endings (Windows \r\n, Mac \r → \n)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 5. Collapse multiple blank lines thành double newline (phân cách paragraph)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 6. Collapse whitespace thừa trong mỗi dòng (trừ \n)
    text = re.sub(r"[^\S\n]+", " ", text)

    # 7. Trim mỗi dòng
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


# ---------------------------------------------------------------------------
# CLI / Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    pdf_candidate = Path("data/manifest.pdf")
    if not pdf_candidate.exists():
        pdf_candidate = Path("../data/manifest.pdf")

    if not pdf_candidate.exists():
        log.error("Could not find manifest.pdf at data/manifest.pdf or ../data/manifest.pdf")
        sys.exit(1)

    print("=" * 70)
    print("INGESTION & RAW PARTITIONING PIPELINE")
    print("=" * 70)
    print(f"Reading PDF: {pdf_candidate.resolve()}")

    loaded_pages = load_pdf(
        path=pdf_candidate,
        document_id="communist-manifesto-1848",
        source=str(pdf_candidate),
        save_raw=True,
    )

    raw_dir = pdf_candidate.parent / "raw"
    raw_files = sorted(list(raw_dir.glob("*.txt")))

    print(f"\n[OK] Đã chia tách dữ liệu PDF thành {len(raw_files)} file raw theo CHƯƠNG tại: {raw_dir}")
    print(f"[OK] Số trang nội dung hợp lệ: {len(loaded_pages)} trang (từ trang 2 đến trang 44)")
    print(f"[OK] File tổng hợp metadata tầng thô: {raw_dir / 'manifest_raw.json'}")

    print("\n" + "=" * 75)
    print("DANH SÁCH CÁC TỆP RAW ĐÃ PHÂN CHIA THEO CHƯƠNG (BRONZE LAYER)")
    print("=" * 75)
    for rf in raw_files:
        size_kb = rf.stat().st_size / 1024
        print(f"  • {rf.name:<55} ({size_kb:.1f} KB)")

    # Hiển thị minh chứng 2 file raw chương mẫu
    print("\n" + "=" * 75)
    print("MINH CHỨNG NỘI DUNG RAW NGUYÊN BẢN CỦA 2 CHƯƠNG TIÊU BIỂU")
    print("=" * 75)

    sample_chapter_files = [
        "01_Preamble.txt",
        "02_Chapter_I_Bourgeois_and_Proletarians.txt",
    ]

    for fname in sample_chapter_files:
        sample_file = raw_dir / fname
        if sample_file.exists():
            content = sample_file.read_text(encoding="utf-8")
            print(f"\n>>> [FILE RAW CHƯƠNG: {sample_file.name}] ({len(content)} ký tự thô):")
            print("-" * 65)
            print(content[:420].strip() + "\n... [phần còn lại của chương] ...")
            print("-" * 65)



