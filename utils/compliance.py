# -*- coding: utf-8 -*-
"""
交单合规检查模块 — 检查交单文件与信用证条款的符合情况
全中文输出版本
"""

import re
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date


# ──────────────────── 单据类型识别 ────────────────────

# ── 内容驱动的单据类型识别规则（不依赖文件名）──
# 每条规则：(type_name, [(关键词, 加权分), ...], 最低阈值)
_CONTENT_TYPE_RULES = [
    ("海运提单 (Bill of Lading)", [
        ("BILL OF LADING", 10), ("B/L", 8), ("OCEAN B/L", 12),
        ("PORT OF LOADING", 8), ("PORT OF DISCHARGE", 8),
        ("SHIPPER", 5), ("CONSIGNEE", 5),
        ("VESSEL", 4), ("CONTAINER NO", 7), ("SEAL NO", 6),
        ("FREIGHT PREPAID", 6), ("FREIGHT COLLECT", 6),
        ("MASTER B/L", 10), ("HOUSE B/L", 10), ("FORWARDER", 3),
        ("TO ORDER", 3), ("ORIGINAL", 2),
    ], 15),

    ("航空运单 (Airway Bill)", [
        ("AIRWAY BILL", 10), ("AIRWAYBILL", 10), ("AWB", 9),
        ("AIR CARGO", 6), ("FLIGHT NO", 8),
        ("AIRPORT OF DEPARTURE", 8), ("AIRPORT OF DESTINATION", 8),
        ("CARRIER'S AGENT", 5), ("SHIPPER'S DECLARATION", 4),
    ], 12),

    ("商业发票 (Commercial Invoice)", [
        ("COMMERCIAL INVOICE", 15), ("INVOICE NO", 6), ("INVOICE NUMBER", 6),
        ("INVOICE DATE", 5), ("TOTAL AMOUNT", 5),
        ("UNIT PRICE", 5), ("QUANTITY", 3), ("DESCRIPTION OF GOODS", 4),
        ("SUB TOTAL", 4), ("GRAND TOTAL", 5),
        ("PRICE TERM", 4), ("FOB", 2), ("CIF", 2),
    ], 18),

    ("形式发票 (Proforma Invoice)", [
        ("PROFORMA INVOICE", 15), ("PROFORMA", 10),
        ("PRO-FORMA", 12),
    ], 12),

    ("装箱单 (Packing List)", [
        ("PACKING LIST", 15), ("PACKING WEIGHT", 10),
        ("GROSS WEIGHT", 6), ("NET WEIGHT", 6),
        ("MEASUREMENT", 6), ("CBM", 5), ("M³", 4),
        ("NO. OF PACKAGES", 7), ("NO. OF PACKS", 7),
        ("CARTONS", 4), ("PALLET", 3), ("PACKAGES", 3),
        ("N.W.", 3), ("G.W.", 3),
    ], 14),

    ("重量单 (Weight List)", [
        ("WEIGHT LIST", 12), ("WEIGHT MEMO", 12),
        ("WEIGHT NOTE", 10), ("CERTIFICATE OF WEIGHT", 12),
        ("TARE WEIGHT", 5),
    ], 10),

    ("原产地证 (Certificate of Origin)", [
        ("CERTIFICATE OF ORIGIN", 15), ("CERTIFIED TRUE COPY", 6),
        ("COUNTRY OF ORIGIN", 8), ("ORIGIN OF GOODS", 6),
        ("CERTIFY THAT", 4), ("MANUFACTURED IN", 5),
        ("FORM A", 10), ("GSP FORM A", 12), ("FORM B", 8),
        ("CHAMBER OF COMMERCE", 5),
    ], 14),

    ("保险单 (Insurance Policy/Certificate)", [
        ("INSURANCE POLICY", 15), ("INSURANCE CERTIFICATE", 13),
        ("OPEN POLICY", 10), ("CERTIFICATE OF INSURANCE", 12),
        ("MODE AND CONVEYANCE", 5), ("INSURED VALUE", 5),
        ("INSURER", 3), ("PREMIUM", 3),
        ("ALL RISKS", 5), ("ICC(A)", 4), ("ICC(B)", 4), ("ICC(C)", 4),
    ], 14),

    ("汇票 (Draft/Bill of Exchange)", [
        ("EXCHANGE FOR", 15), ("DRAFT", 10),
        ("BILL OF EXCHANGE", 12), ("AT SIGHT", 8),
        ("DAYS AFTER SIGHT", 10), ("PAY TO THE ORDER OF", 10),
        ("TENOR", 5), ("DATE OF ISSUE", 4),
        ("FIRST EXCHANGE", 6), ("SECOND EXCHANGE", 6),
        ("BEARING DATE", 4),
    ], 16),

    ("检验证书 (Inspection Certificate)", [
        ("INSPECTION CERTIFICATE", 12), ("INSPECTION REPORT", 10),
        ("QUALITY INSPECTION", 8), ("INSPECTION AND TESTING", 8),
        ("INSPECTED BY", 5), ("RESULT OF INSPECTION", 5),
        ("SGS", 6), ("INTERTEK", 5), ("BV", 4),
    ], 12),

    ("品质证明书 (Quality Certificate)", [
        ("QUALITY CERTIFICATE", 12), ("CERTIFICATE OF QUALITY", 11),
        ("QUALITY REPORT", 8), ("QUALITY ANALYSIS", 6),
        ("SPECIFICATION", 4),
    ], 10),

    ("数量证明书 (Quantity Certificate)", [
        ("QUANTITY CERTIFICATE", 12), ("CERTIFICATE OF QUANTITY", 11),
        ("QUANTITY VERIFICATION", 8),
    ], 8),

    ("受益人证明 (Beneficiary's Certificate)", [
        ("BENEFICIARY'S CERTIFICATE", 15), ("BENEFICIARY CERTIFICATE", 12),
        ("BENEFICIARY'S DECLARATION", 12), ("BENEFICIARY DECLARATION", 10),
        ("WE HEREBY CERTIFY", 5), ("WE HEREBY DECLARE", 5),
    ], 10),

    ("装运通知 (Shipping Advice)", [
        ("SHIPPING ADVICE", 12), ("ADVICE OF SHIPMENT", 10),
        ("SHIPPING NOTICE", 8), ("NOTICE OF SHIPMENT", 8),
        ("ETD", 4), ("ETA", 4), ("VESSEL NAME", 3),
    ], 10),

    ("电放保函 (Telex Release)", [
        ("TELEX RELEASE", 15), ("LETTER OF INDEMNITY", 10),
        ("LOI TELEX RELEASE", 12), ("RELEASE ORDER", 5),
    ], 8),
]


def identify_document_type(filename, text=""):
    """
    根据文件名和文本内容识别单据类型（中文）。
    
    增强版：优先使用文件名快速匹配，如果文件名无法识别，
    则通过文本内容进行深度分析（内容驱动识别）。
    """
    name = filename.upper()
    t = text.upper() if text else ""

    # ── 第一层：文件名快速匹配（保持原有逻辑）──

    # 提单类
    if any(kw in name for kw in ['BILL OF LADING', 'B/L', 'BL', 'AWB', 'AIRWAY']):
        if 'OCEAN' in name or 'SEA' in name or 'MARINE' in name:
            return '海运提单 (Bill of Lading)'
        elif 'AIR' in name or 'AWB' in name:
            return '航空运单 (Airway Bill)'
        elif 'MULTIMODAL' in name or 'COMBINED' in name:
            return '多式联运提单'
        else:
            return '提单 (Bill of Lading)'

    # 发票类
    if any(kw in name for kw in ['COMMERCIAL', 'INVOICE', 'CI']):
        if 'PROFORMA' in name:
            return '形式发票'
        elif 'CUSTOMS' in name:
            return '海关发票'
        else:
            return '商业发票'

    # 装箱单/重量单
    if any(kw in name for kw in ['PACKING LIST', 'PL', 'WEIGHT LIST', 'WL']):
        return '装箱单 / 重量单'

    # 汇票
    if any(kw in name for kw in ['DRAFT', 'DRAFTS', 'EXCHANGE', 'HUIPIAO']):
        return '汇票'

    # 原产地证
    if any(kw in name for kw in ['ORIGIN', 'CO', 'FORM A', 'GSP']):
        return '原产地证'

    # 保险单
    if any(kw in name for kw in ['INSURANCE', 'POLICY', 'IP']):
        return '保险单/凭证'

    # 检验证
    if any(kw in name for kw in ['INSPECTION', 'QC', 'QUALITY']):
        return '检验证书'

    # 证明/声明类 — 文件名部分匹配时也尝试用内容确认
    if any(kw in name for kw in ['CERTIFICATE', 'CERT', 'DECLARATION']):
        if 'ORIGIN' in t or 'ORIGIN' in name:
            return '原产地证'
        if 'INSPECTION' in t or 'INSPECTION' in name:
            return '检验证书'
        if 'WEIGHT' in t or 'WEIGHT' in name:
            return '重量证明书'
        if 'QUALITY' in t or 'QUALITY' in name:
            return '品质证明书'
        if 'BENEFICIARY' in t or 'BENEFICIARY' in name:
            return '受益人证明/声明'
        # 文件名有 cert 但无法确定具体类型，进入内容驱动层
        pass

    # ── 第二层：内容驱动深度识别（当文件名无信息时）──
    if text and len(text.strip()) >= 20:
        content_result = _identify_by_content(t)
        if content_result:
            return content_result

    # ── 最终兜底：返回"其他单据"而非"未知单据" ──
    return "其他单据"


def _identify_by_content(t: str) -> str:
    """
    纯通过文本内容分析来识别单据类型。
    
    Args:
        t: 文本内容（已转大写）
        
    Returns:
        中文单据类型名称，或 None（无法判断）
    """
    best_match = None
    best_score = 0
    
    # 只看前 3000 字符（通常头部信息足够判断）
    sample = t[:3000]
    
    for type_name, keywords, threshold in _CONTENT_TYPE_RULES:
        score = 0
        matched_keywords = []
        
        for keyword, weight in keywords:
            count = sample.count(keyword)
            if count > 0:
                score += count * weight
                matched_keywords.append(keyword)
        
        if score > best_score and score >= threshold:
            best_score = score
            best_match = type_name
    
    return best_match


# ──────────────────── 单据内容提取 ────────────────────

def extract_bl_info(text):
    """
    从提单文本中提取关键字段。
    返回包含各字段的字典。
    """
    info = {
        "bl_number": "",
        "shipper": "",
        "consignee": "",
        "notify_party": "",
        "vessel_name": "",
        "port_of_loading": "",
        "port_of_discharge": "",
        "shipment_date": "",
        "freight": "",
        "container_numbers": [],
        "marks": "",
    }

    t = text.upper()

    # 提单号
    patterns_bl_no = [
        r'B/?L\s*(?:NO\.?|NUMBER|#)\s*:?\s*([\w\-/]+)',
        r'(?:NO\.?|NUMBER)\s*:?\s*([\w\-/]{6,})\s*(?:\n|$)',
    ]
    for pat in patterns_bl_no:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            info["bl_number"] = m.group(1).strip()
            break

    # 托运人
    shipper_patterns = [
        r'(?:SHIPPER|SHIPPERS?|EXPORTER)\s*[\:：]?\s*\n?\s*(.+?)(?:\n\s*(?:CONSIGNEE|CONSIGNOR|$))',
        r'^1\s*(.+?)\s*\n\s*2\s',
    ]
    for pat in shipper_patterns:
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            info["shipper"] = clean_extract(m.group(1))
            break

    # 收货人
    consignee_patterns = [
        r'(?:CONSIGNEE|TO\s+ORDER|TO\s+THE\s+ORDER)\s*[\:：]?\s*\n?\s*(.+?)(?:\n\s*(?:NOTIFY|PARTY|$))',
        r'^2\s*(.+?)\s*\n\s*3\s',
    ]
    for pat in consignee_patterns:
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            info["consignee"] = clean_extract(m.group(1))
            break

    # 通知方
    notify_m = re.search(
        r'(?:NOTIFY(?:\s+(?:PARTY|ADDRESS))?|(?:NOTIFYING|NOTIFICATION).*?(?:PARTY|ADDRESS)?)[\s:\-]*\n?\s*(.+?)(?=\n\s*\n|\n\s*[0-9]|\Z)',
        text, re.DOTALL | re.IGNORECASE
    )
    if notify_m:
        info["notify_party"] = clean_extract(notify_m.group(1))

    # 船名
    vessel_patterns = [
        r'(?:VESSEL|VESSELS?|STEAMER|S/S|SS|M/V|MV)\s*[\:：]?\s*([A-Z][\w\s]{2,40}?)(?:\n|$)',
        r'OCEAN\s+VESSEL\s*[\:：]?\s*([A-Z][\w\s]{2,30}?)',
        r'(?:SAILING|VOYAGE)\s*(?:ON\s+ABOUT|ON\s+OR\s+ABOUT)?\s*[:\s]*([A-Z][\w\s]{2,30})',
    ]
    for pat in vessel_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            info["vessel_name"] = m.group(1).strip()
            break

    # 装货港
    load_m = re.search(
        r'(?:PORT\s+OF\s+LOADING|LOAD\s+PORT|RECEIVED|LOADED|FROM)\s*[\:：]?\s*(.+?)(?:\n|$)',
        text, re.IGNORECASE
    )
    if load_m:
        info["port_of_loading"] = clean_extract(load_m.group(1))

    # 卸货港
    disc_m = re.search(
        r'(?:PORT\s+OF\s+DISCHARGE|DISCHARGE\s+PORT|FOR\s+TRANSPORTATION\s+TO|DELIVERY)\s*[\:：]?\s*(.+?)(?:\n|$)',
        text, re.IGNORECASE
    )
    if disc_m:
        info["port_of_discharge"] = clean_extract(disc_m.group(1))

    # 装船日期
    date_patterns = [
        r'(?:ON\s+BOARD\s+DATE|DATE|SHIPPED\s+ON\s+BOARD|SHIPPING\s+DATE|B/L\s+DATE)[\s:\-]*\n?\s*(.+?)(?:\n|$)',
        r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{2,4}[\/\-]\d{1,2}[\/\-]\d{1,2})(?:\s|$)',
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            info["shipment_date"] = m.group(1).strip()
            break

    # 运费
    freight_m = re.search(r'(?:FREIGHT|CARRIAGE|CARGO)\s*(?:PREPAID|COLLECT|PAYABLE)', text, re.IGNORECASE)
    if freight_m:
        info["freight"] = freight_m.group(0)

    # 集装箱号
    containers = re.findall(r'\b([A-Z]{4}\d{7})\b', text)
    info["container_numbers"] = list(set(containers))

    # 唛头
    marks_m = re.search(
        r'(?:MARKS\s*&\s*NOS?|MARKINGS?|SHIPPING\s+MARKS?)[\s:\-]*\n?\s*(.+?)(?=\n\s*\n|\n\s*[A-Z]{2,}\s*$|\Z)',
        text, re.IGNORECASE | re.DOTALL
    )
    if marks_m:
        info["marks"] = clean_extract(marks_m.group(1))

    return info


def extract_invoice_info(text):
    """从发票文本中提取关键字段。"""
    info = {
        "invoice_number": "",
        "seller": "",
        "buyer": "",
        "total_amount": "",
        "currency": "",
        "items": [],
        "date": "",
    }

    # 发票号
    inv_m = re.search(
        r'(?:INVOICE\s*(?:NO\.?|NUMBER|#)|COMMERCIAL\s+INVOICE\s*NO\.?)[\s:\-]*\n?\s*([\w\-/]+)',
        text, re.IGNORECASE
    )
    if inv_m:
        info["invoice_number"] = inv_m.group(1).strip()

    # 卖方/受益人
    seller_m = re.search(
        r'(?:SELLER|VENDOR|SUPPLIER|EXPORTER|BENEFICIARY)[\s:\-]*\n?\s*(.+?)(?:\n\s*(?:BUYER|CUSTOMER|IMPORTER|$))',
        text, re.DOTALL | re.IGNORECASE
    )
    if seller_m:
        info["seller"] = clean_extract(seller_m.group(1))

    # 买方/申请人
    buyer_m = re.search(
        r'(?:BUYER|CUSTOMER|IMPORTER|APPLICANT|CONSIGNEE)[\s:\-]*\n?\s*(.+?)(?:\n\s*$|\n\s*[A-Z])',
        text, re.DOTALL | re.IGNORECASE
    )
    if buyer_m:
        info["buyer"] = clean_extract(buyer_m.group(1))

    # 总金额
    amt_m = re.search(
        r'(?:TOTAL\s+(?:AMOUNT|VALUE|SUM)|GRAND\s+TOTAL|TOTAL\s*DUE)[\s:\-]*(?:[^\d\n]*)([\d,]+\.?\d*)\s*([A-Z]{3}|USD|EUR|GBP|RMB)',
        text, re.IGNORECASE
    )
    if amt_m:
        info["total_amount"] = amt_m.group(1).replace(",", "")
        info["currency"] = amt_m.group(2)

    # 日期
    dt_m = re.search(
        r'DATE[\s:\-]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{2,4}[\/\-]\d{1,2}[\/\-]\d{1,2}|\w+\s+\d{1,2},?\s+\d{4})',
        text, re.IGNORECASE
    )
    if dt_m:
        info["date"] = dt_m.group(1)

    return info


def extract_packing_list_info(text):
    """从装箱单中提取关键字段。"""
    info = {
        "total_packages": "",
        "package_type": "",
        "gross_weight": "",
        "net_weight": "",
        "measurement": "",
        "container_info": "",
    }

    pkg_m = re.search(r'TOTAL\s*(?:PACKAGES?|PACKAGES?\s*(?:NO\.?)?|CARTONS?|PALLETS?)[\s:]*(\d+)', text, re.IGNORECASE)
    if pkg_m:
        info["total_packages"] = pkg_m.group(1)

    gw_m = re.search(r'(?:GROSS\s*WEIGHT|G\.W\.)[\s:]*(\d+\.?\d*)\s*(KGS?|KG|TONS?)', text, re.IGNORECASE)
    if gw_m:
        info["gross_weight"] = f"{gw_m.group(1)} {gw_m.group(2)}"

    nw_m = re.search(r'(?:NET\s*WEIGHT|N\.W\.)[\s:]*(\d+\.?\d*)\s*(KGS?|KG|TONS?)', text, re.IGNORECASE)
    if nw_m:
        info["net_weight"] = f"{nw_m.group(1)} {nw_m.group(2)}"

    meas_m = re.search(r'(?:MEASUREMENT?|MEAS\.?|CBM|VOLUME)[\s:]*(\d+\.?\d*)\s*(CBM|M3|CU\.?M)', text, re.IGNORECASE)
    if meas_m:
        info["measurement"] = f"{meas_m.group(1)} {meas_m.group(2)}"

    return info


def extract_draft_info(text):
    """从汇票文本中提取关键字段。"""
    info = {
        "amount": "",
        "currency": "",
        "drawee": "",
        "drawer": "",
        "date": "",
        "tenor": "",
    }

    amt_m = re.search(r'SUM\s*OF\s*([A-Z]+)\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
    if amt_m:
        info["currency"] = amt_m.group(1)
        info["amount"] = amt_m.group(2).replace(",", "")

    drawee_m = re.search(r'TO\s*:?[\s\n]*(.+?)(?:\n|$)', text, re.DOTALL | re.IGNORECASE)
    if drawee_m:
        info["drawee"] = clean_extract(drawee_m.group(1))

    tenor_m = re.search(r'(AT\s+\d+\s*DAY[S]?\s*SIGHT|AT\s+SIGHT)', text, re.IGNORECASE)
    if tenor_m:
        info["tenor"] = tenor_m.group(1)

    return info


def clean_extract(s):
    """清理提取的文本。"""
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'\n.*$', '', s)
    return s.strip()


# ──────────────────── 合规检查规则引擎 ────────────────────

def check_compliance(lc_text, lc_analysis, doc_results, doc_labels=None):
    """
    根据信用证条款分析结果，逐一核对每份提交的单据。
    
    参数:
        lc_text: LC 原始文本
        lcanalyze_lc(lc_text) 的返回结果
        doc_results: 文件处理结果列表，每个元素为 {"filename", "type", "text", "is_ocr"}
        doc_labels: 文件标签列表（可选）
    
    返回:
        每份单据的详细检查结果列表
    """
    checks = []
    fields = lc_analysis.get("raw_fields", {})
    expiry_date_str = lc_analysis.get("expiry_date", "")
    latest_ship = lc_analysis.get("latest_shipment", "")
    pres_period_raw = lc_analysis.get("presentation_period", "")

    # 解析交单期天数
    pres_days = 21  # 默认
    days_match = re.search(r'(\d+)\s*DAY', pres_period_raw.upper())
    if days_match:
        pres_days = int(days_match.group(1))

    # 遍历每份单据进行检查
    for doc in doc_results:
        filename = doc["filename"]
        doctype = identify_document_type(filename, doc.get("text", ""))
        text = doc.get("text", "")
        is_ocr = doc.get("is_ocr", False)

        doc_check = {
            "filename": filename,
            "doctype": doctype,
            "is_ocr": is_ocr,
            "items": [],       # 检查项列表
            "summary": "",     # 摘要结论
            "pass_count": 0,
            "warn_count": 0,
            "fail_count": 0,
        }

        # ── 通用检查（所有单据） ──

        # OCR 准确性警告
        if is_ocr:
            doc_check["items"].append({
                "check": "文件可读性",
                "status": "WARN",
                "detail": "该文件为扫描件，通过 OCR 识别，可能存在个别字符识别不准确的情况，请与原件核对。",
                "suggestion": "建议人工复核关键信息（金额、日期、名称拼写）是否正确。",
            })
            doc_check["warn_count"] += 1

        # ── 基本信息存在性 + 智能重试 ──
        if not text or len(text.strip()) < 20:
            # 尝试从 pdf_extractor 获取更详细的元数据
            # （app.py 可能只传了基础 extract_text 结果，这里做二次尝试）
            doc_path = doc.get("path", "")
            
            # 如果有文件路径，且文本太短，记录更详细的失败原因
            fail_detail = "无法从文件中提取有效文本内容，或文本过短"
            fail_suggestion = "确认文件未加密、非图片格式，或尝试重新上传清晰版 PDF。如为扫描件，系统会自动启用 OCR 识别。"
            
            # 尝试根据 filename 猜测类型（即使没有文本）
            guessed_type = _identify_by_content((filename + " " + (text or "")).upper())
            doctype_for_display = guessed_type or doctype
            
            doc_check["items"].append({
                "check": "文本提取",
                "status": "FAIL",
                "detail": f"{fail_detail}（当前文本长度: {len(text.strip() if text else '')} 字符）。",
                "suggestion": fail_suggestion,
            })
            doc_check["fail_count"] += 1
        else:
            # 文本正常，用内容驱动的方式重新确认单据类型
            content_guess = _identify_by_content(text.upper())
            if content_guess and doctype == "其他单据":
                # 文件名没识别出来但内容识别出来了 → 更新类型
                doctype = content_guess
                doc_check["doctype"] = doctype

        # ── 按单据类型的专项检查 ──

        bl_keywords = ['提单', 'BILL OF LADING', 'B/L', 'B/L']
        ci_keywords = ['发票', 'INVOICE', 'COMMERCIAL']
        pl_keywords = ['装箱', 'PACKING LIST', 'WEIGHT']
        draft_keywords = ['汇票', 'DRAFT', 'EXCHANGE']

        if any(kw in doctype.upper() for kw in bl_keywords):
            _check_bl(doc_check, text, fields, lc_analysis)
        elif any(kw in doctype.upper() for kw in ci_keywords):
            _check_ci(doc_check, text, fields, lc_analysis)
        elif any(kw in doctype.upper() for kw in pl_keywords):
            _check_pl(doc_check, text, fields, lc_analysis)
        elif any(kw in doctype.upper() for kw in draft_keywords):
            _check_draft(doc_check, text, fields, lc_analysis)
        else:
            # 通用单据检查
            _check_generic(doc_check, text, fields, lc_analysis)

        # ── 生成摘要 ──
        total = doc_check["pass_count"] + doc_check["warn_count"] + doc_check["fail_count"]
        if doc_check["fail_count"] > 0:
            doc_check["summary"] = f"❌ 存在 {doc_check['fail_count']} 项不符点"
        elif doc_check["warn_count"] > 0:
            doc_check["summary"] = f"⚠️ 通过但有 {doc_check['warn_count']} 项需关注"
        else:
            doc_check["summary"] = f"✅ 全部 {doc_check['pass_count']} 项检查通过"

        checks.append(doc_check)

    # ── 整体时间节点交叉检查 ──
    time_checks = _check_time_nodes(doc_results, latest_ship, expiry_date_str, pres_days)
    if time_checks:
        checks.append({
            "filename": "[系统交叉核对]",
            "doctype": "时间节点综合审核",
            "is_ocr": False,
            "items": time_checks,
            "summary": "见各项检查结果" if time_checks else "时间节点正常",
            "pass_count": sum(1 for i in time_checks if i["status"] == "PASS"),
            "warn_count": sum(1 for i in time_checks if i["status"] == "WARN"),
            "fail_count": sum(1 for i in time_checks if i["status"] == "FAIL"),
        })

    return checks


def _check_bl(check_obj, text, fields, lc_analysis):
    """检查提单与 LC 条款的一致性。"""
    bl_info = extract_bl_info(text)
    applicant = lc_analysis.get("applicant", "").upper()
    beneficiary = lc_analysis.get("beneficiary", "").upper()
    port_load_lc = fields.get("44E", "").upper()
    port_disc_lc = fields.get("44F", "").upper()
    freight_required = ""
    notify_lc = ""

    # 从 46A 中获取提单要求
    docs_46a = fields.get("46A", "")
    for line in docs_46a.split("\n"):
        ul = line.upper()
        if "B/L" in ul or "BILL OF LADING" in ul:
            if "FREIGHT PREPAID" in ul:
                freight_required = "PREPAID"
            elif "FREIGHT COLLECT" in ul:
                freight_required = "COLLECT"
            if "NOTIFY" in ul:
                notify_m = re.search(r'NOTIF[Y]?.*?(.+?)(?:MARKED|FULL|$)', ul, re.DOTALL)
                if notify_m:
                    notify_lc = notify_m.group(1).strip().upper()

    # 1. 收货人是否符合要求
    order_kw = ["TO ORDER", "OF ORDER", "TO THE ORDER", "MADE OUT TO ORDER"]
    consignee_upper = bl_info.get("consignee", "").upper()
    has_order = any(kw in consignee_upper for kw in order_kw)

    if has_order:
        check_obj["items"].append({
            "check": "收货人抬头 (Consignee)",
            "status": "PASS",
            "detail": f"提单抬头为 '{bl_info['consignee']}'，符合指示性抬头的标准做法。",
            "suggestion": None,
        })
        check_obj["pass_count"] += 1
    elif consignee_upper and applicant and applicant in consignee_upper:
        check_obj["items"].append({
            "check": "收货人抬头 (Consignee)",
            "status": "WARN",
            "detail": f"收货人为 '{bl_info.get("consignee","")}，直接开给申请人。在某些情况下这可能不符合信用证要求。",
            "suggestion": "如 LC 要求 'TO ORDER OF XXX BANK' 或 'TO ORDER'，则此处需要修改。",
        })
        check_obj["warn_count"] += 1
    else:
        check_obj["items"].append({
            "check": "收货人抬头 (Consignee)",
            "status": "PASS" if not consignee_upper else "WARN",
            "detail": f"收货人信息: {bl_info['consignee'] or '(未提取到)'}",
            "suggestion": "请人工核对 LC 对提单收货人的具体要求。" if not consignee_upper else None,
        })
        if consignee_upper:
            check_obj["warn_count"] += 1
        else:
            check_obj["pass_count"] += 1

    # 2. 通知方是否匹配
    if notify_lc and bl_info.get("notify_party"):
        if notify_lc.replace(" ", "") in bl_info["notify_party"].upper().replace(" ", "") \
           or bl_info["notify_party"].upper().replace(" ", "") in notify_lc.replace(" ", ""):
            check_obj["items"].append({
                "check": "通知方 (Notify Party)",
                "status": "PASS",
                "detail": f"通知方 '{bl_info['notify_party'][:50]}...' 与 LC 要求一致。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "通知方 (Notify Party)",
                "status": "FAIL",
                "detail": f"通知方 '{(bl_info['notify_party'] or '')[:50]}' 与 LC 要求的 '{notify_lc[:50]}' 不符。",
                "suggestion": "修改提单通知方以匹配信用证要求。",
            })
            check_obj["fail_count"] += 1

    # 3. 装货港
    if port_load_lc and bl_info.get("port_of_loading"):
        if _port_match(port_load_lc, bl_info["port_of_loading"]):
            check_obj["items"].append({
                "check": "装货港 (Port of Loading)",
                "status": "PASS",
                "detail": f"装货港 '{bl_info['port_of_loading']}' 与 LC 要求一致。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "装货港 (Port of Loading)",
                "status": "FAIL",
                "detail": f"实际装货港 '{bl_info['port_of_loading']}' 与 LC 要求 '{port_load_lc}' 不同。",
                "suggestion": "确保装货港与信用证条款一致。",
            })
            check_obj["fail_count"] += 1

    # 4. 卸货港
    if port_disc_lc and bl_info.get("port_of_discharge"):
        if _port_match(port_disc_lc, bl_info["port_of_discharge"]) or "COVERING" in port_disc_lc:
            check_obj["items"].append({
                "check": "卸货港 (Port of Discharge)",
                "status": "PASS",
                "detail": f"卸货港 '{bl_info['port_of_discharge']}' 符合 LC 要求范围。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "卸货港 (Port of Discharge)",
                "status": "FAIL",
                "detail": f"实际卸货港 '{bl_info['port_of_discharge']}' 与 LC 要求 '{port_disc_lc}' 不同。",
                "suggestion": "确认目的港是否正确。",
            })
            check_obj["fail_count"] += 1

    # 5. 运费标记
    if freight_required and bl_info.get("freight"):
        if freight_required.upper() in bl_info["freight"].upper():
            check_obj["items"].append({
                "check": "运费支付方式 (Freight)",
                "status": "PASS",
                "detail": f"运费标记为 '{bl_info['freight']}'，符合 LC 要求。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "运费支付方式 (Freight)",
                "status": "FAIL",
                "detail": f"B/L 运费标记为 '{bl_info['freight']}'，LC 要求 '{freight_required}'。",
                "suggestion": "修正运费标记以匹配信用证要求。",
            })
            check_obj["fail_count"] += 1

    # 6. 装船日期 vs 最迟装运日
    if bl_info.get("shipment_date") and lc_analysis.get("latest_shipment"):
        try:
            ship_date_parsed = _parse_flex_date(bl_info["shipment_date"])
            latest_ship_parsed = _parse_flex_date(lc_analysis["latest_shipment"])
            if ship_date_parsed and latest_ship_parsed:
                if ship_date_parsed <= latest_ship_parsed:
                    check_obj["items"].append({
                        "check": "装船日期 vs 最迟装运日",
                        "status": "PASS",
                        "detail": f"装船日期 ({bl_info['shipment_date']}) 在最迟装运日 ({lc_analysis['latest_shipment']}) 之前或当天。",
                        "suggestion": None,
                    })
                    check_obj["pass_count"] += 1
                else:
                    check_obj["items"].append({
                        "check": "装船日期 vs 最迟装运日",
                        "status": "FAIL",
                        "detail": f"装船日期 ({bl_info['shipment_date']}) 晚于最迟装运日 ({lc_analysis['latest_shipment']}), 属于晚装运(Late Shipment)不符点。",
                        "suggestion": "这是严重的不符点。需要联系申请人修改信用证的装运期，或者申请接受此不符点。",
                    })
                    check_obj["fail_count"] += 1
        except Exception:
            pass

    # 7. 清洁已装船批注
    if text:
        t_upper = text.upper()
        if ("CLEAN ON BOARD" in t_upper or "CLEAN ABOARD" in t_upper
                or "ON BOARD" in t_lower ):
            check_obj["items"].append({
                "check": "清洁已装船批注 (Clean On Board)",
                "status": "PASS",
                "detail": "提单包含 'Clean On Board' 或类似装船批注。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        elif "SHIPPED" in t_upper or "LOADED" in t_upper:
            check_obj["items"].append({
                "check": "清洁已装船批注 (Clean On Board)",
                "status": "PASS",
                "detail": "提单包含 'Shipped on board' 或 'Loaded' 表述。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "清洁已装船批注 (Clean On Board)",
                "status": "WARN",
                "detail": "未能确认提单是否包含清洁装船批注。",
                "suggestion": "UCP600 要求提单必须显示货物已装船或已收妥待运并加注装船批注。请人工确认 B/L 是否有此批注。",
            })
            check_obj["warn_count"] += 1

    # 8. 全套正本
    if text and ("FULL SET" in text.upper() or "ORIGINAL" in text.upper()):
        check_obj["items"].append({
            "check": "全套/正本份数",
            "status": "PASS",
            "detail": "提单标注了 FULL SET 或 ORIGINAL 字样。",
            "suggestion": "确认提交的正本份数与 LC 要求一致（通常 3/3）。",
        })
        check_obj["pass_count"] += 1


def _check_ci(check_obj, text, fields, lc_analysis):
    """检查商业发票与 LC 条款的一致性。"""
    inv_info = extract_invoice_info(text)
    applicant = lc_analysis.get("applicant", "")
    beneficiary = lc_analysis.get("beneficiary", "")
    amount_lc = lc_analysis.get("amount", "")

    # 1. 卖方是否匹配受益人
    if inv_info.get("seller") and beneficiary:
        b_clean = re.sub(r'[\s.,\-]+', '', beneficiary.upper())
        s_clean = re.sub(r'[\s.,\-]+', '', inv_info["seller"].upper())
        if b_clean in s_clean or s_clean in b_clean or _name_match(inv_info["seller"], beneficiary):
            check_obj["items"].append({
                "check": "卖方/受益人一致性",
                "status": "PASS",
                "detail": f"发票卖方 '{inv_info['seller'][:40]}...' 与 LC 受益人匹配。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "卖方/受益人一致性",
                "status": "FAIL",
                "detail": f"发票卖方 '{inv_info['seller'][:40]}...' 与 LC 受益人不符。",
                "suggestion": "确保发票上的卖方名称与信用证受益人完全一致。",
            })
            check_obj["fail_count"] += 1

    # 2. 买方是否匹配申请人
    if inv_info.get("buyer") and applicant:
        a_clean = re.sub(r'[\s.,\-]+', '', applicant.upper())
        b_clean = re.sub(r'[\s.,\-]+', '', inv_info["buyer"].upper())
        if a_clean in b_clean or b_clean in a_clean or _name_match(inv_info["buyer"], applicant):
            check_obj["items"].append({
                "check": "买方/申请人一致性",
                "status": "PASS",
                "detail": f"发票买方 '{inv_info['buyer'][:40]}...' 与 LC 申请人匹配。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "买方/申请人一致性",
                "status": "WARN",
                "detail": f"发票买方 '{inv_info['buyer'][:40]}...' 可能与 LC 申请人不一致。",
                "suggestion": "确认发票买方是否应为 LC 开证申请人。",
            })
            check_obj["warn_count"] += 1

    # 3. 货物描述一致性（简化版）
    goods_lc = lc_analysis.get("goods_description", "")[:200]
    if goods_lc and len(text) > 100:
        keywords_lc = set(re.findall(r'[A-Z]{3,}', goods_lc.upper()))
        keywords_inv = set(re.findall(r'[A-Z]{3,}', text.upper()))
        overlap = keywords_lc & keywords_inv
        if len(overlap) >= min(3, len(keywords_lc)):
            check_obj["items"].append({
                "check": "货物描述一致性",
                "status": "PASS",
                "detail": f"发票中的关键词 ({len(overlap)}) 与 LC 货物描述基本吻合。",
                "suggestion": "UCP600 要求发票货物描述必须与信用证一致（可以更详细但不能矛盾）。",
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "货物描述一致性",
                "status": "WARN",
                "detail": "发票货物描述与 LC 货物描述的关键词重叠较少，请人工仔细核对。",
                "suggestion": "逐条对比发票品名与信用证45A条款。",
            })
            check_obj["warn_count"] += 1

    # 4. 金额不超过 LC 金额
    if inv_info.get("total_amount") and amount_lc:
        try:
            inv_amt = float(inv_info["total_amount"])
            amt_match = re.search(r'([\d,.]+)', amount_lc.replace(",", ""))
            if amt_match:
                lc_amt = float(amt_match.group(1).replace(",", ""))
                if inv_amt <= lc_amt * 1.10:  # 允许10%容差（如有39A）
                    check_obj["items"].append({
                        "check": "发票金额合理性",
                        "status": "PASS",
                        "detail": f"发票金额 {inv_info['currency']} {inv_amt:,.2f} 未超过 LC 金额上限。",
                        "suggestion": None,
                    })
                    check_obj["pass_count"] += 1
                else:
                    check_obj["items"].append({
                        "check": "发票金额合理性",
                        "status": "FAIL",
                        "detail": f"发票金额 {inv_info['currency']} {inv_amt:,.2f} 超过了 LC 金额 {lc_amt:,.2f} 的合理范围。",
                        "suggestion": "发票金额不得超过信用证金额（除非有39A容差条款允许超支）。",
                    })
                    check_obj["fail_count"] += 1
        except ValueError:
            pass


def _check_pl(check_obj, text, fields, lc_analysis):
    """检查装箱单。"""
    pl_info = extract_packing_list_info(text)

    if pl_info.get("total_packages") and pl_info["total_packages"]:
        check_obj["items"].append({
            "check": "包装数量",
            "status": "PASS",
            "detail": f"总包装数: {pl_info['total_packages']}",
            "suggestion": "确认包装数与发票、提单一致。",
        })
        check_obj["pass_count"] += 1

    if pl_info.get("gross_weight"):
        check_obj["items"].append({
            "check": "毛重信息",
            "status": "PASS",
            "detail": f"毛重: {pl_info['gross_weight']}",
            "suggestion": None,
        })
        check_obj["pass_count"] += 1

    if pl_info.get("net_weight"):
        check_obj["items"].append({
            "check": "净重信息",
            "status": "PASS",
            "detail": f"净重: {pl_info['net_weight']}",
            "suggestion": None,
        })
        check_obj["pass_count"] += 1

    if pl_info.get("measurement"):
        check_obj["items"].append({
            "check": "体积/尺寸",
            "status": "PASS",
            "detail": f"体积: {pl_info['measurement']}",
            "suggestion": None,
        })
        check_obj["pass_count"] += 1

    if not check_obj["items"]:
        check_obj["items"].append({
            "check": "装箱单基本信息",
            "status": "WARN",
            "detail": "未能自动提取装箱单关键信息，请人工核对包装数量、重量、体积等数据的一致性。",
            "suggestion": "确认 PL 数据与 CI、BL 一致。",
        })
        check_obj["warn_count"] += 1


def _check_draft(check_obj, text, fields, lc_analysis):
    """检查汇票。"""
    draft_info = lc_analysis.get("draft", {})
    ext_draft = extract_draft_info(text)

    # 是否需要汇票
    if not draft_info.get("required"):
        check_obj["items"].append({
            "check": "汇票提交要求",
            "status": "INFO",
            "detail": "根据 LC 条款分析，此信用证可能不强制要求提交汇票。如提交则按以下项目检查。",
            "suggestion": None,
        })

    # 付款期限
    if ext_draft.get("tenor") and draft_info.get("draft_at"):
        tenor_ext = ext_draft["tenor"].upper()
        tenor_lc = draft_info["draft_at"].upper()
        if "SIGHT" in tenor_ext and "SIGHT" in tenor_lc:
            check_obj["items"].append({
                "check": "汇票付款期限 (Tenor)",
                "status": "PASS",
                "detail": f"汇票付款期限 '{ext_draft['tenor']}' 与 LC 要求 '{draft_info['draft_at']}' 一致。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        elif tenor_ext and tenor_lc:
            check_obj["items"].append({
                "check": "汇票付款期限 (Tenor)",
                "status": "FAIL",
                "detail": f"汇票付款期限 '{ext_draft['tenor']}' 与 LC 要求 '{draft_info['draft_at']}' 不符。",
                "suggestion": "修正汇票付款期限以匹配信用证42C条款。",
            })
            check_obj["fail_count"] += 1

    # 受票人
    if ext_draft.get("drawee") and draft_info.get("drawee_detail"):
        d_clean = re.sub(r'[\s.\-,]+', '', ext_draft["drawee"].upper())
        lc_d_clean = re.sub(r'[\s.\-,]+', '', draft_info["drawee_detail"].upper())
        if d_clean in lc_d_clean or lc_d_clean in d_clean:
            check_obj["items"].append({
                "check": "受票人 (Drawee)",
                "status": "PASS",
                "detail": f"受票人 '{ext_draft['drawee'][:40]}...' 符合 LC 要求。",
                "suggestion": None,
            })
            check_obj["pass_count"] += 1
        else:
            check_obj["items"].append({
                "check": "受票人 (Drawee)",
                "status": "FAIL",
                "detail": f"受票人 '{ext_draft['drawee'][:40]}...' 与 LC 要求 '{draft_info['drawee_detail'][:40]}' 不符。",
                "suggestion": "修正受票人以匹配信用证42A条款指定的银行。",
            })
            check_obj["fail_count"] += 1

    # 金额
    if ext_draft.get("amount") and ext_draft.get("currency"):
        check_obj["items"].append({
            "check": "汇票金额",
            "status": "PASS",
            "detail": f"汇票金额: {ext_draft['currency']} {ext_draft['amount']}",
            "suggestion": "通常汇票金额应与发票金额一致。",
        })
        check_obj["pass_count"] += 1

    if not [i for i in check_obj["items"] if i["check"] != "汇票提交要求"]:
        check_obj["items"].append({
            "check": "汇票基本信息",
            "status": "WARN",
            "detail": "未能自动提取全部汇票字段，请人工核对付款期限、受票人、金额等关键要素。",
            "suggestion": "对照 LC 42/42A/42C 条款逐项核对汇票。",
        })
        check_obj["warn_count"] += 1


def _check_generic(check_obj, text, fields, lc_analysis):
    """通用单据检查。"""
    if text and len(text) > 50:
        check_obj["items"].append({
            "check": "文件内容完整性",
            "status": "PASS",
            "detail": f"文件已成功提取文本内容（约 {len(text)} 字符）。",
            "suggestion": "请人工逐条核对单据内容与 LC 46A 及 47A 条款的完全一致性。",
        })
        check_obj["pass_count"] += 1
    else:
        check_obj["items"].append({
            "check": "文件内容完整性",
            "status": "WARN",
            "detail": "文件文本较短或为空，无法进行自动化比对。",
            "suggestion": "确认文件格式正确且非纯图像文件。",
        })
        check_obj["warn_count"] += 1


# ──────────────────── 时间节点交叉检查 ────────────────────

def _check_time_nodes(doc_results, latest_ship_str, expiry_str, pres_days):
    """检查整体时间节点的逻辑关系。"""
    items = []

    # 尝试从提单获取装船日期
    bl_ship_date = None
    for doc in doc_results:
        doctype = identify_document_type(doc["filename"], doc.get("text", ""))
        if "提单" in doctype and doc.get("text"):
            bl_info = extract_bl_info(doc["text"])
            if bl_info.get("shipment_date"):
                bl_ship_date = _parse_flex_date(bl_info["shipment_date"])
                break

    if not bl_ship_date:
        return items

    try:
        latest_ship_dt = _parse_flex_date(latest_ship_str) if latest_ship_str else None
        expiry_dt = _parse_flex_date(expiry_str) if expiry_str else None
    except Exception:
        return items

    # 计算理论最迟交单日
    if bl_ship_date:
        latest_present = bl_ship_date + timedelta(days=pres_days)

        # 交单窗口检查
        now = datetime.now().date()
        expiry_date_val = expiry_dt.date() if expiry_dt and isinstance(expiry_dt, datetime) else None
        latest_present_date = latest_present.date() if isinstance(latest_present, datetime) else latest_present
        present_deadline = min(
            latest_present_date,
            expiry_date_val if expiry_date_val else latest_present_date
        ) if expiry_date_val else latest_present_date

        if now > present_deadline:
            items.append({
                "check": "交单时效性",
                "status": "FAIL",
                "detail": f"当前日期 ({now.isoformat()} ) 已超过最迟交单截止日 ({present_deadline.isoformat()}).",
                "suggestion": "尽快联系开证行或申请人说明情况，考虑不符点交单。",
            })
        elif (present_deadline - now).days <= 5:
            items.append({
                "check": "交单时效性",
                "status": "WARN",
                "detail": f"距最迟交单截止日仅剩 {(present_deadline - now).days} 天，请注意及时寄单。",
                "suggestion": "国际快递通常需 3-5 个工作日，建议立即安排寄送正本单据。",
            })
        else:
            items.append({
                "check": "交单时效性",
                "status": "PASS",
                "detail": f"最迟交单截止日为 {present_deadline.isoformat()} ，目前尚有 {(present_deadline - now).days} 天余量。",
                "suggestion": None,
            })
    return items


# ──────────────────── 辅助函数 ────────────────────

def _port_match(port_a, port_b):
    """宽松比较两个港口名是否匹配。"""
    a_clean = re.sub(r'[\s.\-]', '', port_a.upper())
    b_clean = re.sub(r'[\s.\-]', '', port_b.upper())
    if a_clean == b_clean:
        return True
    # 子集匹配
    if len(a_clean) > 4 and a_clean in b_clean:
        return True
    if len(b_clean) > 4 and b_clean in a_clean:
        return True
    return False


def _name_match(name_a, name_b):
    """宽松比较两个公司名是否匹配。"""
    a_clean = re.sub(r'[^A-Z0-9]', '', name_a.upper())
    b_clean = re.sub(r'[^A-Z0-9]', '', name_b.upper())
    if a_clean == b_clean:
        return True
    if a_clean in b_clean and len(a_clean) > 10:
        return True
    if b_clean in a_clean and len(b_clean) > 10:
        return True
    return False


def _parse_flex_date(date_str):
    """灵活解析各种日期格式。"""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    formats = [
        '%y%m%d', '%Y%m%d',          # YYMMDD, YYYYMMDD
        '%d/%m/%Y', '%d-%m-%Y',      # DD/MM/YYYY
        '%m/%d/%Y', '%m-%d-%Y',      # MM/DD/YYYY
        '%d/%m/%y', '%d-%m-%y',      # DD/MM/YY
        '%Y-%m-%d',                   # YYYY-MM-DD
        '%b %d %Y', '%B %d %Y',      # Jan 01 2026
        '%d %b %Y', '%d %B %Y',      # 01 Jan 2026
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    # 最后尝试 dateutil
    try:
        return parse_date(date_str)
    except Exception:
        return None


def summarize_checks(compliance_results):
    """汇总合规检查结果，返回统计摘要。"""
    total_pass = sum(c.get("pass_count", 0) for c in compliance_results)
    total_warn = sum(c.get("warn_count", 0) for c in compliance_results)
    total_fail = sum(c.get("fail_count", 0) for c in compliance_results)
    total_items = total_pass + total_warn + total_fail

    failed_docs = [c["filename"] for c in compliance_results if c.get("fail_count", 0) > 0]
    warned_docs = [c["filename"] for c in compliance_results if c.get("warn_count", 0) > 0 and c.get("fail_count", 0) == 0]

    if total_fail > 0:
        overall = "❌ 存在不符点"
        risk_level = "高"
    elif total_warn > 0:
        overall = "⚠️ 需要关注"
        risk_level = "中"
    else:
        overall = "✅ 合规"
        risk_level = "低"

    return {
        "overall_status": overall,
        "risk_level": risk_level,
        "total_documents": len(compliance_results),
        "total_checks": total_items,
        "pass_count": total_pass,
        "warn_count": total_warn,
        "fail_count": total_fail,
        "documents_with_issues": failed_docs,
        "documents_needing_attention": warned_docs,
        "recommendation": get_recommendation(total_fail, total_warn, failed_docs),
    }


def get_recommendation(fail_count, warn_count, failed_docs):
    """根据检查结果给出操作建议（中文）。"""
    if fail_count > 0:
        return (
            f"检测到 {fail_count} 项不符点，涉及以下文件："
            + "、".join(failed_docs[:5])
            + "。建议：\n"
            "1. 优先修正所有 FAIL 级别的项目后再交单；\n"
            "2. 如无法在装运前修改，可与申请人沟通不符点交单的可能性；\n"
            "3. 重大不符点（如晚装运、超金额等）可能导致拒付风险。"
        )
    elif warn_count > 0:
        return (
            f"没有发现明确不符点，但有 {warn_count} 项需要注意的事项。"
            f"建议交单前再次人工复核这些 WARN 项目，确保万无一失。"
        )
    else:
        return "所有检查项均通过。建议在正式交单前再做一次最终的人工复核。"
