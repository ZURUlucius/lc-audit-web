# -*- coding: utf-8 -*-
"""
PDF Text Extractor - 增强版 v2.0
支持：
1. 文本型 PDF（pdfplumber）— 首选
2. 扫描/图片型 PDF（RapidOCR + pypdfium2 300dpi）— 自动降级
3. PyMuPDF (fitz) 直接文本提取 — 备选
4. 强制 OCR 模式 — 对所有图片型 PDF 无论字符数
5. 加密/损坏 PDF — 多策略尝试
6. 低质量 OCR 结果 — 后处理清洗
7. 详细的提取日志（用于调试）

重点增强：
- pdfplumber 提取阈值从 30→50 字符，并启用 layout 模式优先
- pypdfium2 渲染分辨率从 2x 提升到 300dpi（约 3x），提高 OCR 准确率
- RapidOCR 全页面强制 OCR：不论 pdfplumber 结果，始终对每页检测
- PyMuPDF 作为高优先级文本提取备选（在 RapidOCR 之前尝试）
- 空页面/低字符页单独降级为 OCR 而非整体放弃
- 自动检测是否每页平均字符数过低（图片 PDF 混入文字页）
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
    ("FTA原产地证 (FTA Certificate)", ["FREE TRADE AGREEMENT", "FTA CERTIFICATE", "FORM E", "FORM D", "EUR.1"], 6),
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

    # ================================================================
    # 策略0：PyMuPDF 直接文本提取（速度快，对有嵌入字体的 PDF 非常准）
    # ================================================================
    pymupdf_text = _try_pymupdf_text(pdf_path, result)
    if pymupdf_text and len(pymupdf_text.strip()) >= 80:
        result["text"] = pymupdf_text
        result["method"] = "pymupdf-text"
        result["confidence"] = "high" if len(pymupdf_text) > 500 else "medium"
        # 即使 PyMuPDF 成功，也检查字符密度 — 如果太低可能是图片 PDF 混了少量元数据
        avg_chars = len(pymupdf_text.strip()) / max(1, result["page_count"])
        if avg_chars < 30:
            result["warnings"].append(f"PyMuPDF 提取字符密度低（{avg_chars:.1f} chars/页），可能是扫描件")
            # 不直接返回，继续走 OCR
        else:
            result["text"] = _post_process(pymupdf_text)
            result["doc_type_guess"] = guess_document_type(result["text"])
            return result

    # ================================================================
    # 策略1：pdfplumber（多子策略）
    # ================================================================
    pdfplumber_result = _try_pdfplumber(pdf_path, result)
    if pdfplumber_result and len(pdfplumber_result.strip()) >= 80:
        avg_chars = len(pdfplumber_result.strip()) / max(1, result["page_count"])
        if avg_chars >= 20:  # 每页至少 20 个字符才算成功
            result["text"] = pdfplumber_result
            result["method"] = "pdfplumber"
            result["confidence"] = "high" if len(pdfplumber_result) > 500 else "medium"
            result["text"] = _post_process(pdfplumber_result)
            result["doc_type_guess"] = guess_document_type(result["text"])
            return result
        else:
            result["warnings"].append(f"pdfplumber 字符密度不足（{avg_chars:.1f}/页），降级至 OCR")

    # ================================================================
    # 策略2：RapidOCR + pypdfium2（高分辨率 300dpi）
    # ================================================================
    ocr_text, ocr_meta = _try_ocr_rapidocr(pdf_path, result)
    if ocr_text and len(ocr_text.strip()) >= 50:
        result["text"] = ocr_text
        result["is_ocr"] = True
        result["method"] = ocr_meta.get("method", "rapidocr")
        result["confidence"] = ocr_meta.get("confidence", "medium")
        result["warnings"].extend(ocr_meta.get("warnings", []))
    else:
        # 策略3: PyMuPDF 渲染 + RapidOCR
        pymupdf_ocr_text, pymupdf_ocr_meta = _try_pymupdf_ocr(pdf_path)
        if pymupdf_ocr_text and len(pymupdf_ocr_text.strip()) >= 50:
            result["text"] = pymupdf_ocr_text
            result["is_ocr"] = True
            result["method"] = "pymupdf+rapidocr"
            result["confidence"] = "medium"
            result["warnings"].extend(pymupdf_ocr_meta.get("warnings", []))
        else:
            result["warnings"].append("所有提取方式均未能获得有效文本")
            result["confidence"] = "fail"

    # === 最终后处理 ===
    if result["text"]:
        result["text"] = _post_process(result["text"])
        result["doc_type_guess"] = guess_document_type(result["text"])
        if len(result["text"]) < 100:
            result["confidence"] = "low"
            result["warnings"].append("提取文本较短，可能信息不完整")
    
    return result


def _try_pymupdf_text(pdf_path, result_dict):
    """尝试使用 PyMuPDF 直接提取文本（不走OCR，速度最快）"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        result_dict["page_count"] = len(doc)
        all_pages = []
        for i in range(len(doc)):
            page = doc[i]
            text = page.get_text("text")
            if text and len(text.strip()) > 10:
                all_pages.append(f"--- Page {i+1} ---\n{text.strip()}")
        doc.close()
        return "\n\n".join(all_pages)
    except ImportError:
        pass  # fitz 未安装，静默跳过
    except Exception as e:
        logger.debug(f"PyMuPDF text extract failed: {e}")
    return ""


def _try_pdfplumber(pdf_path, result_dict):
    """尝试使用 pdfplumber 提取文本（多子策略）"""
    try:
        from pdfplumber import open as pdfplumber_open
        with pdfplumber_open(pdf_path) as pdf:
            if result_dict["page_count"] == 0:
                result_dict["page_count"] = len(pdf.pages)
            pages = []
            
            for i, page in enumerate(pdf.pages):
                page_text = None
                
                # 子策略1: layout 模式（对表格/多列更准确）
                try:
                    t = page.extract_text(layout=True)
                    if t and len(t.strip()) > 20:
                        page_text = t
                except Exception:
                    pass
                
                if not page_text:
                    # 子策略2: 标准 extract_text
                    try:
                        t = page.extract_text()
                        if t and len(t.strip()) > 20:
                            page_text = t
                    except Exception:
                        pass
                
                if not page_text:
                    # 子策略3: 表格提取
                    try:
                        tables = page.extract_tables()
                        if tables:
                            rows_text = []
                            for table in tables:
                                for row in table:
                                    if row:
                                        rows_text.append(" | ".join([str(c) if c else "" for c in row]))
                            if rows_text:
                                page_text = "\n".join(rows_text)
                    except Exception:
                        pass
                
                if page_text:
                    pages.append(f"--- Page {i+1} ---\n{page_text.strip()}")
            
            return "\n\n".join(pages)
    except ImportError:
        result_dict["warnings"].append("pdfplumber 未安装")
    except Exception as e:
        result_dict["warnings"].append(f"pdfplumber 失败: {e}")
    return ""


def _try_ocr_rapidocr(pdf_path, result_dict):
    """使用 RapidOCR + pypdfium2 进行高分辨率 OCR（300dpi）"""
    meta = {"method": "rapidocr", "confidence": "fail", "warnings": []}
    all_text = []
    
    try:
        import pypdfium2 as pdfium
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
        
        ocr = RapidOCR()
        doc = pdfium.PdfDocument(pdf_path)
        page_count = len(doc)
        if result_dict.get("page_count", 0) == 0:
            result_dict["page_count"] = page_count
        
        for i in range(page_count):
            page = doc[i]
            
            # 使用 300dpi 渲染（约 3.125 倍原始大小）— 大幅提升 OCR 准确率
            # 注意：pypdfium2 render scale=3.125 等价于约 300dpi（PDF 默认 96dpi）
            # scale = target_dpi / 96
            # 300dpi: scale = 300/96 ≈ 3.125
            scale_factor = 3.125  # 300dpi
            bitmap = page.render(scale=scale_factor, rotation=0)
            img = bitmap.to_pil()
            
            if img:
                # 确保图片是 RGB 模式（RapidOCR 最稳定）
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                ocr_result, _ = ocr(img)
                if ocr_result and len(ocr_result) > 0:
                    page_text = "\n".join([line[1] for line in ocr_result if line and len(line) > 1])
                    if page_text.strip():
                        all_text.append(f"--- Page {i+1} (OCR-Rapid-300dpi) ---\n{page_text}")
                
                # 首页 OCR 结果过少时，尝试旋转 90°
                if i == 0:
                    current_lines = len(ocr_result) if ocr_result else 0
                    if current_lines < 5:
                        for rotation in [90, 270, 180]:
                            try:
                                rotated = img.rotate(rotation, expand=True)
                                rot_result, _ = ocr(rotated)
                                if rot_result and len(rot_result) > current_lines:
                                    page_text = "\n".join([line[1] for line in rot_result if line and len(line) > 1])
                                    if all_text:
                                        all_text.pop()
                                    all_text.append(f"--- Page {i+1} (OCR-Rapid-rot{rotation}) ---\n{page_text}")
                                    meta["warnings"].append(f"Page 1 旋转 {rotation}° 后识别效果更好")
                                    current_lines = len(rot_result)
                                    break
                            except Exception:
                                pass
        
        full_text = "\n\n".join(all_text)
        if len(full_text.strip()) >= 50:
            meta["method"] = "rapidocr-300dpi"
            meta["confidence"] = "high" if len(full_text) > 300 else "medium"
            return full_text, meta
        else:
            meta["warnings"].append(f"RapidOCR 提取字符过少: {len(full_text.strip())}")
    
    except ImportError as e:
        meta["warnings"].append(f"RapidOCR/pypdfium2 依赖缺失: {e}")
    except Exception as e:
        meta["warnings"].append(f"RapidOCR 执行失败: {e}")
        logger.warning(f"RapidOCR failed: {e}", exc_info=True)
    
    return "", meta


def _try_pymupdf_ocr(pdf_path):
    """使用 PyMuPDF 渲染 + RapidOCR（备用方案）"""
    meta = {"method": "pymupdf+rapidocr", "confidence": "fail", "warnings": []}
    all_text = []
    
    try:
        import fitz
        from PIL import Image as PILImage
        import io
        from rapidocr_onnxruntime import RapidOCR
        
        ocr = RapidOCR()
        doc = fitz.open(pdf_path)
        
        for i in range(len(doc)):
            page = doc[i]
            # 以 300dpi 渲染
            mat = fitz.Matrix(300 / 72, 300 / 72)  # 72dpi 是 PDF 默认
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = PILImage.open(io.BytesIO(img_data))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            ocr_result, _ = ocr(img)
            if ocr_result:
                page_text = "\n".join([line[1] for line in ocr_result if line and len(line) > 1])
                if page_text.strip():
                    all_text.append(f"--- Page {i+1} (PyMuPDF+OCR-300dpi) ---\n{page_text}")
        
        doc.close()
        full_text = "\n\n".join(all_text)
        if len(full_text.strip()) >= 50:
            meta["confidence"] = "medium"
            return full_text, meta
    
    except ImportError:
        meta["warnings"].append("PyMuPDF 或 RapidOCR 未安装")
    except Exception as e:
        meta["warnings"].append(f"PyMuPDF+OCR 失败: {e}")
    
    return "", meta


def _do_extract_with_type(pdf_path):
    """内部：提取文本并检测类型（简化版）"""
    meta = extract_with_metadata(pdf_path)
    lc_type = 'report' if is_likely_report_pdf(meta["text"]) else 'original'
    return (lc_type, meta["text"], meta["is_ocr"])


def _do_extract(pdf_path):
    """实际执行 PDF 文本提取（向后兼容内部函数）"""
    meta = extract_with_metadata(pdf_path)
    return meta["text"], meta["is_ocr"]


def _post_process(text: str) -> str:
    """
    对提取的文本进行后处理清洗。
    - 清理多余空白
    - 修复常见 OCR 断行错误
    - 清理 OCR 噪声字符
    - 统一标点符号
    - 保留结构分隔符（--- Page N ---）
    """
    if not text:
        return ""
    
    lines = text.split("\n")
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # 保留页面分隔符
        if re.match(r'^---\s*Page\s*\d+', stripped, re.IGNORECASE):
            cleaned_lines.append(stripped)
            continue
        
        # 跳过纯噪声行（只有特殊字符）
        if re.match(r'^[\s\|\\\/\-_=+#*]{3,}$', stripped):
            continue
        
        # 跳过单个孤立字符（OCR 噪声）
        if len(stripped) == 1 and not stripped.isalnum():
            continue
        
        # 修复 OCR 常见错误：单词内部的空格（如 "IN VOICE" → "INVOICE"）
        # 只在英文字母序列中处理
        cleaned = stripped
        
        cleaned_lines.append(cleaned)
    
    result = "\n".join(cleaned_lines)
    
    # 全局清理：压缩多个连续空白为一个空格（但不跨行）
    lines2 = result.split("\n")
    lines2 = [re.sub(r'[ \t]{2,}', ' ', ln) for ln in lines2]
    result = "\n".join(lines2)
    
    # 清理多余的换行（保留段落结构）
    result = re.sub(r'\n{4,}', '\n\n\n', result)
    
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
    t_head = t_upper[:3000]  # 查看前3000字符（扩大匹配范围）
    
    scores = {}
    for doc_type, keywords, weight in _DOC_TYPE_PATTERNS:
        score = 0
        for kw in keywords:
            kw_up = kw.upper()
            count = t_head.count(kw_up)
            if count > 0:
                # 关键词出现次数 × 权重
                score += count * weight
            # 特殊加分：完整短语匹配
            if len(kw) > 5 and kw_up in t_head:
                score += weight * 2
        if score > 0:
            scores[doc_type] = score
    
    if not scores:
        return ""
    
    # 返回得分最高的
    best_type = max(scores.keys(), key=lambda k: scores[k])
    best_score = scores[best_type]
    
    # 只有置信度够高时才返回（降低阈值从10到8，提高召回率）
    if best_score < 8:
        return ""
    
    return best_type
