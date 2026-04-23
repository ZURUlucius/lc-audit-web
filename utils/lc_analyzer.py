# -*- coding: utf-8 -*-
"""
LC 条款分析器 — 解析 SWIFT MT700 字段并执行条款分析
增强版：完整提取 42/42A/42C 汇票要求、47A 详细附加条件、49 确认方式等
"""

import re


# ──────────────────── 字段解析 ────────────────────

def parse_mt700_fields(text):
    """从文本中提取所有 SWIFT MT700 字段。

    Supports two common formats:
      1. Single-line:  :20:VALUE
      2. Two-line (HSBC/JPMorgan advising):  :20:Label\\n: :VALUE

    Also handles HSBC-style continuation lines that start with ": ".
    """
    fields = {}

    # Step 1: Find all field tag positions
    # Matches patterns like:  :27:,  :40A:,  :20 ,  :72Z:
    tag_pattern = re.compile(r'^(\s*):(\d{2}[A-Z]?)\s*:', re.MULTILINE)
    matches = list(tag_pattern.finditer(text))

    for i, match in enumerate(matches):
        tag = match.group(2)
        start_pos = match.end()

        # Where does this field's content end?
        if i + 1 < len(matches):
            end_pos = matches[i + 1].start()
        else:
            end_pos = len(text)

        raw_block = text[start_pos:end_pos]

        # Step 2: Parse the block line by line
        lines = raw_block.split('\n')
        value_lines = []
        found_first_value = False

        for line in lines:
            stripped = line.strip()

            # Skip empty lines and pure continuation markers
            if not stripped or stripped in (':', ': :', ':  ', ':   ', ':\t', ':\t\t'):
                continue

            # Skip the ": " prefix on continuation/ value lines
            if stripped.startswith(': '):
                content = stripped[2:].strip()
                if not content:
                    continue
                value_lines.append(content)
                found_first_value = True
                continue
            elif stripped.startswith(':'):
                content = stripped[1:].strip()
                if not content:
                    continue
                value_lines.append(content)
                found_first_value = True
                continue

            # Line without ":" prefix - could be a label or a continuation
            if not found_first_value and not value_lines:
                # First non-empty, non-":" line after the tag -> likely a label
                # Skip it ONLY if it looks like a label (short text with spaces, no +/- prefix)
                if len(stripped) < 60 and not stripped.startswith('+') and not stripped.startswith('-'):
                    if not re.match(r'^[\d/,.\-\(\)A-Z]+$', stripped):
                        continue  # Skip label like "Documentary Credit Number"
                # If it doesn't look like a label, treat as value
                value_lines.append(stripped)
                found_first_value = True
            else:
                # Continuation of previous line's content
                value_lines.append(stripped)

        value = ' '.join(value_lines).strip()

        # Clean up any leading ": " that may remain from continuation line parsing
        if value.startswith(': '):
            value = value[2:].strip()
        elif value.startswith(':'):
            value = value[1:].strip()

        # ── 清理银行页眉/页脚噪音 ──
        # HSBC/JPMorgan advising PDF 每页底部含银行名称+地址+SWIFT等页脚
        # 这些会污染字段值。常见模式:
        #   "The Hongkong and Shanghai Banking Corporation Limited"
        #   "HSBC ... BUILDING ... Page N / M"
        #   "Tel: +852 ... SWIFT: HSBCHKHHHKH DCAAM..."
        #   "--- Page N ---"
        noise_patterns = [
            r'\s*The Hongkong and Shanghai Banking Corporation Limited.*?Page\s+\d+\s*/\s*\d+',
            r'\s*HSBC\s+.*?Page\s+\d+\s*/\s*\d+',
            r'\s*Tel:\s*[\d\-\s]+.*?SWIFT:.*',
            r'\s*---\s*Page\s+\d+\s*---.*',
            r'\s*DCAAM\d+\s*$',
        ]
        for npat in noise_patterns:
            value = re.sub(npat, '', value, flags=re.IGNORECASE).strip()
        # 去掉末尾残留的 " :" 空标记
        value = re.sub(r'\s*:\s*$', '', value).strip()
        # 去掉中间的 " ." 孤立句号（HSBC 续行分隔符）
        value = re.sub(r'\s*\.\s*:', ':', value)
        value = re.sub(r'(?<!\w)\.\s*(?=[A-Z])', ' ', value)

        if tag not in fields and value:
            fields[tag] = value

    return fields


# ──────────────────── 文本清理 ────────────────────

def clean_text(text):
    return text.replace("\\n", "\n").strip() if text else ""


# ─────────────── 42 汇票条款详细提取 ───────────────

def parse_draft_requirements(fields):
    """
    解析汇票相关条款（42/42A/42C）。
    返回结构化字典，包含是否需要提交汇票、金额比例、付款期限、受票人等信息。
    """
    draft_42 = fields.get("42", fields.get("42A", ""))
    draft_42c = fields.get("42C", "")   # Draft at / 付款条件 (AT SIGHT / XX DAYS)
    draft_42a_drawee = fields.get("42A", "")  # Drawee / 受票人

    result = {
        "required": False,          # 是否必须提交汇票
        "has_draft_clause": False,  # 是否存在任何汇票相关条款
        "draft_at": "",             # 即期/远期 (AT SIGHT / 30 DAYS SIGHT 等)
        "drawee_bank": "",          # 受票行
        "drawee_detail": "",        # 受票人详细信息
        "percentage": "",           # 汇票金额占比 (100% / etc)
        "raw_text": "",
        "notes": [],
    }

    # 合并所有汇票相关文本
    all_draft = ""
    if draft_42:
        all_draft += draft_42 + "\n"
    if draft_42c:
        all_draft += draft_42c + "\n"
    if draft_42a_drawee:
        all_draft += draft_42a_drawee + "\n"

    raw = all_draft.strip().upper()

    if not raw or raw == "N/A":
        return result

    result["has_draft_clause"] = True
    result["raw_text"] = all_draft.strip()

    # 判断是否需要提交汇票
    draft_keywords = [
        'DRAFT', 'DRAFTS', 'BILL OF EXCHANGE', 'EXCHANGE',
        'HUIPIAO', '汇票', 'USANCE', 'AT SIGHT'
    ]
    has_any_kw = any(kw in raw for kw in draft_keywords)

    # 在 46A 中查找汇票要求
    doc_reqs = fields.get("46A", "")
    has_in_46a = any(kw in doc_reqs.upper() for kw in ['DRAFT', 'DRAFTS', 'BILL OF EXCHANGE'])

    if has_any_kw or has_in_46a:
        result["required"] = True
    else:
        # 如果有 42 字段但没有明确提到 draft，可能只是指定了受票人
        result["required"] = bool(draft_42c)

    # 提取即期/远期
    sight_match = re.search(r'AT\s+SIGHT', raw)
    days_match = re.search(r'AT\s+(\d+)\s*(?:DAY)?S?\s*SIGHT?', raw)
    usance_match = re.search(r'USANCE\s*:?\s*(.+)', raw)
    after_match = re.search(r'(\d+)\s*DAYS?\s+(?:AFTER|FROM)\s+(?:B/L|BL|SHIPMENT|DATE)', raw)

    if sight_match:
        result["draft_at"] = "AT SIGHT（即期）"
    elif days_match:
        result["draft_at"] = f"{days_match.group(1)} DAYS SIGHT（{days_match.group(1)}天远期）"
    elif after_match:
        result["draft_at"] = f"{after_match.group(1)} DAYS AFTER SHIPMENT DATE（装运后{after_match.group(1)}天远期）"
    elif usance_match:
        result["draft_at"] = usance_match.group(1).strip()

    # 提取受票人
    drawee_patterns = [
        r'DRAWEE\s*:?\s*(.+)',
        r'ON\s+([A-Z][\w\s&.,]+(?:BANK|NA|INC|LTD|CORP))',
        r'(?:FOR|TO)\s*(?:THE\s+)?(ACCOUNT\s+OF\s+.+)',
    ]
    for pat in drawee_patterns:
        m = re.search(pat, raw, re.IGNORECASE | re.DOTALL)
        if m:
            result["drawee_detail"] = m.group(1).strip()
            break

    # 从 42A 获取受票行代码
    if draft_42a_drawee:
        result["drawee_bank"] = draft_42a_drawee.strip()

    # 提取百分比
    pct_match = re.search(r'(\d+)\s*%\s*(?:OF\s+INVOICE|OF\s+LC)?', raw)
    if pct_match:
        result["percentage"] = f"{pct_match.group(1)}%"
    else:
        result["percentage"] = "100%（默认）"

    # 生成注意事项
    if result["required"]:
        result["notes"].append("[OK] 此信用证要求提交汇票")
    else:
        result["notes"].append("[INFO] 未发现明确的汇票提交要求")

    if result["draft_at"]:
        result["notes"].append(f"[DRAFT] 汇票类型: {result['draft_at']}")

    if result["drawee_detail"]:
        result["notes"].append(f"[DRAWEE] 受票人: {result['drawee_detail']}")

    return result


# ─────────────── 47A 附加条件详细提取 ───────────────

def parse_additional_conditions(cond_47a):
    """
    解析 47A Additional Conditions 为分类后的详细列表。
    返回按类别分组的结果。
    """
    result = {
        "raw": cond_47a,
        "items": [],         # 原始条目列表
        "categories": {},    # 分类汇总
        "summary_notes": [], # 关键摘要提示
    }

    if not cond_47a or cond_47a == "N/A":
        result["summary_notes"].append("无 47A 附加条件")
        return result

    # 按 + 开头或换行分隔
    lines = []
    for line in cond_47a.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Handle both "+ CONTENT" and ":+ CONTENT" formats (HSBC advising style)
        if line.startswith(":+") or line.startswith("+") or line.startswith("-") or line.startswith(":-"):
            lines.append(line[1:].strip())
        elif line.startswith("/PHONBAN/") or line.startswith("/"):
            continue  # SWIFT 特殊标记
        elif lines and len(line) > 10:
            # 续行（非字段标签的文本）
            lines[-1] += " " + line
        else:
            pass

    # 过滤掉空行和过短的内容
    items = [l for l in lines if len(l) > 5]
    result["items"] = items

    # 对每个条目进行分类
    categories = {
        "document_requirements": [],     # 单据要求
        "shipping_conditions": [],       # 运输条件
        "banking_charges": [],           # 银行费用
        "presentation_rules": [],        # 交单规则
        "insurance_requirements": [],    # 保险要求
        "certificates": [],              # 证明文件
        "penalty_deduction": [],         # 罚款扣款
        "other_conditions": [],          # 其他
    }

    for item in items:
        item_upper = item.upper()
        classified = False

        # 银行费用类
        if any(kw in item_upper for kw in [
            'CHARGE', 'FEE', 'COMMISSION', 'EXPENSE',
            'ACCOUNT', 'REIMBURSE', 'BENEFICIARY\'S'
        ]):
            if any(kw in item_upper for kw in ['CHARGE', 'FEE', 'COMMISSION']):
                categories["banking_charges"].append(item)
                classified = True

        # 交单规则类
        if not classified and any(kw in item_upper for kw in [
            'PRESENT', 'DOCUMENT', 'L/C', 'VALID', 'EXPIRY',
            'PERIOD', 'DAYS AFTER', 'BEFORE', 'WITHIN', 'LATEST'
        ]):
            categories["presentation_rules"].append(item)
            classified = True

        # 运输类
        if not classified and any(kw in item_upper for kw in [
            'SHIP', 'TRANSHIP', 'PARTIAL', 'LOADING', 'DISCHARGE',
            'PORT', 'CONTAINER', 'VESSEL', 'AIRPORT', 'ROUTE'
        ]):
            categories["shipping_conditions"].append(item)
            classified = True

        # 保险类
        if not classified and any(kw in item_upper for kw in [
            'INSURANCE', 'INSURER', 'COVER', 'POLICY', 'CERTIFICATE',
            'ICC', 'INSTITUTE'
        ]):
            categories["insurance_requirements"].append(item)
            classified = True

        # 证明文件类
        if not classified and any(kw in item_upper for kw in [
            'CERTIFICATE', 'DECLARATION', 'STATEMENT', 'AFFIDAVIT',
            'ATTESTATION', 'CONFIRM', 'ORIGIN', 'HEALTH', 'PHYTOSANITARY'
        ]):
            categories["certificates"].append(item)
            classified = True

        # 扣款罚款类
        if not classified and any(kw in item_upper for kw in [
            'DEDUCT', 'LESS', 'PENALTY', 'REDUCE', 'DISCOUNT'
        ]):
            categories["penalty_deduction"].append(item)
            classified = True

        if not classified:
            categories["other_conditions"].append(item)

    result["categories"] = categories

    # 生成关键摘要
    if categories["penalty_deduction"]:
        result["summary_notes"].append(
            f"[WARN] 发现 {len(categories['penalty_deduction'])} 条扣款/罚款条款，请注意实际收款金额可能减少"
        )

    if categories["certificates"]:
        cert_names = [c[:40] + "..." if len(c) > 40 else c for c in categories["certificates"]]
        result["summary_notes"].append(
            f"[DOC] 需要 {len(categories['certificates'])} 种额外证明文件: {', '.join(cert_names[:3])}"
        )

    if categories["banking_charges"]:
        result["summary_notes"].append(
            f"[FEE] 包含银行费用分摊条款 ({len(categories['banking_charges'])} 条)"
        )

    if categories["shipping_conditions"]:
        result["summary_notes"].append(
            f"[SHIP] 包含额外运输限制条件 ({len(categories['shipping_conditions'])} 条)"
        )

    return result


# ─────────────── 46A 单据要求解析（增强版）───────────────

def parse_doc_list(doc_46a):
    """将 46A 字段解析为结构化单据列表。

    Handles formats:
      - "+ CONTENT" lines (standard MT700)
      - ":+ CONTENT" lines (HSBC advising style, joined with spaces)
      - ": " as line-separator artifact from HSBC format
    """
    docs = []
    if not doc_46a:
        return docs

    # Pre-process: normalize HSBC format artifacts
    # After parse_mt700_fields joins lines with space, we get patterns like:
    #   "+ ITEM1 :+ ITEM2" or "+ ITEM1 :+ ITEM2 :CONTINUATION"
    #   or HSBC style: "1/ INVOICE ... . :2/ B/L ... . :3/ CO ..."
    normalized = doc_46a

    # Replace " :+" (colon then plus) with newline - this is the HSBC new-entry marker
    normalized = re.sub(r'\s*:\s*\+', '\n+', normalized)

    # HSBC item separator: ". :" or " ::" before a number like "2/", "3/", "4/"
    # Pattern: " . :2/" or " ::2/" -> split into new entry
    normalized = re.sub(r'\s*\.\s*:(?=\d+\s*/)', '\n', normalized)
    normalized = re.sub(r'\s*::(?=\d+\s*/)', '\n', normalized)

    # Split into individual document entries
    raw_lines = normalized.split("\n")
    entries = []
    current = []

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect new entry: starts with "+", or with "N/" (HSBC numbered list: 1/, 2/, 3/...)
        is_new_entry = stripped.startswith("+") or re.match(r'^\d+\s*/', stripped)

        if is_new_entry and current:
            entries.append(" ".join(current))
            current = []

        content = stripped.lstrip("+").strip()
        if content:
            current.append(content)

    if current:
        entries.append(" ".join(current))

    for content in entries:
        if not content:
            continue
        doc_type = identify_document_type(content)
        docs.append({
            "type": doc_type,
            "raw_content": content,
            "key_points": extract_key_points(content),
        })
    return docs


def identify_document_type(text):
    """根据文本内容识别单据类型（中文）。"""
    t = text.upper()
    mapping = {
        ("COMMERCIAL INVOICE",): "商业发票 (Commercial Invoice)",
        ("PROFORMA INVOICE",): "形式发票",
        ("PACKING LIST", "WEIGHT LIST"): "装箱单/重量单",
        ("BILL OF LADING", "B/L", "BILLS OF LADING", "OCEAN B/L"): "海运提单 (Bill of Lading)",
        ("AIRWAY BILL", "AWB", "AIRWAYBILL"): "航空运单",
        ("CERTIFICATE OF ORIGIN", "CO"): "原产地证",
        ("INSURANCE POLICY", "INSURANCE CERTIFICATE"): "保险单/凭证",
        ("DRAFT", "BILL OF EXCHANGE"): "汇票 (Draft)",
        ("INSPECTION CERTIFICATE", "INSPECTION REPORT"): "检验证书",
        ("QUALITY CERTIFICATE",): "品质证明书",
        ("QUANTITY CERTIFICATE",): "数量证明书",
        ("WEIGHT CERTIFICATE",): "重量证明书",
        ("BENEFICIARY'S CERTIFICATE",): "受益人证明",
        ("BENEFICIARY'S DECLARATION",): "受益人声明",
        ("SHIPPING ADVICE", "SHIPPING ADVICE", "ADVICE OF SHIPMENT"): "装运通知",
        ("GSP FORM A", "FORM A", "CERTIFICATE OF ORIGIN GSP"): "普惠制产地证 (Form A)",
        ("CUSTOMS INVOICE",): "海关发票",
        ("CONSULAR INVOICE",): "领事发票",
        ("TELEX RELEASE",): "电放保函",
        ("COURIER RECEIPT",): "快递收据",
        ("POST RECEIPT",): "邮政收据",
    }

    for keywords, cn_name in mapping.items():
        if any(kw in t for kw in keywords):
            return cn_name

    return "其他单据"


def extract_key_points(text):
    """从单据描述中提取关键要求点。"""
    points = []

    # 份数
    qty_patterns = [
        r'(?:IN|IN\s+DUPLICATE|IN\s+TRIPLICATE|IN\s+QUADRUPLICATE|IN\s+SEXTUPLICATE)',
        r'(\d)\s*(?:SETS?|COPY|COPIES?)',
        r'(FULL\s+SET|ORIGINAL\s*\+\s*COPY)',
        r'(?:SET\s*)?\((\d)/(\d)\)',
    ]
    for pat in qty_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                if m.lastindex and m.group(1) is not None and int(m.group(1)) > 0:
                    points.append(f"数量: {m.group(0)}")
                else:
                    points.append(f"数量: {m.group(0)}")
            except (ValueError, TypeError):
                points.append(f"数量: {m.group(0)}")
            break

    # 签署要求
    sign_patterns = [r'(?:SIGNED|MANUALLY\s+SIGNED)', r'CERTIFIED']
    for pat in sign_patterns:
        if re.search(pat, text, re.IGNORECASE):
            points.append("需签署")
            break

    # 抬头要求
    head_patterns = [
        r'MADE\s+OUT\s+(?:TO\s+THE\s+ORDER\s+OF|TO\s+ORDER\s+OF)\s*(.+?)(?:\s*(?:MARKED|NOTIFY|$))',
        r'(?:CONSIGNEE|TO)\s*:\s*(.+?)(?:\s*$)',
    ]
    for pat in head_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            points.append(f"抬头: {m.group(1).strip()}")
            break

    # 通知方
    notify_m = re.search(r'NOTIF[Y]?.*?(.+?)(?:\s*(?:MARKED|$))', text, re.IGNORECASE | re.DOTALL)
    if notify_m:
        points.append(f"通知方: {notify_m.group(1).strip()}")

    # 运费标记
    freight_m = re.search(r'(?:FREIGHT|CARRIAGE)\s+(PREPAID|COLLECT|PAYABLE\s+AT\s+DESTINATION)',
                          text, re.IGNORECASE)
    if freight_m:
        points.append(f"运费: {freight_m.group(1)}")

    # 时间要求
    date_m = re.search(r'DATE[D]?\s*(?:NOT\s+LATER\s+THAN|WITHIN|NOT\s+LATE\s+THAN|BEFORE)\s*(.+)',
                       text, re.IGNORECASE)
    if date_m:
        points.append(f"时间要求: {date_m.group(1).strip()}")

    return points


# ─────────────── 条款异常检测（增强版）───────────────

def detect_anomalies(fields):
    """
    检测四类条款异常：
      1. 自相矛盾 (Contradictions)
      2. 操作上不合理 (Operationally Unreasonable)
      3. 模糊/不完整 (Ambiguous / Incomplete)
      4. 非常规财务条款 (Unusual Financial Clauses)
    返回异常字典列表。
    """
    anomalies = []
    f = fields
    cond_47a = (f.get("47A", "") + " " + f.get("72", "")).upper()
    cond_47a_raw = (f.get("47A", "") + " " + f.get("72", ""))

    # ════════════ 类型 1：自相矛盾 ════════════

    # 分批装运 vs 47A 矛盾
    partials = f.get("43P", "").upper()
    if "NOT ALLOWED" in partials or "PROHIBITED" in partials:
        if "PARTIAL" in cond_47a and "ALLOWED" in cond_47a:
            anomalies.append(_make_anomaly(
                type_name="自相矛盾",
                severity="HIGH",
                fields=["43P", "47A"],
                text=f"43P 规定 '{f.get('43P', '')}' 但 47A 可能允许分批装运",
                description="分批装运条款存在潜在矛盾。43P 明确禁止分批装运，但 47A 附加条件中可能隐含允许分批的含义，请与开证行确认。",
            ))

    # 转运 vs 47A 矛盾
    tranship = f.get("43T", "").upper()
    if "NOT ALLOWED" in tranship or "PROHIBITED" in tranship:
        if ("TRANSHIP" in cond_47a and "ALLOWED" in cond_47a) or ("TRANSSHIPMENT" in cond_47a and "ALLOWED" in cond_47a):
            anomalies.append(_make_anomaly(
                type_name="自相矛盾",
                severity="HIGH",
                fields=["43T", "47A"],
                text=f"43T 禁止转运，但 47A 可能允许转运",
                description="转运条款存在潜在矛盾，请与开证行确认。",
            ))

    # 金额容差 vs 精确金额要求
    tolerance = f.get("39A", "")
    if tolerance:
        exact_pattern = re.compile(r'EXACT\s+AMOUNT|NO\s+TOLERANCE|FIXED\s+AMOUNT')
        for line in (f.get("47A", "") + "\n" + f.get("46A", "")).split("\n"):
            if exact_pattern.search(line.upper()):
                anomalies.append(_make_anomaly(
                    type_name="自相矛盾",
                    severity="HIGH",
                    fields=["39A", "47A/46A"],
                    text=f"39A 允许浮动({tolerance})，但 47A 或 46A 要求精确金额",
                    description="金额浮动条款与单据/附加条件中的精确金额要求矛盾。请确认实际操作应以哪个为准。",
                ))
                break

    # ════════════ 类型 2：操作上不合理 ════════════

    # 极短交单期
    pres_period = f.get("48", "")
    short_match = re.search(r'(\d+)\s*DAYS?', pres_period.upper())
    if short_match and int(short_match.group(1)) < 7:
        anomalies.append(_make_anomaly(
            type_name="操作上不合理",
            severity="MEDIUM",
            fields=["48"],
            text=f"交单期仅 {short_match.group(1)} 天",
            description=f"交单期仅 {short_match.group(1)} 天，对于国际海运来说可能不足以准备全套正本单据。通常建议至少 14-21 天。如遇船期延误或寄单延迟风险很高。",
        ))

    # 申请人签署的证明文件
    if re.search(r'APPLICANT.*?(?:CERTIFICATE|SIGN(?:ED)?|ATTEST|CONFIRM|APPROVE|ACCEPT)',
                 cond_47a, re.IGNORECASE | re.DOTALL):
        anomalies.append(_make_anomaly(
            type_name="操作上不合理",
            severity="MEDIUM",
            fields=["47A"],
            text="要求申请人签署或确认的证明文件",
            description="条款要求获取由申请人（买方）签署或确认的文件。如果申请人拒绝配合或不及时响应，将导致无法按时交单。建议申请修改为第三方机构出具的证明。",
        ))

    # 非常短的装运期
    ship_date = f.get("44C", "")
    expiry_date = f.get("31D", "")
    # 如果装运日和效期太近（<15天），提示风险
    try:
        ship_str = re.search(r'(\d{6})', ship_date)
        exp_str = re.search(r'(\d{6})', expiry_date)
        if ship_str and exp_str:
            s_year = 2000 + int(ship_str.group(1)[:2])
            s_mon = int(ship_str.group(1)[2:4])
            s_day = int(ship_str.group(1)[4:6])
            e_year = 2000 + int(exp_str.group(1)[:2])
            e_mon = int(exp_str.group(1)[2:4])
            e_day = int(exp_str.group(1)[4:6])
            gap_days = (e_year - s_year) * 365 + (e_mon - s_mon) * 30 + (e_day - s_day)
            if 0 <= gap_days < 15:
                anomalies.append(_make_anomaly(
                    type_name="操作上不合理",
                    severity="HIGH",
                    fields=["44C", "31D"],
                    text=f"最迟装运日({ship_str.group(1)})与有效期({exp_str.group(1)})仅间隔约{gap_days}天",
                    description="装运日期与信用证有效期间隔过短。扣除交单期后几乎没有缓冲余地，一旦装运稍有延误就可能错过交单窗口。建议申请延展有效期。",
                ))
    except Exception:
        pass

    # ════════════ 类型 3：模糊/不完整 ════════════

    # 引用外部附件
    if re.search(r'\bANNEX\b|\bATTACH(?:ED|MENT)|AS PER SEPARATE\b|SEE ATTACHED|REFER TO SEPARATE',
                 cond_47a, re.IGNORECASE):
        anomalies.append(_make_anomaly(
            type_name="模糊/不完整",
            severity="MEDIUM",
            fields=["47A"],
            text="引用了外部附件（Annex/Attachment）",
            description="条款引用了未包含在信用证正文中的附件文件。请确认该附件是否已收到且内容完整。缺少附件可能导致交单时无法满足要求。",
        ))

    # 引用未提供的参考号
    ref_pattern = re.compile(r'(?:REF(?:ERENCE)?|NO\.?|NUMBER|CODE|ID)\s*:?\s*([A-Z0-9/\-]{5,})')
    refs_found = ref_pattern.findall(cond_47a)
    if refs_found:
        anomalies.append(_make_anomaly(
            type_name="模糊/不完整",
            severity="LOW",
            fields=["47A"],
            text=f"引用了外部参考编号: {', '.join(refs_found[:3])}",
            description="条款引用了一个或多个外部参考编号（如订单号、合同号等）。请确认您手头持有对应文件并能按要求提供。",
        ))

    # 模糊的货物描述
    goods_desc = f.get("45A", "")
    if goods_desc and len(goods_desc.strip()) < 20:
        anomalies.append(_make_anomaly(
            type_name="模糊/不完整",
            severity="LOW",
            fields=["45A"],
            text="货物描述过于简短",
            description="45A 货物描述非常简短，可能在制作发票、提单等单据时难以确保与信用证的严格一致。建议补充更详细的货物品名、规格等信息。",
        ))

    # ════════════ 类型 4：非常规财务条款 ════════════

    # 自动扣款超过 5%
    deduce_pattern = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:DEDUCT|LESS|PENALTY|REDUCE|HOLD|RETAIN)',
                               cond_47a, re.IGNORECASE)
    if deduce_pattern and float(deduce_pattern.group(1)) > 5:
        anomalies.append(_make_anomaly(
            type_name="非常规财务条款",
            severity="HIGH",
            fields=["47A"],
            text=f"自动扣款 {deduce_pattern.group(1)}%",
            description=f"条款规定了高达 {deduce_pattern.group(1)}% 的自动扣款机制。这超出了标准不符点费用的范围（通常为每个不符点 USD 50-100），可能导致实际收款大幅减少。请评估此条款对利润的影响。",
        ))

    # 第三方偿付复杂条款
    if re.search(r'REIMBURSE(?:MENT)?\s*(?:BANK|CLAIM|INSTRUCTION)', cond_47a, re.IGNORECASE):
        if re.search(r'(?:UNLESS|EXCEPT|ONLY IF|SUBJECT TO)', cond_47a, re.IGNORECASE):
            anomalies.append(_make_anomaly(
                type_name="非常规财务条款",
                severity="MEDIUM",
                fields=["47A", "53"],
                text="偿付条款附带复杂条件",
                description="偿付行条款附带了额外的限制条件，可能导致收款延迟或产生额外费用。请仔细阅读偿付指示并确认理解其影响。",
            ))

    # 隐含转让限制
    if re.search(r'(?:NOT TRANSFERABLE|ASSIGNMENT NOT ALLOWED|WITHOUT CONSENT)', cond_47a, re.IGNORECASE):
        anomalies.append(_make_anomaly(
            type_name="非常规财务条款",
            severity="LOW",
            fields=["47A"],
            text="包含转让/让渡限制",
            description="信用证条款暗示了转让或权益让渡的限制。如果您计划将信用证项下的收款权转让给融资银行，这些限制可能会造成障碍。",
        ))

    return anomalies


def _make_anomaly(type_name, severity, fields, text, description):
    """构造标准化的异常字典。"""
    return {
        "type": type_name,
        "severity": severity,
        "fields": fields,
        "text": text,
        "description": description,
        "severity_cn": {"HIGH": "高", "MEDIUM": "中", "LOW": "低"}.get(severity, "未知"),
        "clause_ref": ", ".join(fields) if isinstance(fields, list) else str(fields),
    }


# ───────────────── 主分析函数 ─────────────────

def _format_swift_date(date_str):
    """将 SWIFT MT700 日期格式 (YYMMDD) 转为可读格式 (YYYY-MM-DD)。"""
    if not date_str or date_str == "N/A":
        return date_str
    s = str(date_str).strip()
    # 尝试解析 YYMMDD 或 YYYYMMDD
    if len(s) == 6 and s.isdigit():
        year = int(s[:2])
        if year >= 80:
            year += 1900
        else:
            year += 2000
        return f"{year}-{s[2:4]}-{s[4:6]}"
    elif len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def analyze_lc(lc_text):
    """
    执行完整的信用证条款分析。
    返回结构化分析结果字典。
    """
    fields = parse_mt700_fields(lc_text)

    # ── 基本信息 ──
    # LC号码：优先取 :21 (Documentary Credit Number)，其次 :20 (Sender's Reference)
    # 很多银行通知格式中，:20 是银行内部参考号，:21 才是真正的信用证编号
    lc_no = fields.get("21", fields.get("20", "N/A"))
    amount = fields.get("32B", "N/A")
    expiry_raw = fields.get("31D", "N/A")
    issue_date_raw = fields.get("31C", "N/A")
    # 格式化开证日期 YYMMDD -> YYYY-MM-DD
    issue_date = _format_swift_date(issue_date_raw)
    applicant = clean_text(fields.get("50", "N/A"))
    beneficiary = clean_text(fields.get("59", "N/A"))
    issuing_bank_raw = fields.get("52A", fields.get("52D", fields.get("51", "N/A")))
    issuing_bank = clean_text(issuing_bank_raw)
    latest_ship = fields.get("44C", "N/A")
    port_load = fields.get("44E", "N/A")
    port_disc = fields.get("44F", "N/A")
    goods_desc = clean_text(fields.get("45A", "N/A"))
    # Form of LC: 40B (newer) or 40A (older)
    form_of_lc = fields.get("40B", fields.get("40A", "N/A"))
    avail_with_raw = fields.get("41A", fields.get("41D", "N/A"))
    avail_with = clean_text(avail_with_raw)
    confirm_inst = fields.get("49", "WITHOUT")  # CONFIRM / WITHOUT / MAY ADD
    charge_clause = fields.get("71B", "")
    # 从 41A 或 78 中提取通知行/议付行信息
    advising_bank = avail_with

    # ── 交单期 ──
    presentation_period = fields.get("48", "")
    if not presentation_period:
        presentation_period = "21 DAYS AFTER B/L DATE（默认）"

    # ── 汇票条款（增强） ──
    draft_info = parse_draft_requirements(fields)

    # ── 单据要求 46A（增强） ──
    docs_required = fields.get("46A", "")
    doc_requirements = parse_doc_list(docs_required)

    # ── 附加条件 47A（增强） ──
    add_conditions_raw = fields.get("47A", "")
    additional_conditions = parse_additional_conditions(add_conditions_raw)

    # ── 异常检测 ──
    anomalies = detect_anomalies(fields)

    # ── 效期地点解析（31D 格式: YYMMDD[PLACE]） ──
    # 31D 的标准格式是日期(6位)后面紧跟地点，无分隔符
    # 例如 "260610HONG KONG" -> date=260610, place="HONG KONG"
    # 某些格式可能包含 "/" 分隔，如 "260610/HONG KONG"
    expiry_place = ""
    expiry_date_only = ""
    if expiry_raw and expiry_raw != "N/A":
        # 先尝试按 "/" 分割
        if "/" in expiry_raw:
            parts = expiry_raw.split("/")
            expiry_date_only = parts[0].strip() if parts else ""
            expiry_place = parts[-1].strip() if len(parts) > 1 else ""
        else:
            # 无分隔符：提取开头的6位数字作为日期，剩余部分作为地点
            dm = re.match(r'^(\d{6})\s*(.+)$', expiry_raw.strip())
            if dm:
                expiry_date_only = dm.group(1)
                expiry_place = dm.group(2).strip()
            else:
                # 如果没有地点后缀，整串可能是纯日期
                if re.match(r'^\d{6}$', expiry_raw.strip()):
                    expiry_date_only = expiry_raw.strip()
                    expiry_place = ""
                else:
                    # 无法解析，整串作为地点
                    expiry_place = expiry_raw.strip()
    
    # 如果没解析到地点但有完整原始值，做最后尝试
    if not expiry_place and expiry_raw and expiry_raw != "N/A":
        # 可能是纯地点（某些银行只写地点不写日期）
        if not re.match(r'^\d{6}', expiry_raw.strip()):
            expiry_place = expiry_raw.strip()

    # ── 71B 费用条款 ──
    charges_info = {
        "raw": charge_clause,
        "for_beneficiary": bool(re.search(r'BENEFICIARY', charge_clause.upper())),
        "for_applicant": bool(re.search(r'APPLICANT', charge_clause.upper())),
        "all_outside": bool(re.search(r'OUTSIDE', charge_clause.upper())),
        "notes": [],
    }
    if charge_clause:
        if charges_info["all_outside"]:
            charges_info["notes"].append("开证行所在地以外的银行费用由受益人承担")
        if re.search(r'ISSUING\s+BANK', charge_clause.upper()):
            charges_info["notes"].append("开证行费用由申请人承担")

    return {
        "lc_no": lc_no,
        "amount": amount,
        "currency": amount.split()[0] if " " in amount else "USD",
        "expiry_date": expiry_raw,
        "expiry_place": expiry_place,
        "issue_date": issue_date,
        "applicant": applicant,
        "beneficiary": beneficiary,
        "issuing_bank": issuing_bank,
        "advising_bank": advising_bank,
        "latest_shipment": latest_ship,
        "port_loading": port_load,
        "port_discharge": port_disc,
        "goods_description": goods_desc[:1200],
        "form_of_lc": form_of_lc,
        "available_with": avail_with,
        "confirmation": confirm_inst,
        "presentation_period": presentation_period,
        "charges": charges_info,

        # 增强模块
        "draft": draft_info,
        "doc_requirements": doc_requirements,
        "additional_conditions": additional_conditions,
        "anomalies": anomalies,

        # 原始数据保留（供报告生成器使用）
        "raw_fields": fields,
        "clauses": fields,  # 完整的 MT700 字段字典，报告需要逐字段展示
    }
