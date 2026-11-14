# Báo cáo cá nhân — Day 6

**Họ và tên:** Nguyễn Văn Minh  
**MSSV:** 2A202603771  
**Lớp:** L3B  
**Chủ đề & Corpus:** *Tuyên ngôn của Đảng Cộng sản (Manifesto of the Communist Party)* — Karl Marx & Frederick Engels  
**Kho lưu trữ mã nguồn:** [starter/src/](starter/src/)  

---

## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - *Chủ đề:* Tài liệu chính trị - kinh tế - triết học kinh điển *Tuyên ngôn của Đảng Cộng sản* (bản dịch tiếng Anh chính thức của Samuel Moore năm 1888 dưới sự biên tập của Frederick Engels).
  - *Nguồn & Giấy phép:* Tải từ [Marxists Internet Archive (marxists.org)](https://www.marxists.org/archive/marx/works/1848/communist-manifesto/) ấn bản năm 2005. Thuộc phạm vi công cộng (**Public Domain**), không chứa thông tin cá nhân hay bí mật thương mại, được phép phân phối và nghiên cứu tự do.
  - *Số trang vật lý và quy tắc tính trang:* File PDF gốc `data/manifest.pdf` có tổng cộng 44 trang vật lý. Áp dụng quy tắc loại trừ: Trang 1 là trang bìa và thông tin ấn bản/colophon (`excluded_pages = [1]`). Toàn bộ các trang từ 2 đến 44 là trang nội dung thực tế chứa văn bản liên tục của tác phẩm. Tổng số trang nội dung hợp lệ là **43 trang** ($\ge 30$ trang theo quy định của Rubric). Tổng số ký tự nội dung đã chuẩn hóa đạt 118,900 ký tự.
- **Chuẩn hóa, lỗi và giới hạn:**
  - *Bóc tách nhiễu hệ thống (Noise Stripping):* Toàn bộ 43 trang của tài liệu gốc bị dính 3 dòng running header lặp lại: `Manifesto of the Communist Party \n Karl Marx and Frederick Engels \n Marxists Internet Archive (marxists.org) 2005`. Nếu không loại bỏ, header này sẽ làm loãng embedding của chunk đầu mỗi trang. Pipeline sử dụng regex `_HEADER_PATTERN` để bóc tách 100% header này trước khi xử lý.
  - *Chuẩn hóa Unicode & Định dạng:* Sử dụng `unicodedata.normalize("NFC", text)` để đồng nhất bảng mã Unicode; loại bỏ ký tự điều khiển ASCII < 32 (non-printable); chuẩn hóa dấu ngắt dòng về `\n`; bảo tồn các khoảng ngắt đoạn kép (`\n\n`) để phục vụ thuật toán chunking theo đoạn; collapse khoảng trắng thừa trong mỗi dòng.
  - *Ghi nhận lỗi & Trang rỗng:* Trong quá trình đọc, hàm `load_pdf` theo dõi ngưỡng `min_chars = 50`. Toàn bộ 43 trang nội dung đều có dung lượng từ 890 đến 3,700 ký tự, không có trang nào bị lỗi đọc hoặc rỗng (`empty/error: none`).
  - *Tầng lưu trữ dữ liệu thô (Bronze Layer):* Trước khi làm sạch, pipeline đã phân chia và lưu trữ dữ liệu thô nguyên bản của 6 chương và 1 bìa vào thư mục `data/raw/` (`00_Cover_and_Metadata.txt` đến `06_Appendix_Prefaces.txt`) cùng `manifest_raw.json` để bảo toàn khả năng truy vết nguồn gốc (Data Lineage).
- **Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí:**
  - *Embedding Model:* `embeddinggemma` chạy hoàn toàn local qua Ollama (`http://localhost:11434`), kiến trúc Gemma 3 text embedding của Google DeepMind, tham số: 307M, kích thước vector biểu diễn: **768 chiều**.
  - *Asymmetric Retrieval Task Prefixes:* Để phát huy tối đa độ chính xác của EmbeddingGemma, pipeline áp dụng tiền tố chỉ dẫn theo đặc tả của Google: văn bản tài liệu được gắn `title: Manifesto of the Communist Party | text: <chunk>`, còn câu hỏi truy vấn được gắn `task: search result | query: <question>`.
  - *Vector Store:* PostgreSQL 16 kết hợp extension `pgvector` (phiên bản `pgvector 0.7.4`), triển khai bằng Docker Compose nội bộ trên cổng `127.0.0.1:55433`. Bảng lưu trữ `doc_chunks` lưu `chunk_id` (PRIMARY KEY, băm MD5), `strategy`, `document_id`, `page`, `text`, `metadata` (JSONB) và `embedding` (vector 768 chiều).
  - *Metric tìm kiếm:* Cosine distance (`<=>`). Đánh chỉ mục GIN trên trường `metadata` để tăng tốc độ lọc kết hợp.
  - *Chi phí & Lệnh chạy:* Chạy local 100% qua Docker và Ollama, chi phí gọi API là **$0.00**. Lệnh chạy pipeline: `python -m src.run` (kích hoạt trong môi trường ảo `starter/.venv`).
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - *Trường bắt buộc:* `document_id` (`communist-manifesto-1848`), `source` (`data/manifest.pdf`), `page` (trang vật lý từ 2 đến 44).
  - *Trường bổ sung:*
    1. `chapter`: Tên chương lớn (`Preamble`, `Chapter I`, `Chapter II`, `Chapter III`, `Chapter IV`, `Appendix`). Nguồn trích xuất từ cấu trúc bảng mục lục chuẩn của Manifesto. Lý do chọn: Cho phép thu hẹp không gian tìm kiếm vào từng phần luận điểm cụ thể, tránh va chạm ngữ nghĩa giữa các chương.
    2. `section`: Tên tiểu mục / ấn bản cụ thể (ví dụ: `Bourgeois and Proletarians`, `Proletarians and Communists`, `1. Reactionary Socialism`, `The 1888 English Edition`, v.v.). Lý do chọn: Cực kỳ hữu dụng khi người dùng tìm kiếm chính xác quan điểm của Marx-Engels trong một trào lưu hoặc ấn bản lịch sử cụ thể.
    3. `raw_chapter_file`: Tên tệp raw tương ứng trong `data/raw/` phục vụ kiểm tra đối chiếu nguồn gốc.

---

## Cấu hình và benchmark
- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):**
  - **Strategy A (Fixed-size Window):** Chia văn bản theo cửa sổ trượt kích thước cố định `chunk_size = 500` ký tự, độ gối `overlap = 50` ký tự, không phân biệt ranh giới câu/đoạn. Sinh ra **263 chunks**. Metadata: `document_id`, `source`, `page`, `chapter`, `section`. Không áp dụng bộ lọc khi truy xuất.
  - **Strategy B (Paragraph-aware Semantic Boundary):** Chia văn bản theo ranh giới đoạn văn tự nhiên (dựa trên dấu ngắt `\n\n`), gộp các đoạn liên tiếp cho đến khi đạt tối đa `max_size = 1000` ký tự, không overlap (`overlap = 0`). Sinh ra **158 chunks** (giảm 40% số chunk so với A nhưng bảo tồn trọn vẹn ngữ cảnh). Cùng metadata như A, không áp dụng bộ lọc khi truy xuất.
  - **Strategy C (Paragraph-aware + Metadata Filter):** Giữ **chính xác 100%** cách chia chunk, tham số `max_size = 1000`, `overlap = 0` và số lượng chunk (158 chunks) như Strategy B. **Khác biệt duy nhất:** Khi câu truy vấn có yêu cầu ngữ cảnh (ví dụ chỉ định rõ trong `Chapter I` hay `Chapter II`), Strategy C sẽ kích hoạt mệnh đề lọc `WHERE metadata @> filter_dict` trên PostgreSQL trước khi tính khoảng cách Cosine.
- **≥20 câu: phân chia ≥15 dev / ≥5 test, câu metadata filter và cách kiểm chứng evidence:**
  - Bộ benchmark gồm **22 câu hỏi** bằng tiếng Anh được thiết kế thủ công trước khi chạy thử nghiệm, lưu tại [benchmark/questions.json](benchmark/questions.json).
  - *Phân chia split:* **17 câu Dev** (tỷ lệ 77.3%) và **5 câu Test** (tỷ lệ 22.7%), đảm bảo điều kiện $\ge 15$ dev và $\ge 5$ test của đề bài.
  - *Độ đa dạng câu hỏi:* Gồm câu hỏi sự thật trực tiếp (`truc_tiep`: 12 câu), câu hỏi diễn đạt lại / ý nghĩa (`dien_dat_lai`: 6 câu), và câu hỏi có điều kiện / ngoại lệ (`dieu_kien_ngoai_le`: 4 câu).
  - *Câu hỏi Metadata Filter:* Có 4 câu hỏi chứa filter metadata xác thực (`q07`, `q11`, `q14`, `q19`), trong đó có đúng **1 câu thuộc tập Test** (`q19`, yêu cầu filter `{"chapter": "Chapter I"}`).
  - *Kiểm chứng Evidence:* 100% các đoạn `evidence_quote` đều được trích xuất trực tiếp từ các trang nội dung sau khi chuẩn hóa của file PDF, đảm bảo chuỗi ký tự tồn tại chính xác tại `gold_page`.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test:**
  - Để tránh thiên lệch (overfitting/cherry-picking) vào tập Test, tiêu chí lựa chọn chiến lược tối ưu được đóng băng trước như sau:
    1. Ưu tiên 1: Độ hoàn thiện ngữ cảnh (**Chunk Coherence** $\ge 1.5/2.0$) để đảm bảo chunk trả về cho mô hình sinh không bị cụt câu, mất chủ ngữ.
    2. Ưu tiên 2: Độ chính xác truy xuất bằng chứng (**Evidence Hit@3** trên tập Dev $\ge 80\%$).
    3. Ưu tiên 3: Tiết kiệm tài nguyên lưu trữ và thời gian xử lý (số lượng chunk ít hơn để giảm chi phí vector database).

---

## Kết quả

### Bảng 1: Kết quả truy xuất Benchmark (Hit@1 & Hit@3)

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **A** (Fixed 500, overlap 50) | dev | 13/17 (76.5%) | 15/17 (88.2%) | 263 | 0.85s | $0.00 |
| **A** (Fixed 500, overlap 50) | test | 3/5 (60.0%) | 5/5 (100.0%) | 263 | 0.85s | $0.00 |
| **B** (Paragraph max 1000) | dev | 12/17 (70.6%) | 14/17 (82.4%) | 158 | 0.81s | $0.00 |
| **B** (Paragraph max 1000) | test | 3/5 (60.0%) | 4/5 (80.0%) | 158 | 0.81s | $0.00 |
| **C** (Paragraph + Filter) | dev | 12/17 (70.6%) | 14/17 (82.4%) | 158 | 0.86s | $0.00 |
| **C** (Paragraph + Filter) | test | 3/5 (60.0%) | 4/5 (80.0%) | 158 | 0.86s | $0.00 |

### Bảng 2: Kết quả đánh giá thủ công 5 chiều chất lượng

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|:---:|:---:|:---:|:---:|
| **A** | 0.8/2 (n=10) | 15/15 (100.0%) | N/A | 0: 0 câu, 1: 2 câu, 2: 3 câu (TB: 1.6/2) |
| **B** | 2.0/2 (n=10) | 15/15 (100.0%) | N/A | 0: 1 câu, 1: 1 câu, 2: 3 câu (TB: 1.4/2) |
| **C** | 2.0/2 (n=10) | 15/15 (100.0%) | 1/1 (100.0%) | 0: 1 câu, 1: 1 câu, 2: 3 câu (TB: 1.4/2) |

- **Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
  - *Traces đầy đủ:* Toàn bộ truy vấn, Top-3 hits, điểm cosine similarity, metadata và nhãn match được lưu tại: [starter/results/traces_A.json](starter/results/traces_A.json), [starter/results/traces_B.json](starter/results/traces_B.json), và [starter/results/traces_C.json](starter/results/traces_C.json).
  - *Nhãn chấm thủ công:* Lưu chi tiết tại [starter/results/audit_manual.json](starter/results/audit_manual.json).
  - *Cách chọn mẫu Coherence (Tiêu chí 2):* Chọn 10 vị trí trang cố định trải dài trên toàn bộ tài liệu: Trang `[2, 3, 5, 8, 10, 14, 18, 21, 28, 35]`. Tại mỗi trang, lấy chunk chứa phần đầu của trang để chấm độc lập trên thang điểm 0-2 (0 = cắt giữa ý, 1 = hiểu một phần, 2 = tự hiểu trọn ý).
  - *Cách chọn mẫu Metadata & Grounding (Tiêu chí 3 & 4):* Đánh giá trên toàn bộ 5 câu hỏi của tập Test (`q18`, `q19`, `q20`, `q21`, `q22`), mỗi câu kiểm tra 3 chunks trong Top-3 (tổng cộng 15 chunks / chiến lược).

---

## Phân tích và kết luận

- **So sánh A–B và B–C; 2 ví dụ sai có ID câu và nguồn:**
  - *So sánh A vs B (Tác động của chiến lược Chunking):*
    - Về mặt số lượng và tài nguyên, Strategy B chỉ cần **158 chunks** so với **263 chunks** của Strategy A (tiết kiệm gần 40% chi phí lưu trữ và tính toán vector).
    - Về mặt ngữ nghĩa (**Chunk Coherence**), Strategy B vượt trội hoàn toàn với điểm số tuyệt đối **2.0/2.0** so với **0.8/2.0** của Strategy A. Trong Strategy A, do cắt cứng theo mốc 500 ký tự, có tới 30% mẫu bị cắt đứt giữa câu hoặc mở đầu bằng một mệnh đề phụ không có chủ ngữ (ví dụ: `does the bourgeoisie get over these crises?...` ở trang 8). Trong khi đó, Strategy B ngắt trọn vẹn theo paragraph (`\n\n`), đảm bảo nguyên vẹn logic của từng luận điểm.
    - Về độ chính xác truy xuất (Hit@3), Strategy A đạt 88.2% trên Dev và 100% trên Test, cao hơn Strategy B (82.4% Dev, 80% Test). Lý do: Cửa sổ 500 ký tự với overlap 50 ký tự của A tạo ra mật độ điểm lấy mẫu dày hơn, giúp "bắt trúng" các câu hỏi ngắn cụ thể; tuy nhiên độ dài ngắn này khiến chunk bị phân mảnh ngữ cảnh.
  - *So sánh B vs C (Tác động của Metadata Filtering):*
    - B và C có cùng thuật toán chunking. Khác biệt xảy ra ở các câu hỏi có điều kiện lọc metadata.
    - Tại câu `q19` (Test), câu hỏi yêu cầu tìm thông tin vũ khí của giai cấp tư sản trong `Chapter I`. Strategy C áp dụng `filter: {"chapter": "Chapter I"}`, đảm bảo 100% kết quả Top-3 đều thuộc Chương I, loại bỏ hoàn toàn nguy cơ rò rỉ chunk từ các chương khác. Với các câu hỏi không có filter, kết quả của B và C hoàn toàn tương đồng.
  - *Phân tích 2 trường hợp truy xuất thất bại cụ thể:*
    1. **Ca lỗi 1 — Câu `q11` (Split: Dev, Strategy B, Top-3 không trúng):**
       - *Câu hỏi:* `"In Chapter II, what is the first measure listed as generally applicable in the most advanced countries?"`
       - *Gold Source:* Trang 21, Evidence: `"1. Abolition of property in land and application of all rents of land to public purposes."`
       - *Thực tế truy xuất (Top-1):* Mô hình trả về chunk ở Trang 21 nhưng chỉ chứa câu mở đầu: `"Nevertheless, in most advanced countries, the following will be pretty generally applicable:"` (Score: 0.4659).
       - *Nguyên nhân:* Do văn bản gốc ngắt dòng đôi (`\n\n`) giữa câu mở đầu và danh sách 10 biện pháp, bộ tách đoạn của Strategy B đã tách câu giới thiệu thành một chunk riêng. Chunk này có độ tương đồng ngữ nghĩa rất cao với câu hỏi ("most advanced countries... generally applicable"), nhưng nội dung biện pháp số 1 lại nằm ở chunk kế tiếp. Kết quả: `page_match = True` nhưng `evidence_match = False`.
    2. **Ca lỗi 2 — Câu `q22` (Split: Test, Strategy B/C, Top-3 không trúng):**
       - *Câu hỏi:* `"According to the 1893 Italian edition preface, what condition is necessary for the rule of the bourgeoisie in any country?"`
       - *Gold Source:* Trang 44 (Lời tựa bản tiếng Ý 1893), Evidence: `"But in any country the rule of the bourgeoisie is impossible without national independence..."`
       - *Thực tế truy xuất:* Top-1 rơi vào Trang 12 (Chương I, Score: 0.4742) với đoạn: `"The essential conditions for the existence and for the sway of the bourgeois class is the formation..."`
       - *Nguyên nhân:* **Hiện tượng va chạm ngữ nghĩa (Semantic Collision)**. Từ khóa *"rule of the bourgeoisie"* và *"essential condition"* xuất hiện rất nổi bật ở phần kết Chương I (Trang 12), tạo lực hút vector mạnh hơn đoạn Lời tựa ngắn ở Trang 44. Do câu `q22` không có metadata filter, bộ truy xuất dày đặc (Dense Retriever) đã bị kéo lệch sang Chương I.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - *Chiến lược được chọn:* **Strategy B (kết hợp cơ chế lọc có chọn lọc như Strategy C)** là giải pháp tối ưu cho hệ thống RAG thực tế.
  - *Đánh đổi (Trade-off):* Chấp nhận hy sinh một phần nhỏ độ bao phủ thô của Hit@3 (giảm từ 100% của A xuống 80% của B trên tập Test nhỏ) để đổi lấy **Chunk Coherence đạt mức hoàn hảo (2.0/2.0)** và giảm 40% chi phí lưu trữ/tính toán. Trong kiến trúc RAG sinh câu trả lời, một chunk mạch lạc giữ trọn ý nghĩa quan trọng hơn nhiều so với một chunk bị cắt cụt đầu đuôi (vốn dễ gây ảo giác cho LLM).
  - *Điều kiện áp dụng:* Strategy B/C đặc biệt phù hợp với các tài liệu có cấu trúc văn bản phân đoạn rõ ràng (sách, chính sách, tài liệu kỹ thuật, handbook). Nếu tài liệu là văn bản phi cấu trúc hoặc chứa nhiều bảng biểu ngắn, cần bổ sung chunking đa tầng (hierarchical/parent-document retrieval).
- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí:**
  - *Hạn chế dữ liệu & văn phong lịch sử:* Tài liệu *Tuyên ngôn* viết từ năm 1848 với văn phong thế kỷ 19, mật độ thuật ngữ triết học dày đặc và nhiều mệnh đề phức hợp, khiến các câu đơn lẻ có thể bị phụ thuộc ngữ cảnh lớn vào đoạn văn đứng trước.
  - *Quy mô tập Test nhỏ:* Tập Test gồm 5 câu hỏi chỉ mang tính chất minh họa và kiểm tra nhanh (sanity check), chưa đủ lớn về mặt thống kê để khẳng định độ tin cậy tuyệt đối giữa các biến thể.
  - *Đo lường chi phí/thời gian:* Toàn bộ pipeline chạy trên máy local MacBook (Ollama + PostgreSQL Docker), chi phí đo được bằng 0. Khi triển khai trên đám mây (Cloud API), chi phí embedding và vector storage sẽ tỷ lệ thuận với số lượng chunk (ưu thế lớn cho Strategy B).
- **Nếu làm lại hoặc mở rộng, cải tiến gì?**
  - **1. Hybrid Search (Dense Vector + Sparse BM25):** Kết hợp tìm kiếm ngữ nghĩa của `embeddinggemma` với tìm kiếm từ khóa chính xác BM25 (thông qua PostgreSQL `tsvector` hoặc `pg_search`). Điều này sẽ giải quyết triệt để các ca lỗi như `q11` (tìm số thứ tự "1.") hoặc `q22` (tìm chính xác từ khóa "1893 Italian edition").
  - **2. Reranking Layer (Cross-Encoder):** Bổ sung một mô hình Reranker nhẹ (như `bge-reranker-large` hoặc `colbert`) để xếp hạng lại Top-10 chunks trước khi lấy Top-3, giúp khắc phục hiện tượng va chạm ngữ nghĩa giữa các chương.
  - **3. Parent-Document Retrieval:** Lưu trữ các đoạn chunk nhỏ để embed chính xác, nhưng khi trả về cho LLM sẽ trả về toàn bộ đoạn văn bản cha (Parent Chunk) để bảo đảm 100% ngữ cảnh trả lời.

