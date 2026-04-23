# -*- coding: utf-8 -*-
"""
PDF Text Extractor - supports text-based PDFs and OCR for scanned documents.
增强版：自动识别 LC 原始信用证 vs 已生成的报告 PDF
"""

import os
import re
import tempfile


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


def is_likely_report_pdf(text: str) -> bool:
    """
    判断提取的文本是否来自已生成的审核报告（而非原始信用证 MT700）。
    
    报告 PDF 特征：
    - 包含 "信用证条款审核报告" / "LC Audit" 等标题
    - 包含 HTML 标签残留 (<b>, </b>)
    - 包含 "本报告由...系统自动生成"
    - 缺少 SWIFT MT700 字段格式 (:20:, :40A:, :32B: 等)
    
    Returns:
        True = 这是一个已生成的报告 PDF（不是原始 LC）
        False = 可能是原始信用证
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


def _do_extract_with_type(pdf_path):
    """内部：提取文本并检测类型"""
    text, is_ocr = _do_extract(pdf_path)
    if not text or len(text.strip()) < 50:
        return ('unknown', text, is_ocr)
    lc_type = 'report' if is_likely_report_pdf(text) else 'original'
    return (lc_type, text, is_ocr)


def _do_extract(pdf_path):
    """实际执行 PDF 文本提取"""
    # Try pdfplumber first
    try:
        from pdfplumber import open as pdfplumber_open

        pages = []
        with pdfplumber_open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages.append(f"--- Page {i+1} ---\n{text}")
        result = "\n\n".join(pages)

        # If we got enough text, return it
        if len(result.strip()) >= 50:
            return result, False
    except ImportError:
        result = ""
    except Exception:
        result = ""

    # Fall back to OCR if pdfplumber didn't yield enough text
    if len(result.strip()) < 50:
        try:
            import pypdfium2 as pdfium
            from PIL import Image
            from rapidocr_onnxruntime import RapidOCR

            ocr = RapidOCR()
            all_text = []

            doc = pdfium.PdfDocument(pdf_path)
            for i in range(len(doc)):
                page = doc[i]
                bitmap = page.render(scale=2)  # 2x for better OCR accuracy
                img = bitmap.to_pil()
                ocr_result, _ = ocr(img)
                if ocr_result:
                    page_text = "\n".join([line[1] for line in ocr_result])
                    all_text.append(f"--- Page {i+1} (OCR) ---\n{page_text}")

            result = "\n\n".join(all_text)
            if result.strip():
                return result, True
        except ImportError:
            pass
        except Exception as e:
            print(f"OCR error: {e}")

    # Last resort: return whatever we have
    return result or "", False
