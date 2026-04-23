# -*- coding: utf-8 -*-
"""
PDF Text Extractor - 增强版
支持：
1. 文本型 PDF（pdfplumber）— 首选
2. 扫描/图片型 PDF（RapidOCR + pypdfium2）— 自动降级
3. 加密/损坏 PDF — 多策略尝试
4. 低质量 OCR 结果 — 后处理清洗
5. 详细的提取日志（用于调试）
"""

import os
import re
import tempfile
import logging

logger = logging.getLogger(__name__)

# 模式匹配：识别已生成的审核报告（非原始信用证）
_REPORT_PATTERNS = [
    re.compile(r'信用证.*条款审核报告', re.IGNORECASE),
    re.compile(r'LC\s*Audit', re.IGNORECASE),
    re.compile(r'交单合规审核报告', re.IGNORECASE),
    re.compile(r'Compliance\s*Check\s*Report', re.IGNORECASE),
    re.compile(r'审核结论|风险与异常分析', re.IGNORECASE),
    re.compile(r'本报告由.*系统自动生成', re.IGNORECASE),
    re.compile(r'Discrepancy\s*(Report|Letter)', re.IGNORECASE),
]

# 单据类型识别关键词（用于从文本内容推断单据类型）
_DOC_TYPE_PATTERNS = [
    # (类型名称, 关键词列表, 权重)
    ("海运提单 (Bill of Lading)", ["BILL OF LADING", "B/L", "BILLS OF LADING", "OCEAN B/L", "MASTER B/L", "HOUSE B/L", " vessel ", " PORT OF LOADING ", "PORT OF DISCHARGE", "CONTAINER NO", "SHIPPER", "CONSIGNEE", "FREIGHT", "SEAL NO"], 10),
    ("航空运单 (Airway Bill)", ["AIRWAY BILL", "AWB", "AIRWAYBILL", "AIR CARGO", "FLIGHT NO", "AIRPORT OF DEPARTURE"], 8),
    ("商业发票 (Commercial Invoice)", ["COMMERCIAL INVOICE", "INVOICE NO", "INVOICE DATE", "TOTAL AMOUNT", "UNIT PRICE", "QUANTITY", "DESCRIPTION OF GOODS"], 9),
    ("形式发票 (Proforma Invoice)", ["PROFORMA INVOICE", "PROFORMA"], 7),
    ("装箱单 (Packing List)", ["PACKING LIST", "PACKING WEIGHT", "GROSS WEIGHT", "NET WEIGHT", "MEASUREMENT", "CBM", "NO. OF PACKAGES", "CARTONS", "PALLET"], 9),
    ("重量单 (Weight List)", ["WEIGHT LIST", "WEIGHT MEMO", "WEIGHT NOTE"], 6),
    ("原产地证 (Certificate of Origin)", ["CERTIFICATE OF ORIGIN", "C/O", "CERTIFIED TRUE COPY", "COUNTRY OF ORIGIN"], 8),
    ("保险单 (Insurance Policy/Certificate)", ["INSURANCE POLICY", "INSURANCE CERTIFICATE", "OPEN POLICY", "CERTIFICATE OF INSURANCE", "MODE AND CONVEYANCE", "INSURED VALUE"], 8),
    ("汇票 (Draft/Bill of Exchange)", ["EXCHANGE FOR", "DRAFT", "BILL OF EXCHANGE", "AT SIGHT", "DAYS AFTER SIGHT", "PAY TO THE ORDER OF", "TENOR"], 9),
    ("检验证书 (Inspection Certificate)", ["INSPECTION CERTIFICATE", "INSPECTION REPORT", "QUALITY INSPECTION", "INSPECTION AND TESTING"], 7),
    ("品质证明书 (Quality Certificate)", ["QUALITY CERTIFICATE", "CERTIFICATE OF QUALITY", "QUALITY REPORT"], 5),
    ("数量证明书 (Quantity Certificate)", ["QUANTITY CERTIFICATE", "CERTIFICATE OF QUANTITY"], 5),
    ("受益人证明 (Beneficiary's Certificate)", ["BENEFICIARY'S CERTIFICATE", "BENEFICIARY CERTIFICATE", "BENEFICIARY'S DECLARATION", "BENEFICIARY DECLARATION"], 6),
    ("装运通知 (Shipping Advice)", ["SHIPPING ADVICE", "ADVICE OF SHIPMENT", "SHIPPING NOTICE", "NOTICE OF SHIPMENT"], 5),
    ("电放保函 (Telex Release)", ["TELEX RELEASE", "LETTER OF INDemnity for Telex Release", "LOI TELEX RELEASE"], 5),
]


def is_likely_report_pdf(text: str) -> bool:
    """
    判断提取的文本是否来自已生成的审核报告（而非原始信用证 MT700）。
    """
    if not text or len(text.strip()) < 50:
        return False

    # 强特征：命中任何一个报告标题模式
    for pat in _REPORT_PATTERNS:
        if pat.search(text):
            return True

    # 弱特征：有 HTML 标签 + 无 SWIFT 字段格式
    has_html = bool(re.search(r'<[bB]>|</[bB]>|&amp;|&lt;|&gt;', text))
    has_swift_fields = bool(re.search(r':\d{2}[A-Z]?\s*:', text))
    if has_html and not has_swift_fields:
        return True

    return False


def detect_lc_type(pdf_path):
    """
    上传文件类型检测结果。

    Returns:
        ('original', text, is_ocr) — 原始信用证 PDF
        ('report', text, is_ocr)   — 已生成的报告 PDF（误上传）
        ('unknown', text, is_ocr)  — 无法确定
    """
    text, is_ocr = _do_extract(pdf_path)

    if not text or len(text.strip()) < 50:
        return ('unknown', text, is_ocr)

    if is_likely_report_pdf(text):
        return ('report', text, is_ocr)

    # 有 SWIFT MT700 字段 → 原始信用证
    if re.search(r':\d{2}[A-Z]?\s*:', text):
        return ('original', text, is_ocr)

    return ('unknown', text, is_ocr)


def extract_text(pdf_path):
    """
    Extract text from a PDF file (向后兼容接口).
    Returns (text: str, is_ocr: bool)
    """
    lc_type, text, is_ocr = _do_extract_with_type(pdf_path)
    return text, is_ocr


def extract_with_metadata(pdf_path):
    """
    增强版提取接口，返回更多信息。
    
    Returns dict:
        text: str           提取到的文本内容
        is_ocr: bool        是否使用了 OCR
        doc_type_guess: str 猜测的单据类型（基于内容）
        page_count: int     总页数
        method: str         使用的提取方法名
        confidence: str     提取置信度 (high/medium/low/fail)
        warnings: list[str] 警告信息列表
    """
    result = {
        "text": "",
        "is_ocr": False,
        "doc_type_guess": "",
        "page_count": 0,
        "method": "none",
        "confidence": "fail",
        "warnings": [],
    }

    try:
        from pdfplumber import open as pdfplumber_open

        with pdfplumber_open(pdf_path) as pdf:
            result["page_count"] = len(pdf.pages)
            pages = []
            has_text_pages = 0
            total_chars = 0

            for i, page in enumerate(pdf.pages):
                # 尝试多种提取策略
                text = None
                
                # 策略1: 标准 extract_text
                try:
                    text = page.extract_text()
                    if text and len(text.strip()) > 20:
                        has_text_pages += 1
                        total_chars += len(text.strip())
                        pages.append(f"--- Page {i+1} ---\n{text}")
                        continue
                except Exception:
                    pass

                # 策略2: 尝试用 layout 模式提取（对表格型文档更友好）
                try:
                    text = page.extract_text(layout=True)
                    if text and len(text.strip()) > 20:
                        has_text_pages += 1
                        total_chars += len(text.strip())
                        pages.append(f"--- Page {i+1} ---\n{text}")
                        continue
                except Exception:
                    pass

                # 策略3: 尝试提取表格并合并
                try:
                    tables = page.extract_tables()
                    if tables:
                        table_texts = []
                        for table in tables:
                            for row in table:
                                if row:
                                    row_text = " | ".join([str(c) if c else "" for c in row])
                                    table_texts.append(row_text)
                        if table_texts:
                            combined = "\n".join(table_texts)
                            has_text_pages += 1
                            total_chars += len(combined)
                            pages.append(f"--- Page {i+1} [TABLE] ---\n{combined}")
                            continue
                except Exception:
                    pass

            raw_result = "\n\n".join(pages)

            # 判断文本量是否足够
            min_chars = max(50, result["page_count"] * 15)  # 每页至少15个有效字符
            if len(raw_result.strip()) >= min_chars and has_text_pages >= (result["page_count"] + 1) // 2:
                result["text"] = raw_result
                result["method"] = "pdfplumber"
                result["confidence"] = "high" if total_chars > 500 else "medium"

    except ImportError:
        result["warnings"].append("pdfplumber 未安装，将尝试 OCR")
    except Exception as e:
        result["warnings"].append(f"pdfplumber 失败: {str(e)}")

    # === 如果 pdfplumber 提取不足，使用 OCR 降级 ===
    if len(result["text"].strip()) < 50 or result["confidence"] == "fail":
        ocr_text, ocr_meta = _try_ocr(pdf_path)
        if ocr_text and len(ocr_text.strip()) >= 50:
            result["text"] = ocr_text
            result["is_ocr"] = True
            result["method"] = ocr_meta.get("method", "ocr")
            result["confidence"] = ocr_meta.get("confidence", "medium")
            result["warnings"].extend(ocr_meta.get("warnings", []))

    # === 最终后处理 ===
    if result["text"]:
        result["text"] = _post_process(result["text"])
        
        # 猜测单据类型
        result["doc_type_guess"] = guess_document_type(result["text"])

        # 更新置信度
        if len(result["text"]) < 100:
            result["confidence"] = "low"
            result["warnings"].append("提取文本较短，可能信息不完整")
    else:
        result["warnings"].append("所有提取方式均未能获得有效文本")
        result["confidence"] = "fail"

    return result


def _do_extract_with_type(pdf_path):
    """内部：提取文本并检测类型（简化版）"""
    meta = extract_with_metadata(pdf_path)
    lc_type = 'report' if is_likely_report_pdf(meta["text"]) else 'original'
    return (lc_type, meta["text"], meta["is_ocr"])


def _do_extract(pdf_path):
    """实际执行 PDF 文本提取（向后兼容内部函数）"""
    meta = extract_with_metadata(pdf_path)
    return meta["text"], meta["is_ocr"]


def _try_ocr(pdf_path):
    """尝试多种 OCR 方式提取文本"""
    result = {"method": "", "confidence": "fail", "warnings": []}
    all_text = []

    # 方法 1: RapidOCR + pypdfium2（首选）
    try:
        import pypdfium2 as pdfium
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR

        ocr = RapidOCR()
        doc = pdfium.PdfDocument(pdf_path)
        page_count = len(doc)

        for i in range(page_count):
            page = doc[i]
            
            # 先用高分辨率渲染
            bitmap = page.render(scale=2.0, rotation=0)
            img = bitmap.to_pil()

            if img:
                ocr_result, _ = ocr(img)
                if ocr_result:
                    page_text = "\n".join([line[1] for line in ocr_result])
                    all_text.append(f"--- Page {i+1} (OCR-Rapid) ---\n{page_text}")

                # 如果首页结果不好，尝试旋转 90 度再识别一次
                if i == 0 and (not ocr_result or len(ocr_result) < 3):
                    try:
                        rotated_img = img.rotate(90, expand=True)
                        rotated_result, _ = ocr(rotated_img)
                        if rotated_result and len(rotated_result) > len(ocr_result or []):
                            all_text.pop()  # 移除之前的空结果
                            page_text = "\n".join([line[1] for line in rotated_result])
                            all_text.append(f"--- Page {i+1} (OCR-Rapid-rotated) ---\n{page_text}")
                            result["warnings"].append("Page 1 可能是横向排版，已尝试旋转识别")
                    except Exception:
                        pass

        full_text = "\n\n".join(all_text)
        if len(full_text.strip()) >= 50:
            result["method"] = "rapidocr"
            result["confidence"] = "high" if len(full_text) > 300 else "medium"
            return full_text, result

    except ImportError as e:
        result["warnings"].append(f"RapidOCR 依赖缺失: {e}")
    except Exception as e:
        result["warnings"].append(f"RapidOCR 执行失败: {e}")

    # 方法 2: PyMuPDF (fitz) 作为备选
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            page = doc[i]
            # fitz 可以直接提取文本，也可以渲染为图片
            text = page.get_text()
            if text and len(text.strip()) > 30:
                all_text.append(f"--- Page {i+1} (PyMuPDF-text) ---\n{text}")

        if all_text:
            full_text = "\n\n".join(all_text)
            if len(full_text.strip()) >= 50:
                result["method"] = "pymupdf"
                result["confidence"] = "medium"
                return full_text, result

        # PyMuPDF 渲染 + 内置 OCR
        if hasattr(doc, "get_page_images"):
            for i in range(min(len(doc), 5)):  # 最多处理前5页
                page = doc[i]
                pix = page.get_pixmap(dpi=300)
                import io
                img_data = pix.tobytes("png")
                from PIL import Image as PILImage
                img = PILImage.open(io.BytesIO(img_data))
                
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    ocr = RapidOCR()
                    ocr_result, _ = ocr(img)
                    if ocr_result:
                        page_text = "\n".join([line[1] for line in ocr_result])
                        all_text.append(f"--- Page {i+1} (PyMuPDF+OCR) ---\n{page_text}")
                except Exception:
                    pass

        full_text = "\n\n".join(all_text)
        if len(full_text.strip()) >= 50:
            result["method"] = "pymupdf-ocr"
            result["confidence"] = "low"
            return full_text, result

    except ImportError:
        result["warnings"].append("PyMuPDF 未安装")
    except Exception as e:
        result["warnings"].append(f"PyMuPDF 失败: {e}")

    return "", result


def _post_process(text: str) -> str:
    """
    对提取的文本进行后处理清洗。
    - 清理多余空白
    - 合并断行
    - 清理 OCR 噪声字符
    - 统一标点符号
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # 跳过纯噪声行（只有特殊字符）
        if re.match(r'^[\s\|\\\/\-_=+#*]+$', stripped):
            continue
        
        # 清理常见的 OCR 噪声
        cleaned = stripped
        
        # 合并单词内的断行（如 "INV OICE" → "INVOICE"）
        if cleaned_lines and len(cleaned) > 0 and len(cleaned_lines[-1]) > 0:
            prev = cleaned_lines[-1][-1]
            # 如果上一行以字母结尾且当前行以字母开头（无结尾标点），可能是断行
            if re.match(r'^[a-zA-Z]', cleaned) and re.match(r'[a-zA-Z]$', prev):
                # 检查是否像是句子中间断开
                if not prev in '.:!?' and len(cleaned) > 2:
                    cleaned_lines[-1] += " " + cleaned
                    continue
        
        cleaned_lines.append(cleaned)

    result = "\n".join(cleaned_lines)
    
    # 全局清理：压缩多个连续空白为一个空格
    result = re.sub(r'[ \t]+', ' ', result)
    # 清理多余的换行（保留段落结构）
    result = re.sub(r'\n{3,}', '\n\n', result)
    # 清理页码标记周围的噪音
    result = re.sub(r'-+\s*Page\s*\d+\s*\(.*?\)\s*-+', lambda m: f"\n{m.group().strip()}\n", result, flags=re.IGNORECASE)
    
    return result.strip()


def guess_document_type(text: str) -> str:
    """
    从提取的文本内容中猜测单据类型。
    不依赖文件名，仅通过内容分析。
    
    Returns:
        中文单据类型名称，或空字符串（无法判断时）
    """
    if not text or len(text.strip()) < 20:
        return ""

    t_upper = text.upper()
    t_head = t_upper[:2000]  # 只看前2000字符（通常头部有足够信息）

    scores = {}
    for doc_type, keywords, weight in _DOC_TYPE_PATTERNS:
        score = 0
        for kw in keywords:
            count = t_head.count(kw.upper())
            if count > 0:
                # 关键词出现次数 × 权重
                score += count * weight
            # 特殊加分：完整短语匹配
            if len(kw) > 5 and kw in t_head:
                score += weight * 2
        if score > 0:
            scores[doc_type] = score
    
    if not scores:
        return ""
    
    # 返回得分最高的
    best_type = max(scores.keys(), key=lambda k: scores[k])
    best_score = scores[best_type]
    
    # 只有置信度够高时才返回
    if best_score < 10:
        return ""  # 太不确定了
    
    return best_type
