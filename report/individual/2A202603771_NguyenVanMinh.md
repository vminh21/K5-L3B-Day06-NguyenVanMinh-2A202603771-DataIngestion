# Báo cáo cá nhân — Day 6

**Họ và tên:** Nguyễn Văn Minh | **MSSV:** 2A202603771 | **Lớp:** L3B  
**Chủ đề & Corpus:** *Tuyên ngôn của Đảng Cộng sản (Manifesto of the Communist Party)* — Karl Marx & Frederick Engels  
**Kho lưu trữ:** [starter/src/](starter/src/) | **Giao diện Web UI (Bonus):** [app_streamlit.py](app_streamlit.py)  

---

## Dữ liệu và pipeline

### 1. Bảng tóm tắt thông số dữ liệu & môi trường
| Tiêu chí | Chi tiết cấu hình | Ghi chú kỹ thuật |
| :--- | :--- | :--- |
| **Corpus & Tác phẩm** | *Manifesto of the Communist Party* (1848) | Bản dịch tiếng Anh chính thức của Samuel Moore (1888), Engels hiệu đính. |
| **Nguồn & Bản quyền** | [Marxists Internet Archive (marxists.org)](https://www.marxists.org/archive/marx/works/1848/communist-manifesto/) (2005) | **Public Domain** — Hoàn toàn tự do nghiên cứu, không chứa PII / bí mật. |
| **Quy tắc tính trang** | Tổng: **44 trang vật lý**; Bìa/colophon: **1 trang** (`page 1`); Nội dung: **43 trang** (`pages 2–44`) | Đạt yêu cầu $\ge 30$ trang nội dung hợp lệ; tổng 118,900 ký tự. |
| **Tầng thô (Bronze)** | `data/raw/` (7 tệp text chia theo chương) | Lưu trữ nguyên bản 100% kèm [manifest_raw.json](data/raw/manifest_raw.json) phục vụ truy vết. |
| **Làm sạch (Silver)** | Regex `_HEADER_PATTERN` gọt sạch header 3 dòng lặp lại | Chuẩn hóa Unicode NFC, loại ký tự điều khiển ASCII < 32, bảo tồn `\n\n`. |
| **Embedding Model** | `embeddinggemma` (Google DeepMind) qua Ollama Local | 307M params, **768 chiều**, áp dụng Asymmetric prefixes (`title:` / `task:`). |
| **Vector Database** | PostgreSQL 16 + `pgvector 0.7.4` (cổng `55433`) | Bảng `doc_chunks`, metric Cosine (`<=>`), chỉ mục GIN cho metadata JSONB. |
| **Chi phí & Lệnh chạy** | **$0.00** (Local 100%) | `python -m src.run` (trong virtualenv `starter/.venv`). |

### 2. Thiết kế Metadata phục vụ truy vết và lọc
| Trường metadata | Kiểu | Nguồn giá trị | Lý do chọn & Tính hữu dụng |
| :--- | :---: | :--- | :--- |
| `document_id` *(Bắt buộc)* | `str` | `communist-manifesto-1848` | Định danh tài liệu duy nhất trong toàn hệ thống. |
| `source` *(Bắt buộc)* | `str` | `data/manifest.pdf` | Đường dẫn truy vết ngược về tệp nguồn vật lý. |
| `page` *(Bắt buộc)* | `int` | Số trang PDF (2 đến 44) | Căn cứ định vị bằng chứng và đối chiếu `gold_page` của Benchmark. |
| `chapter` *(Lọc bổ sung)* | `str` | Mục lục tác phẩm (Preamble, Ch. I–IV, Appendix) | Thu hẹp không gian tìm kiếm, triệt tiêu va chạm ngữ nghĩa giữa các chương. |
| `section` *(Lọc bổ sung)* | `str` | Tiêu đề tiểu mục / ấn bản cụ thể | Định vị các luận điểm chuyên sâu (ví dụ: *1. Reactionary Socialism*). |
| `raw_chapter_file` | `str` | Tên tệp trong `data/raw/` | Bảo đảm khả năng đối soát 2 chiều (Data Lineage) từ Chunk về Raw. |

---

## Cấu hình và benchmark

### 1. Bảng thông số 3 chiến lược đối chứng (A / B / C)
| Chiến lược | Cơ chế phân đoạn (Chunking) | Kích thước & Overlap | Bộ lọc Metadata khi truy xuất | Số lượng Chunks |
| :---: | :--- | :---: | :---: | :---: |
| **Strategy A** | Cửa sổ trượt cố định (Fixed sliding window) | Size = 500 ký tự, Overlap = 50 | Không lọc (`None`) | **263 chunks** |
| **Strategy B** | Ranh giới đoạn văn tự nhiên (Paragraph-aware) | Max = 1000 ký tự, Overlap = 0 | Không lọc (`None`) | **158 chunks** |
| **Strategy C** | Tương đồng 100% Strategy B | Max = 1000 ký tự, Overlap = 0 | **Lọc theo `chapter`/`section`** | **158 chunks** |

> *Ghi chú kiểm soát biến số:* B–C **chỉ khác nhau duy nhất 1 yếu tố** là việc kích hoạt bộ lọc metadata; A–B chỉ khác nhau thuật toán chia chunk.

### 2. Phân bổ Benchmark & Tiêu chí khóa trước (Frozen Criteria)
* **Bộ câu hỏi:** 22 câu hỏi được biên soạn và kiểm chứng 100% evidence trước khi chạy, lưu tại [benchmark/questions.json](benchmark/questions.json).
  * **Tập Dev (17 câu - 77.3%):** Dùng để phân tích lỗi và điều chỉnh thuật toán.
  * **Tập Test (5 câu - 22.7%):** Giữ kín đánh giá khách quan cuối cùng (`q18` đến `q22`).
  * **Câu hỏi Filter:** 4 câu (`q07`, `q11`, `q14`, `q19`), trong đó `q19` nằm ở tập Test để kiểm tra độ tuân thủ filter độc lập.
* **Tiêu chí lựa chọn chiến lược (Chốt trước khi xem kết quả Test):**
  1. *Ưu tiên 1:* **Chunk Coherence** $\ge 1.5/2.0$ (bảo đảm ngữ cảnh trọn vẹn, không cắt đứt câu).
  2. *Ưu tiên 2:* **Dev Hit@3** $\ge 80\%$ (bảo đảm độ phủ bằng chứng).
  3. *Ưu tiên 3:* **Tiết kiệm tài nguyên** (tối thiểu hóa số lượng chunk lưu trong vector DB).

---

## Kết quả

### Bảng 1: Kết quả truy xuất Benchmark (Hit@1 & Hit@3)
| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian chạy | Chi phí |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A** (Fixed 500/50) | **dev** | 13/17 (76.5%) | 15/17 (88.2%) | 263 | 0.85s | $0.00 |
| **A** (Fixed 500/50) | **test** | 3/5 (60.0%) | 5/5 (100.0%) | 263 | 0.85s | $0.00 |
| **B** (Paragraph 1000) | **dev** | 12/17 (70.6%) | 14/17 (82.4%) | 158 | 0.81s | $0.00 |
| **B** (Paragraph 1000) | **test** | 3/5 (60.0%) | 4/5 (80.0%) | 158 | 0.81s | $0.00 |
| **C** (Paragraph + Filter) | **dev** | 12/17 (70.6%) | 14/17 (82.4%) | 158 | 0.86s | $0.00 |
| **C** (Paragraph + Filter) | **test** | 3/5 (60.0%) | 4/5 (80.0%) | 158 | 0.86s | $0.00 |

### Bảng 2: Kết quả thẩm định chất lượng 5 chiều (Manual Audit)
| Strategy | Coherence trung bình /2 (n=10) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N) | Grounding 0/1/2 (số câu) và TB /2 |
| :---: | :---: | :---: | :---: | :---: |
| **A** | **0.8 / 2.0** *(Kém)* | 15/15 (100.0%) | N/A | Mức 0: 0 câu, Mức 1: 2 câu, Mức 2: 3 câu *(TB: 1.6/2)* |
| **B** | **2.0 / 2.0** *(Tối đa)* | 15/15 (100.0%) | N/A | Mức 0: 1 câu, Mức 1: 1 câu, Mức 2: 3 câu *(TB: 1.4/2)* |
| **C** | **2.0 / 2.0** *(Tối đa)* | 15/15 (100.0%) | **1/1 (100.0%)** | Mức 0: 1 câu, Mức 1: 1 câu, Mức 2: 3 câu *(TB: 1.4/2)* |

* **Minh chứng lưu trữ:**
  * Dữ liệu trace: [results/traces_A.json](results/traces_A.json), [results/traces_B.json](results/traces_B.json), [results/traces_C.json](results/traces_C.json).
  * Chỉ số tổng hợp & Audit: [results/metrics.json](results/metrics.json) và [results/audit_manual.json](results/audit_manual.json).
  * Mẫu Coherence lấy tại 10 trang: `[2, 3, 5, 8, 10, 14, 18, 21, 28, 35]`; Mẫu Metadata & Grounding lấy trên toàn bộ 5 câu test $\times$ Top-3 (15 chunks).

---

## Phân tích và kết luận

### 1. Bảng so sánh Strategy A–B và B–C
| Khía cạnh | So sánh Strategy A vs Strategy B | So sánh Strategy B vs Strategy C |
| :--- | :--- | :--- |
| **Cắt gọt & Ngữ cảnh** | Strategy B vượt trội về độ mạch lạc (Coherence **2.0 vs 0.8**). A bị cắt cụt đầu đuôi ở 30% mẫu do giới hạn 500 ký tự. | B và C cùng giữ trọn vẹn đoạn văn (`\n\n`), không làm vỡ cấu trúc câu. |
| **Tài nguyên & DB** | Strategy B chỉ tạo **158 chunks** (tiết kiệm gần **40%** vector storage so với 263 chunks của A). | Tương đồng 100% về dung lượng và số lượng vector. |
| **Tác động của Lọc** | Không áp dụng bộ lọc. | Strategy C áp dụng `filter: {"chapter": "Chapter I"}` tại câu `q19`, **bảo đảm 100% Top-3 chunks thuộc Chương I**, triệt tiêu nguy cơ rò rỉ ngoại lai. |

### 2. Phân tích 2 trường hợp truy xuất thất bại cụ thể
| Thông tin lỗi | Ca lỗi 1 — Câu `q11` (Tập Dev, Strategy B) | Ca lỗi 2 — Câu `q22` (Tập Test, Strategy B/C) |
| :--- | :--- | :--- |
| **Câu hỏi & Nguồn** | *"In Chapter II, what is the first measure listed as generally applicable...?"* | *"According to the 1893 Italian edition preface, what condition is necessary...?"* |
| **Gold Evidence** | Trang 21: `"1. Abolition of property in land and application of all rents..."` | Trang 44: `"rule of the bourgeoisie is impossible without national independence..."` |
| **Kết quả thực tế** | Top-1 rơi vào Trang 21 nhưng chỉ lấy câu dẫn: `"Nevertheless, in most advanced countries..."` | Top-1 bị kéo sang Trang 12 (Chương I): `"The essential conditions for the existence and for the sway..."` |
| **Nguyên nhân cốt lõi** | **Phân rã danh sách (List Separation):** Dấu ngắt dòng đôi `\n\n` giữa câu giới thiệu và mục số 1 khiến chúng bị tách thành 2 chunk. Chunk 1 khớp ngữ nghĩa câu hỏi nhưng thiếu bằng chứng. | **Va chạm ngữ nghĩa (Semantic Collision):** Cụm từ *"rule of bourgeoisie"* và *"essential condition"* ở Chương I có mật độ từ vựng mạnh hơn đoạn Lời tựa ngắn ở Trang 44. |

### 3. Chiến lược lựa chọn, Giới hạn & Cải tiến
* **Chiến lược được chọn:** **Strategy B (kết hợp lọc Metadata như Strategy C)** là giải pháp tối ưu cho ứng dụng RAG thực tế vì đạt Coherence tuyệt đối (2.0/2.0), triệt tiêu nguy cơ ảo giác và tiết kiệm 40% chi phí.
* **Hạn chế:** Văn phong triết học thế kỷ 19 phức hợp; tập test nhỏ (5 câu) chỉ mang tính minh họa nhanh; môi trường local chưa phản ánh độ trễ mạng thực tế.
* **Hướng cải tiến tương lai:**
  1. *Hybrid Search (BM25 + Dense Vector):* Tích hợp PostgreSQL `tsvector` để sửa lỗi tìm kiếm danh sách số (`q11`) hoặc ấn bản cụ thể (`q22`).
  2. *Cross-Encoder Reranker:* Dùng model xếp hạng lại (như `bge-reranker`) để lọc Top-10 về Top-3, xử lý triệt để va chạm ngữ nghĩa.

---

## Phần mở rộng (Bonus): Ứng dụng RAG Chatbot Local

Để chứng minh tính ứng dụng thực tiễn của dữ liệu sau khi Ingestion, em đã phát triển thêm **2 giao diện RAG Chatbot hoàn chỉnh** chạy hoàn toàn offline trên máy:

| Thành phần Bonus | Tệp nguồn | Công nghệ & Tính năng | Lệnh khởi chạy |
| :--- | :---: | :--- | :--- |
| **1. RAG Console CLI** | [rag_chatbot.py](rag_chatbot.py) | - Pipeline: `embeddinggemma` + `pgvector` + `qwen3:1.7b`<br/>- Stream token thời gian thực trên terminal<br/>- In nguồn trích dẫn: Trang, Chương, Cosine Score | `source starter/.venv/bin/activate`<br/>`python rag_chatbot.py` |
| **2. Streamlit Web UI** | [app_streamlit.py](app_streamlit.py) | - Giao diện Web trực quan, hiện đại tại `http://localhost:8501`<br/>- Thanh Sidebar tùy biến động Strategy A/B/C, Top-K, Chapter Filter<br/>- 4 nút hỏi nhanh các luận điểm kinh điển<br/>- Expander mở rộng xem toàn văn bằng chứng gốc | `source starter/.venv/bin/activate`<br/>`streamlit run app_streamlit.py` |
