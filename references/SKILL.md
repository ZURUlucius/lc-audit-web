---
name: lc-audit
description: "This skill should be used when the user wants to review, audit, or check compliance of Letter of Credit (LC) documents. It covers LC terms review and document compliance checking. Triggers include: 审核信用证, 审核LC, 信用证条款审核, 交单审核, 交单文件审核, 单据合规, LC compliance, 审核提单, 审核发票, 检查信用证, 信用证报告, LC review, LC audit, document check, 核对单据, 信用证相符性, 审核汇票, 装箱单审核, 信用证不符点, discrepancy check, 检查单据是否符合信用证, 信用证交单准备, 备单审核, 审核 Bill of Lading, 审核 Commercial Invoice, 审核 Packing List."
---

# LC Audit Skill (信用证审核技能)

Audit Letter of Credit documents for compliance, covering both terms review and document checking.

## Overview

This skill provides a structured workflow for:

1. **LC Terms Review** — Extract and analyze all terms from an LC, identify key requirements, and generate a comprehensive review report (PDF)
2. **Document Compliance Check** — Compare submitted documents (BL, CI, PL, Draft, etc.) against LC terms for compliance, cross-check data consistency, and flag discrepancies

## Prerequisites

### Dependencies

Install Python dependencies before starting (if not already installed):

```bash
pip install pdfplumber reportlab pypdfium2 rapidocr-onnxruntime Pillow
```

### CJK Font

The report requires a CJK font. On Windows, the script auto-detects `msyh.ttc` (Microsoft YaHei).
If unavailable, fall back to `simhei.ttf` or `simsun.ttc`.

## Workflow

### Phase 1: Document Extraction

For each input PDF file, extract text content:

1. Copy `scripts/extract_pdf_text.py` to the workspace
2. Run extraction for each PDF:
   ```
   python extract_pdf_text.py INPUT_PDF OUTPUT_TXT
   ```
3. The script auto-detects whether the PDF is text-based or scanned:
   - Text-based: uses `pdfplumber`
   - Scanned/image: falls back to RapidOCR (accuracy ~90-95%)
4. Read the extracted `.txt` files to understand the document contents

### Phase 2A: LC Terms Review Report

When the user wants to **review LC terms only** (no compliance checking):

1. Read the LC text and analyze all SWIFT MT700 fields
2. Read `references/lc_audit_guide.md` for field mapping and audit checkpoints
3. Create a comprehensive PDF report covering:
   - **Basic Info**: LC number, amount, dates, parties, issuing bank
   - **Key Dates**: latest shipment date, presentation period, expiry date
   - **Document Requirements (46A)**: each document type, copies, specific conditions
   - **Additional Conditions (47A)**: insurance, charges, beneficiary contact info, etc.
   - **Bank-Specific Instructions (78)**: sending instructions, reference numbers, fees
   - **⚠️ Clause Anomaly Analysis (条款异常分析)**: unreasonable or self-contradictory clauses found in the LC — see detailed rules below
   - **Compliance Checklist**: actionable checklist for document preparation
   - **Risk Summary**: discrepancy risk matrix with severity levels

4. For the report PDF, use `scripts/generate_lc_review.py` as a template/framework, but the AI agent should customize the content based on the actual LC terms

**Important knowledge for LC terms review:**
- Field 47A often contains bank-specific instructions (e.g., JPMorgan, HSBC special requirements)
- "THE ORIGINAL OF THIS LETTER OF CREDIT MUST BE PRESENTED..." is directed at the **negotiating bank**, NOT the beneficiary — the LC original is held by the advising bank in Safe Custody
- The presentation deadline is: **min(B/L date + presentation period, LC expiry date)**
- Check for double periods in NIT numbers (e.g., "890.101..279-0") — must match exactly

**🚨 CRITICAL — No trade-practice inference (严禁依据行业惯例补充条款):**
Every requirement written in the review report **MUST be traceable to explicit wording in the LC text** (fields 46A, 47A, 45A, 78, or any free-text section). Do NOT add, assume, or infer requirements based on:
- General trade practice (e.g., "it is common to show the L/C number on all documents")
- UCP 600 default rules unless the LC explicitly invokes them for that specific point
- Requirements seen in other LCs reviewed previously

If a common requirement (such as showing the L/C number on documents, or a specific number of copies) is **absent from this LC**, it must be **omitted from the report entirely** — do not include it as a note, recommendation, or checklist item.

**How to verify before writing any requirement:**
1. Identify the exact field and line in the LC text that states the requirement.
2. If you cannot point to a specific sentence in the LC, do not include the requirement.
3. If something is genuinely worth noting as a best practice (not an LC requirement), mark it clearly as "行业惯例（非本证要求）" and place it in a separate "补充建议" section — never mix it into the compliance checklist or document requirements table.

---

**⚠️ Clause Anomaly Analysis — Identifying Unreasonable or Self-Contradictory Clauses (条款异常分析):**

During LC review, actively scan for the following types of anomalies and **include them in a dedicated "条款异常分析" section in the PDF report**, using an amber/orange header to distinguish from normal sections:

**Type 1 — Internal Contradictions (自相矛盾)**
Two or more clauses in the same LC that cannot both be satisfied simultaneously. Examples:
- Field 44E says "ANY PORT IN CHINA" but 47A says "ONLY SHENZHEN PORT ALLOWED"
- Field 43P says "PARTIAL SHIPMENTS: ALLOWED" but 47A says "ONLY ONE SHIPMENT PERMITTED"
- Field 39A specifies a tolerance (e.g., ±5%) but 47A says "EXACT AMOUNT ONLY, NO TOLERANCE"
- Two different presentation periods mentioned in different fields
- B/L consignee in 46A differs from consignee named in 47A

**Type 2 — Operationally Unreasonable Clauses (操作上不合理的条款)**
Clauses that are technically valid but create practical impossibilities or severe disadvantages for the beneficiary. Examples:
- Latest shipment date leaves fewer than 7 days from LC issuance/advising date
- Presentation period is extremely short (e.g., 5 days) leaving no buffer for document preparation
- Penalty clauses that automatically deduct amounts (e.g., "5% deduction if container not 100% full") — flag these clearly as they are unusual and potentially unfair
- Requires documents from third parties that the beneficiary cannot control (e.g., "certificate signed by applicant")
- Automatic deductions for subjective criteria (e.g., "loading quality deduction at buyer's discretion")
- Requires specific carrier names that may conflict with actual market availability

**Type 3 — Ambiguous or Incomplete Clauses (模糊/不完整条款)**
Clauses that lack sufficient detail to execute, leaving interpretation open to dispute:
- Document named without specifying copies/originals (e.g., "CERTIFICATE OF ANALYSIS" with no quantity)
- Address or party name incomplete in a way that could cause discrepancies
- Reference to external documents not attached to the LC (e.g., "AS PER ANNEX A" but no annex provided)
- Contradictory or inconsistent port/destination naming (e.g., different spellings in 44F vs 47A)

**Type 4 — Unusual Bank/Financial Clauses (非常规银行/财务条款)**
Clauses that deviate significantly from standard LC practice:
- Automatic penalty deductions from proceeds (vs. standard discrepancy fee)
- Multiple layers of deductions that could make actual payment significantly less than the LC amount
- Unusually high discrepancy fees
- Clauses that shift risk normally borne by the applicant to the beneficiary

**How to present anomalies in the report:**
- Use a dedicated section titled "条款异常分析 / Clause Anomaly Review" with an amber/orange section header
- For each anomaly found, show a table row with: Anomaly Type | LC Fields Involved | Original LC Text (exact quote) | Issue Description | Recommended Action
- If no anomalies are found, include the section with a green "✅ 未发现条款异常" row
- Anomalies of Type 1 (contradictions) should also be elevated to the Risk Matrix with HIGH severity
- Anomalies of Type 2-4 should appear in the Risk Matrix with MEDIUM severity
- Always recommend the beneficiary seek an amendment for Type 1 contradictions before shipping

**⚠️ Critical: Cross-page PI SKU parsing (跨页PI SKU归属):**
- MT700 messages are often split across multiple parts (e.g., Part 1/3, Part 2/3, Part 3/3). The field 45A (Description of Goods) frequently **spans across parts**.
- A PI header (`+++ AS PER PROFORMA INVOICE NUMBER xxx`) may appear near the end of one part, with its SKUs continuing at the start of the next part. The next PI header only appears after ALL SKUs of the current PI are listed.
- **When parsing SKUs, always trace from a PI header to the NEXT PI header (or end of field 45A), NOT to the end of the current page/part.**
- Common pitfall: stopping SKU collection at page boundaries, causing SKUs to be incorrectly attributed to the previous PI or missed entirely.
- **Verification rule:** After parsing, sum all PI subtotals and verify they add up to the LC total amount (field 32B). If they don't match, re-examine cross-page boundaries.
- Example: In MT700 with 3 parts, a PI starting at the end of Part 1 may have its SKUs split across Part 1 (last 1-2 lines) and Part 2 (first few lines), with the next PI header appearing only after all SKUs.

### Phase 2B: Document Compliance Check Report

When the user wants to **check documents against LC terms**:

1. Extract text from all documents (LC + submitted docs like BL, CI, PL, Draft)
2. Read `references/lc_audit_guide.md` for audit checkpoints per document type
3. Create a compliance report covering:
   - **Summary**: PASS/WARN/FAIL for each document
   - **Cross-Data Check**: compare key fields across all documents (amount, LC number, goods description, quantities, weights, volumes)
   - **Per-Document Review**: detailed check table for each document
   - **Container Detail Cross-Check**: if applicable, match container numbers/seals/CBM between packing list and B/L
   - **Time Compliance**: B/L date vs latest shipment date, presentation deadline calculation
   - **Manual Verification Items**: items that require human verification (especially for OCR-extracted scanned documents)
   - **Discrepancy Summary**: all potential discrepancies with risk level and recommendations

4. For the report PDF, use `scripts/generate_compliance.py` as a template/framework, but customize based on actual document contents

**Important knowledge for compliance checking:**
- Scanned B/L documents require OCR — note this in the report and flag that Consignee/Notify fields need manual verification

**B/L 提单审核 — 货代单 vs 船东单区分（必审项）:**

Every B/L must be identified as one of two types:
- **Master B/L (MBL/船东单)**: Issued by the shipping line/carrier (e.g., "MAERSK LINE", "COSCO", "EVERGREEN"). The carrier is the actual ocean carrier.
- **House B/L (HBL/货代单 / Forwarder B/L)**: Issued by a freight forwarder (NVOCC). The forwarder consolidates cargo and issues their own B/L. A MBL will exist separately under the carrier's name.

**If the B/L is a Forwarder/House B/L (货代单), the following 4 fields are mandatory and must all be present:**
1. **货代名字** — Forwarder company name (the NVOCC issuing the HBL, e.g., "DHL GLOBAL FORWARDING", "KUEHNE + NAGEL")
2. **货代身份** — Forwarder identity (e.g., NVOCC license number, FMC备案号, or similar regulatory registration)
3. **船东名字** — Carrier/shipping line name (the actual ocean carrier performing the shipment, e.g., "MAERSK", "MSC")
4. **船司身份** — Carrier identity (carrier's IMO number or official registration)

> Note: Under UCP 600 Article 20, a transport document must identify the carrier. For a Forwarder B/L, the carrier is the actual shipping line (not the forwarder), so both the forwarder (as issuer) and the carrier (as the carrier) must be named. The forwarder's identity as NVOCC must also appear.

**If the B/L is a Master B/L (船东单), check:**
- Carrier name and identity (IMO number)
- 3 original copies notation ("3/3 ORIGINAL" or equivalent)

**正本份数（All B/L types）:** The B/L must explicitly state the number of original copies presented (e.g., "3/3 ORIGINAL", "ORIGINAL 1 OF 3", "FULL SET 3/3"). LC 46A for this LC requires "FULL SET (3/3) ORIGINAL" — verify the B/L reflects this.
- Cross-check data must be EXACTLY consistent (NIT numbers, addresses, amounts)
- The beneficiary does NOT need to submit the LC original — it's held by the advising bank
- Extra document copies (e.g., JPMorgan requiring +1 invoice copy, +1 transport document copy) must be flagged
- Pay attention to non-standard presentation periods (e.g., 18 days instead of the usual 21 days)

## Report Output

- Generate PDF reports using `reportlab` with CJK font support
- Use consistent visual styling:
  - 🔴 Red header: critical/high-risk sections
  - Blue header: standard sections
  - Green background: PASS items
  - Amber/Yellow background: WARN items
  - Red background: FAIL items
- Reports should be professional and suitable for sharing with banks/clients
- Deliver the final PDF to the user via `deliver_attachments` and `open_result_view`

## CIPL Template (CI+PL 生成模板)

### Template Path

- **TARGET US 客户 CIPL 模板**: `C:\Users\jason.lzx\Desktop\Lucius\TARGET US\1.2. CIPL.xlsm`

### CI Sheet Layout

| Cell Range | Content | Source |
|-----------|---------|--------|
| B1-B4 | 受益人信息（名称/地址行1/地址行2/国家） | LC field 59 |
| B7 | "MESSRS:"（标签，模板内置） | — |
| C7-C10 | 申请人信息（名称/地址行1/地址行2/国家） | LC field 50 |
| F7-F9 | 标签（DATE / INVOICE NO / L/C NO.） | — |
| G7 | 日期 | Invoice Date |
| G8 | 发票号 | Invoice Number |
| G9 | LC号 | LC Number |
| 14-60行 | 数据行（品名/数量/单价/金额等） | LC 45A 货描 + PI |
| 61行 | TOTAL 行 | 自动汇总 |

### PL Sheet Layout

| Cell Range | Content | Source |
|-----------|---------|--------|
| B1-B3 | 受益人信息 | LC field 59 |
| C7-C10 | 申请人信息（公式 =CI!C7 ~ =CI!C10） | 自动跟随CI sheet |
| P7-P9 | 标签（DATE / INVOICE NO / L/C NO.） | — |
| P7 | 日期 | Invoice Date |
| P8 | 发票号 | Invoice Number |
| P9 | LC号 | LC Number |
| 15行+ | 数据行（品名/数量/箱数/毛重/净重/尺码等） | LC 45A 货描 + PI |
| R列 | Container | 集装箱号 |

### 申请人显示规则

- **默认**：C7-C10 显示 LC field 50 的申请人信息
- **如条款有特殊要求**：按条款调整（例如某些LC要求显示其他收货方）
- PL sheet 通过公式 `=CI!C7`~`=CI!C10` 自动同步，无需额外写入

### .xlsm 文件生成注意事项

- openpyxl 的 `save()` 会丢失 `xl/vbaProject.bin`、`xl/calcChain.xml`、`xl/printerSettings/` 等组件
- 解决方案：ZIP 层级修补策略（详见 Working Memory 中的 openpyxl 处理 .xlsm 文件章节）
- 关键：不要保留模板的 sharedStrings.xml（openpyxl 用内联字符串代替）

## Common Pitfalls (踩坑经验)

- `pdfplumber` returns empty text for scanned PDFs — must fall back to OCR
- On Windows, `pdf2image` requires `poppler` which may not be installed — use `pypdfium2` instead
- RapidOCR works well without system-level dependencies (unlike Tesseract)
- Python's `color` parameter conflicts with Python 3.13 keyword — use `hdr_color` or similar variable names instead
- B/L Consignee field often contains very long names with multiple entities and NIT numbers — OCR accuracy drops for these
- When comparing data across documents, normalize whitespace and formatting (e.g., "56,268.940 KGS" vs "56,268.94 KGS")
- Some LCs have non-standard field layouts — do not rely solely on SWIFT tag parsing; also scan for free-text instructions
- **Cross-page PI SKU parsing error**: When field 45A spans multiple MT700 parts, a PI's SKUs may be split across pages. Always trace from PI header to the NEXT PI header, not to page boundaries. Always verify by summing all PI subtotals against the LC total amount (32B) — if they don't match, check for split SKUs at page transitions
- **行业惯例误写入报告 / Trade-practice items incorrectly written as LC requirements**: e.g., writing "all documents must show L/C number" when the LC has no such clause. Always verify each checklist item against a specific field+line in the LC text. If no source exists, omit it. Discovered in LC 30/00482 (FELYX TOYS, Bulgaria) — the LC has no requirement to show L/C number on documents.
- **ReportLab `backColor` parameter does NOT work in `ParagraphStyle`**: `ParagraphStyle`'s `backColor` parameter is ignored by ReportLab's rendering engine. Badge/cell background colors rendered this way silently disappear, causing colored status badges to appear as plain black text. Fix: use a `Table` wrapper (single-cell table) with `TableStyle([("BACKGROUND", ...)])` to apply background colors reliably. Use `textColor` in `ParagraphStyle` for foreground text color. This pattern should be used for all status badges (`tag_cell()` / `tag()`) in the PDF report.
- **ReportLab `colWidths` must sum to exactly 17cm for A4**: When a table's `colWidths` sum to less than 17cm (A4 minus 2cm left + 2cm right margins), ReportLab stretches the table to fill the full width — but only proportionally. Narrow columns get wider, which can cause layout shifts. Ensure all main content tables have `colWidths` totaling exactly 17cm, and status badge columns use a dedicated narrow width (e.g., `1.6*cm` or `2.0*cm`) within the total.
- **交单备查清单 LC依据必须精确到字段+条款编号**: Every checklist item's LC reference must be traceable to an exact field number and specific clause number in the MT700 text. Do NOT write references like `"行业惯例"`, `"46A"`, or `"47A第12条"` unless that exact clause exists in the LC. For example: `"46A第3-6项"` for B/L requirements (referencing the specific 4 carrier options), `"47A第12条"` for the no-draft clause, `"44E"` for port of loading, etc. Verify each reference against the extracted LC text before writing it into the checklist.
- **45A货描一致性核对缺失 / Missing goods description consistency check**: LC 45A goods description must ALWAYS be cross-checked against the Commercial Invoice and Packing List. Common discrepancies include: item description wording, SKU/item code, unit of measure (PCS vs PC), currency symbol (USD vs US$), incoterms specificity (LC says "FOB ANY PORT OF CHINA" but invoice shows "FOB YANTIAN PORT OF CHINA" — this is generally acceptable as Yantian is a Chinese port, but must be explicitly noted). Always include a dedicated 45A vs CI/PL consistency table in the report. Discovered in LC DC HK1205569 (ZURU INC).
- **ReportLab + Emoji rendering: colored emoji glyphs render as black squares**: ReportLab uses CJK fonts (msyh.ttc / simhei.ttf) that do NOT support colored Unicode emoji (U+1F534 🔴, U+1F7E1 🟡, U+1F7E2 🟢, U+26A0 ⚠, etc.). When these emoji appear inside a `Paragraph`, the font renders them as a black glyph or a blank rectangle — even if `textColor` is set. The `TableStyle` row background colors (RED_LIGHT, AMBER, etc.) are actually applied; the problem is the emoji character itself is black. Fix: replace all emoji with plain ASCII/Unicode text alternatives that the font can render: use `tag_cell("FAIL", "FAIL")` (which uses Table BACKGROUND) for red badges; use `tag_cell("WARN", "WARN")` for amber; use `[!]` or `[! WARNING]` for inline alert markers; use `[x]` or `FAIL` text instead of `🔴`. Never use colored emoji as visual indicators in PDF reports generated by ReportLab.
- **CJK fonts also fail on many CJK-compatible symbols**: Beyond emoji, several CJK-compatible-area characters also render as black/blank in msyh.ttc / simhei.ttf, including: **circled numbers ①-⑳** (U+2460-U+2473), **box-drawing characters** (U+2500-U+257F), **ballot box ☐/☒** (U+2610/U+2611), **white square □/■** (U+25A1/U+25A0), **arrow →←↑↓** (U+2190-U+2195), **emoji PRESENTATION** characters. Safe alternatives: use plain ASCII text like `(1) (2) (3)` instead of ① ② ③; use `-` or `->` instead of `→`; use `[ ]` or `[x]` instead of `☐`; use plain text like `[CHECKLIST]` instead of `📋`. Note: box-drawing chars in Python source code comments (`# ─── SECTION ───`) are fine — they never reach the PDF. Only text inside `Paragraph()` or string literals used in the PDF matters.
- **SWIFT MT700 冒号分隔符清理 / SWIFT colon delimiter cleanup**: LC original text contains excessive `::` or `:::` colons used as SWIFT MT700 field/sub-field delimiters. When displaying clause original text in reports, these colons appear as meaningless visual clutter (e.g., `::::` between every sub-field). Fix: use `_clean_lc_colons()` function to convert `::` → newline, strip leading/trailing colons, collapse multiple spaces, and limit consecutive newlines to max 2. Apply this cleanup to all places where raw LC text is displayed: clause original text boxes, 47A snippet text, and any field showing unprocessed LC content.
- **PDF 报告紧凑排版规范 / Compact PDF report layout standards**: To avoid excessive whitespace that makes reports look sparse and wastes pages:
  - Title fontSize should be ~20pt (not larger than 22pt); h1 spaceBefore ≤ 10mm; h2 spaceBefore ≤ 6mm
  - Body text fontSize should be 9pt with leading 14; small text 8pt with leading 12
  - All `Spacer` values should be minimal: section gaps 2-4mm, intra-section gaps 1-2mm
  - Table cell padding: TOPPADDING/BOTTOMPADDING = 3 (not 4), LEFTPADDING/RIGHTPADDING = 2 (not 3)
  - HRFlowable spaceAfter should be 3-4mm (not 8mm)
  - Remove unnecessary `PageBreak()` calls — let ReportLab's natural page flow handle pagination
  - B/L (Bill of Lading) related special requirement tags should use **yellow/amber** color (`C.AMBER_BD`) for visual distinction from other document types (which use blue)
  - All table `colWidths` must sum to exactly 174mm (= 210mm A4 width minus 18mm×2 margins) — verify this when adding or modifying tables
- **HTML 标签残留清理 / HTML tag artifact cleanup**: When report content includes strings that were originally HTML-formatted (e.g., draft reasons, snippet text from web sources), residual tags like `<br/>`, `<i>`, `<b>`, `<font ...>` may appear as visible garbled text in the PDF. Always clean HTML tags before passing content to `Paragraph()`: use `re.sub(r'</?(?:br|b|i|font|/?[^>]+)>', '', text)` to strip them.
- **PDF 文件文本提取增强 / Enhanced PDF text extraction for compliance check**: The web app's compliance check pipeline (`app.py → pdf_extractor.py → compliance.py`) has been significantly enhanced to handle problematic PDFs:
  - **`pdf_extractor.py`** now uses a multi-strategy extraction approach: (1) `pdfplumber` standard mode → (2) `pdfplumber` layout mode (for table-heavy docs) → (3) `pdfplumber` table extraction fallback → (4) **RapidOCR + pypdfium2** OCR at 2x scale → (5) **PyMuPDF** as final fallback. Each page is independently evaluated.
  - **OCR auto-detect**: If `pdfplumber` yields <50 chars total OR <15 chars per page on average, the system automatically falls back to OCR without user intervention.
  - **Landscape page handling**: For the first page, if initial OCR returns <3 lines of text, the system automatically tries rotating the image 90° before re-OCR — this handles landscape-oriented documents (e.g., some B/L formats).
  - **Post-processing**: Extracted text goes through `_post_process()` which cleans OCR noise, merges broken words across line breaks, compresses whitespace, and normalizes punctuation.
  - **Content-based document type detection**: `compliance.py`'s `identify_document_type()` now uses a two-layer approach: Layer 1 matches filename keywords (fast), and if that fails, Layer 2 analyzes the extracted text content against a keyword-weighted scoring system with ~100+ patterns covering BL/CI/PL/Draft/Origin/Certificate/etc. This means even files uploaded with generic names like "Other Document" or "未知单据" can be correctly identified based on their actual content.
  - **`guess_document_type()` in pdf_extractor.py**: Provides an independent content-analysis guess that is passed through `extract_with_metadata()` metadata, so `app.py` can pre-label documents before they reach `check_compliance()`.
  - **Key lesson from LC 55146100065**: All submitted document PDFs showed as "未知单据" because `identify_document_type()` only checked filename keywords (which were generic like "B/L", "CI" from form keys), and when those didn't match the specific patterns, it fell through to "未知单据". The fix adds content-driven type detection as Layer 2 so that even with generic filenames, the document type is correctly identified from the actual text content.
- **Web app function signature alignment**: When integrating modules developed separately into a Flask pipeline, always verify cross-module call signatures match. Common issues include: wrong parameter count, passing raw lists vs dict-wrapped objects, and assuming internal helper functions exist. The pattern `check_compliance(lc_text, lc_analysis, doc_results, doc_labels)` and `generate_compliance_report(lc_analysis, checks, summary, doc_labels, output_path)` must be kept consistent between callers and definitions.
- **Undefined variable in compliance.py B/L check (`t_lower`)**: In `compliance.py` line ~776, the "Clean On Board" check condition used `t_lower` which was never defined — only `t_upper = text.upper()` existed. This caused `NameError: name 't_lower' is not defined` on the web app when checking Bill of Lading documents. Fix: replace `t_lower` with `t_upper`. Always run a quick grep for variable consistency after copy-pasting conditional blocks.


