# -*- coding: utf-8 -*-
"""
LC Audit Report Builder - 理想模板版 (Ideal Template Format v4.0)

基于 ReportLab 生成 PDF，严格按照理想审核报告模板的8章节结构生成。

章节结构:
1. 信用证基本信息 / Basic Information（含SWIFT字段号 + 关键时间节点计算）
2. 货物描述 (45A Description of Goods)
3. 单据要求 (46A Documents Required) - 逐单据展开含47A附加要求汇总
4. 附加条件要点 (47A Key Additional Conditions) - 分类展示
5. 条款异常分析 / Clause Anomaly Review - 5列表格
6. 风险矩阵 / Risk Matrix - 4列表格
7. 交单备查清单 / Compliance Checklist - 按单据分组checkbox
8. 审核总结与建议 / Summary & Recommendations
"""

import os
import re
import textwrap
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, ListFlowable, ListItem, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =============================================================================
# 字体注册（中文支持）
# =============================================================================

def _register_fonts():
    """注册中文字体 — 优先使用项目内嵌字体，确保 Linux 云端环境可用"""
    import sys

    # 项目内嵌字体目录（相对于 utils/ 的上级）
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _embedded_dir = os.path.join(_base_dir, "static", "fonts")

    font_paths = [
        # === 优先级1：项目内嵌字体（跨平台保证）===
        (os.path.join(_embedded_dir, "simhei.ttf"), "SimHei", 0),
        (os.path.join(_embedded_dir, "msyh.ttc"), "msyh", 0),
        (os.path.join(_embedded_dir, "simsun.ttc"), "simsun", 1),
        # === 优先级2：Windows 系统字体 ===
        ("C:/Windows/Fonts/msyh.ttc", "msyh_win", 0),
        ("C:/Windows/Fonts/simhei.ttf", "SimHei_win", 0),
        # === 优先级3：Linux 系统字体 ===
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "wqy", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "noto", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "dejavu", 0),  # 最后兜底
        # === 优先级4：macOS 系统字体 ===
        ("/System/Library/Fonts/PingFang.ttc", "PingFang", 0),
        ("/Library/Fonts/Arial Unicode.ttf", "ArialUni", 0),
    ]

    registered = False
    registered_names = []
    for path, name, index in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
                registered = True
                registered_names.append(name)
            except Exception as e:
                print(f"[LC Audit] Font register warning: {name} ({path}): {e}")
                continue

    if not registered:
        print("[LC Audit] WARNING: No CJK font found! Chinese characters will render as squares.")

    return registered, registered_names

_registered_result = _register_fonts()
_registered = _registered_result[0] if isinstance(_registered_result, tuple) else _registered_result

def get_font_name():
    """获取可用中文字体名称"""
    # 按优先级顺序查找已注册的中文字体
    candidates = ["SimHei", "msyh", "SimHei_win", "msyh_win", "simsun",
                  "wqy", "noto", "PingFang", "ArialUni"]
    for f in candidates:
        try:
            pdfmetrics.getFont(f)
            return f
        except Exception:
            continue
    print("[LC Audit] WARNING: Falling back to Helvetica — Chinese will NOT render!")
    return "Helvetica"  # 最终兜底（中文会显示为方块）

FONT = get_font_name()
FONT_BOLD = FONT  # 粗体用同一个字体


# =============================================================================
# 颜色方案（专业蓝色调）
# =============================================================================

class C:
    """颜色常量"""
    NAVY       = "#1B2A4A"      # 深海军蓝 - 主标题
    BLUE       = "#2563EB"      # 主蓝色 - 章节标题
    LIGHT_BLUE = "#DBEAFE"      # 浅蓝背景 - 信息框
    DGREY      = "#374151"      # 深灰 - 正文
    GREY       = "#6B7280"      # 中灰 - 标签/次要文字
    LGREY      = "#F3F4F6"      # 浅灰背景 - 斑马纹表格
    WHITE      = "#FFFFFF"
    RED_BD     = "#DC2626"      # 红色边框 - 严重/FAIL
    RED_BG     = "#FEE2E2"      # 红色背景
    AMBER_BD   = "#D97706"      # 琥珀色边框 - 警告/WARN
    AMBER_BG   = "#FEF3C7"      # 琥珀色背景
    GREEN_BD   = "#059669"      # 绿色边框 - 通过/PASS
    GREEN_BG   = "#ECFDF5"      # 绿色背景
    BORDER     = "#E5E7EB"


def hex_color(s):
    return colors.HexColor(s)


# =============================================================================
# 辅助函数
# =============================================================================

def P(name, **kw):
    """快捷创建段落样式"""
    kw["fontName"] = kw.get("fontName", FONT)
    return ParagraphStyle(name, **kw)


def make_styles():
    """创建所有样式"""
    S = {}
    # 标题样式
    S["title"]       = P("title", fontSize=20, leading=26, textColor=hex_color(C.NAVY), alignment=TA_CENTER, spaceAfter=2, fontName=FONT_BOLD)
    S["subtitle"]    = P("sub", fontSize=12, leading=16, textColor=hex_color(C.GREY), alignment=TA_CENTER, spaceAfter=4)
    S["h1"]          = P("h1", fontSize=14, leading=18, textColor=hex_color(C.BLUE), spaceBefore=10, spaceAfter=4, fontName=FONT_BOLD)
    S["h2"]          = P("h2", fontSize=11, leading=15, textColor=hex_color(C.NAVY), spaceBefore=6, spaceAfter=3, fontName=FONT_BOLD)

    # 正文样式
    S["body"]        = P("body", fontSize=9, leading=14, textColor=hex_color(C.DGREY), spaceAfter=2, alignment=TA_JUSTIFY, wordWrap="CJK")
    S["bl"]          = P("bl", fontSize=9, leading=14, textColor=hex_color(C.DGREY), spaceAfter=2, wordWrap="CJK")
    S["small"]       = P("small", fontSize=8, leading=12, textColor=hex_color(C.GREY), spaceAfter=1, wordWrap="CJK")
    S["label"]       = P("label", fontSize=9, leading=14, textColor=hex_color(C.GREY), wordWrap="CJK")
    S["value"]       = P("value", fontSize=9.5, leading=15, textColor=hex_color(C.DGREY), wordWrap="CJK")

    # 表格样式
    S["th"]          = P("th", fontSize=9, leading=14, textColor=hex_color(C.WHITE), alignment=TA_CENTER, fontName=FONT_BOLD, wordWrap="CJK")
    S["tc"]          = P("tc", fontSize=9, leading=14, textColor=hex_color(C.DGREY), wordWrap="CJK")

    # 风险等级专用
    S["risk_high"]   = P("risk_h", fontSize=9, leading=14, textColor=hex_color("#991B1B"), fontName=FONT_BOLD)
    S["risk_med"]    = P("risk_m", fontSize=9, leading=14, textColor=hex_color("#92400E"), fontName=FONT_BOLD)
    S["risk_low"]    = P("risk_l", fontSize=9, leading=14, textColor=hex_color("#065F46"))
    S["note_title"]  = P("nt", fontSize=9, leading=14, fontName=FONT_BOLD)
    S["note_body"]   = P("nb", fontSize=9, leading=14)

    # 条款显示
    S["clause_tag"]  = P("ctag", fontSize=8.5, leading=13, textColor=hex_color(C.WHITE), alignment=TA_CENTER, fontName=FONT_BOLD)
    S["clause_text"] = P("ctext", fontSize=9.5, leading=15, textColor=hex_color(C.DGREY), leftIndent=4*mm, wordWrap="CJK")

    return S


def tag_cell(text, bg=C.BLUE, text_color=C.WHITE):
    """带背景色的标签单元格（使用Table wrapper确保背景色正确渲染）"""
    styles = make_styles()
    inner = Paragraph(str(text), styles["clause_tag"])
    tbl = Table([[inner]], colWidths=[26*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), hex_color(bg)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def info_tbl(data, col_widths=None):
    """键值对信息表"""
    styles = make_styles()
    rows = []
    for k, v in data:
        rows.append([
            Paragraph(f"<b>{k}</b>", styles["label"]),
            Paragraph(str(v) if v else "<i>未提供</i>", styles["value"])
        ])
    cw = col_widths or [32*mm, 130*mm]
    t = Table(rows, colWidths=cw)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, 0), (0, -1), hex_color(C.LGREY)),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [hex_color(C.WHITE), hex_color(C.LGREY)]),
        ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
    ]))
    return t


def risk_table(anomalies):
    """异常/风险列表表格（通用版，用于条款异常分析和风险矩阵）"""
    styles = make_styles()
    severity_map = {
        "high": ("高风险", C.RED_BD, C.RED_BG, "risk_high"),
        "medium": ("中等风险", C.AMBER_BD, C.AMBER_BG, "risk_med"),
        "low": ("低风险", C.GREEN_BD, C.GREEN_BG, "risk_low"),
        "严重": ("严重", C.RED_BD, C.RED_BG, "risk_high"),
        "警告": ("警告", C.AMBER_BD, C.AMBER_BG, "risk_med"),
        "提示": ("提示", C.GREEN_BD, C.GREEN_BG, "risk_low"),
        "critical": ("严重", C.RED_BD, C.RED_BG, "risk_high"),
        "warning": ("警告", C.AMBER_BD, C.AMBER_BG, "risk_med"),
        "info": ("提示", C.GREEN_BD, C.GREEN_BG, "risk_low"),
    }

    rows = [[
        Paragraph("<b>风险级别</b>", styles["th"]),
        Paragraph("<b>类型</b>", styles["th"]),
        Paragraph("<b>详细说明</b>", styles["th"]),
        Paragraph("<b>条款号</b>", styles["th"]),
    ]]

    for a in anomalies:
        sev_label, bd_col, bg_col, style_name = severity_map.get(
            a.get("severity", a.get("严重程度", "")),
            ("未知", C.GREY, C.LGREY, "body")
        )
        sev_text = a.get("severity", a.get("严重程度", ""))
        atype = a.get("type", a.get("类型", ""))
        detail = a.get("detail", a.get("详细说明", ""))
        clause = a.get("clause_ref", a.get("条款号", "-"))

        rows.append([
            tag_cell(sev_label, bd_col, C.WHITE),
            Paragraph(atype, styles[style_name]),
            Paragraph(_esc(detail), styles["body"]),
            Paragraph(clause, styles["tc"]),
        ])

    t = Table(rows, colWidths=[22*mm, 24*mm, 100*mm, 18*mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), hex_color(C.NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), hex_color(C.WHITE)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [hex_color(C.WHITE), hex_color(C.LGREY)]),
        ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.NAVY)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def box_para(para_obj, bg=None, border=None):
    """带背景框的段落容器"""
    if bg is None: bg = C.LIGHT_BLUE
    if border is None: border = C.BLUE
    tbl = Table([[para_obj]], colWidths=["100%"])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), hex_color(bg)),
        ("BOX", (0, 0), (-1, -1), 0.8, hex_color(border)),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return tbl


def note_box(title, body_text, level="info"):
    """提示框（用于风险提醒、注意事项等）"""
    styles = make_styles()
    config = {
        "warning": {"bg": C.AMBER_BG, "bd": C.AMBER_BD, "icon": "[!] 注意"},
        "danger":  {"bg": C.RED_BG,   "bd": C.RED_BD,   "icon": "[X] 严重"},
        "info":    {"bg": C.LIGHT_BLUE, "bd": C.BLUE,     "icon": "[i] 提示"},
        "success": {"bg": C.GREEN_BG, "bd": C.GREEN_BD,  "icon": "[OK] 通过"},
    }
    cfg = config.get(level, config["info"])
    content = Paragraph(
        f"<b>{cfg['icon']} {title}</b><br/>{_esc(body_text)}",
        styles["body"]
    )
    return box_para(content, cfg["bg"], cfg["bd"])


def _esc(s):
    """转义 XML 特殊字符"""
    if s is None:
        return ""
    s = str(s).replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    return s


def _clean_lc_colons(text):
    """清理信用证文本中无意义的 SWIFT 冒号分隔符
    
    MT700 报文中使用 ':' 作为字段/子字段分隔符，
    在报告中显示为连续的 '::::' 或 ': ' 等无意义格式。
    此函数将多余的冒号清理为可读格式：
    - '::' 或 ':::' → 换行或空格
    - 行首/行尾多余冒号去除
    - 连续空格压缩
    """
    if not text:
        return ""
    t = str(text)
    # 多个连续冒号 → 换行（SWIFT 子段分隔）
    t = re.sub(r':{2,}', '\n', t)
    # 单独的冒号后跟空格但前面无文字（行首残留）→ 去掉
    t = re.sub(r'^\s*:\s*', '', t, flags=re.MULTILINE)
    # 行尾单独冒号 → 去掉
    t = re.sub(r'\s*:\s*$', '', t, flags=re.MULTILINE)
    # 多个连续空格 → 单个空格
    t = re.sub(r'  +', ' ', t)
    # 多个连续换行 → 最多2个
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def _fmt_amount(amt_str):
    """格式化金额显示"""
    if not amt_str:
        return "-"
    amt_str = str(amt_str).strip().rstrip(",")
    m = re.match(r'([A-Z]{3})\s*([\d,]+\.?\d*)', amt_str, re.I)
    if m:
        cur, num = m.groups()
        try:
            val = float(num.replace(",", ""))
            return f"{cur} {val:,.2f}"
        except ValueError:
            return amt_str
    return amt_str


def _translate_clause(tag, value):
    """将 SWIFT MT700 字段标签翻译为中文"""
    tag_map = {
        "27": "合同序列",
        "40A": "信用证形式",
        "20":  "信用证编号",
        "23": "参考号",
        "31C": "开证日期",
        "31D": "到期日/地",
        "50":  "申请人",
        "59": "受益人",
        "32B": "金额货币",
        "41A": "付款方式",
        "42C": "汇票期限",
        "42A": "汇票付款人",
        "42M": "混付条款",
        "42P": "代付款节",
        "43P": "分批装运",
        "43T": "转运运输",
        "44E": "装船港/发货地",
        "44F": "卸货港/目的地",
        "44C": "最迟装船日",
        "44D": "分批装运",
        "45A": "货物描述",
        "46A": "单据要求",
        "47A": "附加条款",
        "48": "提交期限",
        "49": "说明",
        "51A": "开证行",
        "57A": "通知行",
        "71B": "费用承担",
        "72": "付款指示",
        "78": "指示向银行",
        "Oth": "其他信息",
    }
    label = tag_map.get(tag, f"条款{tag}")
    return label, value or "(未提供)"


def _check_needs_draft(clause_42c, clause_42a, clause_42m, clause_46a_text, clause_47a_text):
    """
    判断信用证是否要求提交汇票。
    返回：(needs_draft, reason_list)
    """
    reasons = []
    needs_draft = False

    if clause_42c and clause_42c.strip():
        needs_draft = True
        reasons.append(f"42C条款规定汇票期限：{_esc(clause_42c.strip())}")

    if clause_42a and clause_42a.strip():
        needs_draft = True
        reasons.append(f"42A条款指定付款人：{_esc(clause_42a.strip())}")

    if clause_42m and clause_42m.strip():
        needs_draft = True
        reasons.append(f"42M混付条款：{_esc(clause_42m.strip())}")

    combined_doc_text = ""
    if clause_46a_text:
        combined_doc_text += " " + clause_46a_text
    if clause_47a_text:
        combined_doc_text += " " + clause_47a_text

    if combined_doc_text:
        draft_patterns = re.findall(
            r'(draft|bill\s+of\s+exchange|exchange\s+for|sight\d*draft|time\d*draft|usance)',
            combined_doc_text,
            re.IGNORECASE
        )
        if draft_patterns and not needs_draft:
            needs_draft = True
            reasons.append("单据要求(或附加条件)中提到汇票(draft/bill of exchange)")

        no_draft_patterns = re.search(
            r'(no\s*draft|without\s*draft|draft\s*not\s*(required)?\s*necessary)',
            combined_doc_text,
            re.IGNORECASE
        )
        if no_draft_patterns:
            needs_draft = False
            reasons = ["明确规定不需提交汇票"]

    return needs_draft, reasons


def _lc_form_cn(form_val):
    """翻译信用证形式为中文"""
    if not form_val:
        return "-"
    form_upper = str(form_val).upper().strip()
    mapping = {
        "IRREVOCABLE": "不可撤销",
        "REVOCABLE": "可撤销",
        "IRREVOCABLE CONFIRMED": "不可撤销保兑",
        "IRREVOCABLE TRANSFERABLE": "不可撤销可转让",
        "CONFIRMED": "保兑",
        "TRANSFERABLE": "可转让",
    }
    for k, v in mapping.items():
        if k in form_upper:
            return v
    return form_val


def _wrap_long(text, max_len=200):
    """截断过长文本"""
    if not text:
        return ""
    t = str(text).strip()
    if len(t) > max_len:
        return t[:max_len] + "..."
    return t


def _days_between(date_str1, date_str2):
    """计算两个日期之间的天数（支持多种格式）"""
    try:
        from dateutil.parser import parse as _dp
        d1 = _dp(date_str1, fuzzy=True)
        d2 = _dp(date_str2, fuzzy=True)
        return (d2 - d1).days
    except Exception:
        # 尝试 YYMMDD 格式
        try:
            from datetime import date as _d
            def _parse_yymmdd(s):
                s = s.strip().replace("/", "")[:6]
                return _d(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))
            return (_parse_yymmdd(date_str2) - _parse_yymmdd(date_str1)).days
        except Exception:
            return None


def summarize_checks(check_results):
    """汇总检查结果统计"""
    total = len(check_results)
    passed = sum(1 for r in check_results if r.get("status") == "PASS")
    warned = sum(1 for r in check_results if r.get("status") == "WARN")
    failed = sum(1 for r in check_results if r.get("status") == "FAIL")
    return {"total": total, "passed": passed, "warned": warned, "failed": failed}


def _doc_type_cn(doc_type_en):
    """单据类型英文->中文"""
    mapping = {
        "commercial invoice": "商业发票",
        "invoice": "发票",
        "packing list": "装箱单",
        "bill of lading": "提单",
        "b/l": "提单",
        "awb": "航空运单",
        "airway bill": "航空运单",
        "certificate of origin": "原产地证",
        "origin": "原产地证",
        "insurance": "保险单/凭证",
        "insurance policy": "保险单",
        "certificate": "证书",
        "draft": "汇票",
        "bill of exchange": "汇票",
        "quality certificate": "质量证书",
        "weight list": "重量单",
        "inspection certificate": "检验证书",
        "beneficiary cert": "受益人证明",
        "beneficiary statement": "受益人声明",
        "courier receipt": "快递收据",
        "fax report": "传真报告",
        "shipping advice": "装船通知",
        "analysis certificate": "分析证书",
    }
    dt_lower = doc_type_en.lower().strip()
    for k, v in mapping.items():
        if k in dt_lower:
            return v
    return doc_type_en


def _detect_soft_clauses(clauses):
    """检测可能的软条款"""
    soft_indicators = [
        (r'(inspection\s+certificate.*issued\s+by\s+(the\s+)?applicant)', '申请人签发检验证书——受益人无法控制'),
        (r'(applicant\s+must\s+(certify|confirm|approve))', '申请人必须确认/批准——主观条款风险'),
        (r'(copy\s+of\s+fax\s+.*\s+(approval|acceptance))', '传真确认单——受益人无法控制确认时间'),
        (r'(documents?\s+released?\s+(against\s+)?undertaking)', '担保放单——工作音诉风险'),
        (r"(beneficiary's\s+declaration.*to\s+the\s+satisfaction\s+of)", '致申请人满意——主观标准'),
        (r'(clean\s+on\s+board.*(?:bearing|showing|indicating).*(?:the\s+)?(?:date|vessel))', '提单中具体要求过于详细——增加不符点风险'),
    ]

    found = []
    all_clause_text = " ".join(str(v) for v in clauses.values())
    for pattern, description in soft_indicators:
        if re.search(pattern, all_clause_text, re.IGNORECASE):
            found.append(description)
    return found


# =============================================================================
# 报告 1：信用证条款审核报告（LC Review Report）— 8章节理想模板版
# =============================================================================

# ---------- 新增辅助函数 ----------


def _short_name(party_text, max_len=60):
    """提取当事人简称（取第一行或逗号前部分）"""
    if not party_text:
        return ""
    text = str(party_text).strip()
    # 取第一行
    first_line = text.split("\n")[0].strip()
    # 如果有逗号分隔的公司名，取第一个逗号前的部分
    if "," in first_line[:max_len]:
        return first_line.split(",")[0].strip()[:max_len]
    return first_line[:max_len]


def _format_date_yymmdd(date_raw):
    """尝试将各种日期格式统一为 YYYY-MM-DD 显示"""
    if not date_raw:
        return "-"
    s = str(date_raw).strip()
    # 已经是长格式
    if "-" in s and len(s) >= 10:
        return s
    # YYMMDD 格式
    m = re.match(r'^(\d{2})(\d{2})(\d{2})', s)
    if m:
        y, mo, d = m.groups()
        return f"20{y}-{mo}-{d}"
    return s


def _extract_amount_number(amount_str):
    """从金额字符串中提取纯数字"""
    if not amount_str:
        return 0.0
    m = re.search(r'[\d,]+\.?\d*', str(amount_str))
    if m:
        try:
            return float(m.group().replace(",", ""))
        except ValueError:
            return 0.0
    return 0.0


def _extract_currency(amount_str):
    """从金额字符串中提取货币代码"""
    if not amount_str:
        return ""
    m = re.match(r'([A-Z]{3})', str(amount_str).strip(), re.I)
    return m.group(1).upper() if m else ""


def _get_tolerance(clauses):
    """
    从 39A 或 39B 提取金额容差百分比。
    返回 (tolerance_pct, source_field) 元组，如 (5, "39A") 或 (0, None)
    """
    tolerance_39a = clauses.get("39A", "").strip()
    tolerance_39b = clauses.get("39B", "").strip()

    if tolerance_39b and tolerance_39b.upper() == "EXCLUDING":
        return (0, "39B(EXCLUDING)")

    if tolerance_39a:
        # 常见格式: "05/05", "10/10", "03/03"
        tm = re.match(r'(\d+)\s*/\s*(\d+)', tolerance_39a)
        if tm:
            pct = int(tm.group(1))
            return (pct, f"39A({pct}%)")

    return (None, None)


def _calc_tolerance_amount(amount_str, tolerance_pct):
    """基于容差百分比计算可接受的最大/最小金额"""
    base = _extract_amount_number(amount_str)
    currency = _extract_currency(amount_str)
    if tolerance_pct is None or base == 0:
        return currency, base, base
    delta = round(base * tolerance_pct / 100, 2)
    return currency, round(base - delta, 2), round(base + delta, 2)


def _bf(bold_text, normal_text=""):
    """快捷加粗：返回 <b>bold</b>normal 格式"""
    if normal_text:
        return f"<b>{bold_text}</b>{normal_text}"
    return f"<b>{bold_text}</b>"


def _translate_partial(val):
    """翻译分批装运条款"""
    if not val:
        return "-"
    u = str(val).upper().strip()
    if "ALLOWED" in u or "PERMITTED" in u:
        return "ALLOWED (允许)"
    elif "PROHIBITED" in u or "NOT ALLOWED" in u:
        return "PROHIBITED (禁止)"
    elif "CONDITIONAL" in u:
        return "CONDITIONAL (有条件允许)"
    return val


def _translate_tranship(val):
    """翻译转运条款"""
    if not val:
        return "-"
    u = str(val).upper().strip()
    if "ALLOWED" in u or "PERMITTED" in u:
        return "ALLOWED (允许)"
    elif "PROHIBITED" in u or "NOT ALLOWED" in u:
        return "PROHIBITED (禁止)"
    return val


def _translate_confirm(form_val):
    """翻译保兑状态（从 40A/40B 推断，兼容旧逻辑）"""
    if not form_val:
        return "-"
    u = str(form_val).upper()
    if "CONFIRM" in u:
        return "CONFIRMED (已保兑)"
    if "MAY ADD" in u:
        return "MAY ADD (可加保兑)"
    return "WITHOUT (未保兑)"


def _translate_confirm_49(confirm_49):
    """翻译保兑状态（从 49 字段直接取值 — 标准做法）"""
    if not confirm_49 or not confirm_49.strip():
        return "- (未注明)"
    u = str(confirm_49).upper().strip()
    if "CONFIRM" in u:
        return "CONFIRMED (已保兑)"
    if "MAY ADD" in u or "MAYADD" in u:
        return "MAY ADD (可加保兑)"
    if "WITHOUT" in u:
        return "WITHOUT (不加保兑)"
    # 如果值不匹配已知模式，原样返回
    return str(confirm_49).strip()


def _basic_info_table(analysis, clauses):
    """构建第一章基本信息的两列表格数据
    
    按照理想模板格式：
    - 信用证号码优先显示为(21)，因为:21才是 Documentary Credit Number
      :20 是 Sender's Reference（银行内部参考号）
    - 到期日和到期地点从 31D 字段中分离：格式通常为 "YYMMDDPLACE" 
      例如 "260610HONG KONG" -> 到期日=2026-06-10, 到期地=HONG KONG
    - 信用证形式优先取 40B（新版MT700），其次取 40A
    - 保兑状态从字段 49 取值（CONFIRM / WITHOUT / MAY ADD）
    """
    amount_str = analysis.get("amount") or clauses.get("32B", "")
    
    # ---- LC 号码标签：优先用 :21（真正的Documentary Credit Number） ----
    lc_no = analysis.get("lc_no") or "-"
    lc_tag = "(21)" if clauses.get("21") else ("(20)" if clauses.get("20") else "")
    lc_label = f"信用证号码 ({lc_tag})" if lc_tag else "信用证号码"
    
    # ---- 到期日/地分离：31D 格式通常是 YYMMDD + 地点（无分隔符） ----
    expiry_raw = clauses.get("31D", "") or analysis.get("expiry_date", "")
    expiry_date_display = "-"
    expiry_place_display = analysis.get("expiry_place") or "-"
    
    if expiry_raw:
        # 尝试提取日期部分 (6位数字)
        dm = re.search(r'(\d{6})', str(expiry_raw))
        if dm:
            expiry_date_display = _format_date_yymmdd(dm.group(1)) or dm.group(1)
            # 日期后面的部分就是地点
            after_date = expiry_raw[dm.end():].strip()
            if after_date:
                expiry_place_display = after_date
    
    # ---- 信用证形式：优先 40B，其次 40A ----
    form_val = clauses.get("40B", "") or clauses.get("40A", "")
    form_tag = "40B" if clauses.get("40B") else ("40A" if clauses.get("40A") else "")
    form_label = f"信用证形式 ({form_tag})" if form_tag else "信用证形式"
    
    # ---- 保兑状态：从 49 字段取值 ----
    confirm_val = clauses.get("49", "")
    
    rows = [
        (_bf(lc_label), lc_no),
        (_bf("开证日期 (31C)"), _format_date_yymmdd(analysis.get("issue_date")) or clauses.get("31C", "-")),
        (_bf("到期日 (31D)"), expiry_date_display),
        (_bf("到期地点"), expiry_place_display),
        (_bf("开证行 (51A)"), analysis.get("issuing_bank") or "-"),
        (_bf("通知行 (57A)"), analysis.get("advising_bank") or "-"),
        (_bf("付款方式 (41A)"), clauses.get("41A", "-")),
        (_bf(form_label), _lc_form_cn(form_val)),
        (_bf("保兑状态 (49)"), _translate_confirm_49(confirm_val)),
        (_bf("金额 (32B)"), _fmt_amount(amount_str)),
        (_bf("申请人 (50)"), _wrap_long(analysis.get("applicant"), 300)),
        (_bf("受益人 (59)"), _wrap_long(analysis.get("beneficiary"), 300)),
    ]
    return rows


def _build_key_dates_box(story, S, clauses, analysis):
    """在第一章末尾添加关键时间节点信息框"""
    lines = []

    # 开证日期
    issue_d = analysis.get("issue_date") or clauses.get("31C", "")
    if issue_d:
        lines.append(_bf("开证日期: ") + _format_date_yymmdd(issue_d))

    # 到期日期
    exp_d = analysis.get("expiry_date") or ""
    exp_m = re.search(r'(\d{6})', str(exp_d)) if exp_d else None
    if exp_m:
        lines.append(_bf("到期日期: ") + _format_date_yymmdd(exp_d))

    # 最迟装船日
    ship_raw = clauses.get("44C", "")
    ship_m = re.search(r'(\d{6})', ship_raw) if ship_raw else None
    if ship_m:
        ss = ship_m.group(1)
        lines.append(_bf("最迟装船日 (44C): ") + _format_date_yymmdd(ss))

    # 交单期
    pres_raw = clauses.get("48", "")
    if pres_raw:
        pm = re.search(r'(\d+)\s*DAYS?', pres_raw, re.I)
        if pm:
            days = int(pm.group(1))
            lines.append(_bf("交单期限 (48): ") + f"提单日后 {days} 天")
            # 计算理论最晚交单日
            if ship_m and exp_m:
                try:
                    from datetime import date as _d
                    ship_dt = _d(2000+int(ss[:2]), int(ss[2:4]), int(ss[4:6]))
                    latest_pres = _d(ship_dt.year, ship_dt.month, ship_dt.day)
                    # 加上交单期天数
                    from datetime import timedelta as _td
                    calc_due = latest_pres + _td(days=days)
                    es = re.search(r'(\d{6})', str(exp_d))
                    if es:
                        exp_dt = _d(2000+int(es.group(1)[:2]), int(es.group(1)[2:4]), int(es.group(1)[4:6]))
                        effective = min(calc_due, exp_dt)
                        lines.append(_bf("实际交单截止日: ") + effective.strftime("%Y-%m-%d") +
                                     f" (min(提单日+{days}天, 到期日))")
                except Exception:
                    pass

    # 分批/转运
    partial = clauses.get("43P", "")
    tranship = clauses.get("43T", "")
    if partial:
        lines.append(_bf("分批装运 (43P): ") + _translate_partial(partial))
    if tranship:
        lines.append(_bf("转运 (43T): ") + _translate_tranship(tranship))

    # 溢短装
    tol_pct, tol_src = _get_tolerance(clauses)
    if tol_pct is not None:
        amt_str = analysis.get("amount") or clauses.get("32B", "")
        cur, lo, hi = _calc_tolerance_amount(amt_str, tol_pct)
        lines.append(_bf("溢短装容差: ") + f"+/- {tol_pct}% ({tol_src}), 可接受金额范围: {cur} {lo:,.2f} ~ {cur} {hi:,.2f}")

    if lines:
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(_bf("关键时间节点与运输参数"), S["h2"]))
        content = Paragraph("<br/>".join(lines), S["body"])
        story.append(box_para(content, C.LIGHT_BLUE, C.BLUE))


# ---------- 第一章：基本信息 ----------

def _build_chapter1_basic_info(story, S, analysis, clauses):
    """第一章：信用证基本信息 — 含SWIFT字段号标注 + 关键时间节点"""
    story.append(Paragraph("一、信用证基本信息 / Basic Information", S["h1"]))

    # 基本信息表（带SWIFT字段号）
    basic_data = _basic_info_table(analysis, clauses)
    story.append(info_tbl(basic_data, col_widths=[34*mm, 128*mm]))

    # 关键时间节点信息框
    _build_key_dates_box(story, S, clauses, analysis)


# ---------- 第二章：货物描述 ----------

def _build_chapter2_goods_desc(story, S, analysis, clauses):
    """第二章：货物描述 (45A Description of Goods)"""
    story.append(Paragraph("二、货物描述 / Description of Goods (45A)", S["h1"]))

    goods_45a = clauses.get("45A", "").strip()
    if not goods_45a:
        story.append(note_box("无货物描述", "本信用证未包含45A货物描述字段。", "info"))
        return

    # 原文展示
    story.append(Paragraph(_bf("货物描述原文 (Field 45A):"), S["h2"]))

    # 清理格式但保留结构
    display = goods_45a
    display = re.sub(r'\s*\.\s*:\s*', '\n  ', display)
    display = re.sub(r'\n\s*\n', '\n', display)

    story.append(box_para(Paragraph(_esc(display), S["body"]), C.WHITE, C.BORDER))

    # 货描一致性备注
    story.append(Spacer(1, 2*mm))
    story.append(note_box(
        "[i] 货物描述核对提醒",
        "商业发票和装箱单中的品名、规格、数量、单价、金额必须与45A货描完全一致。"
        "HS编码、型号/SKU、贸易术语(Incoterms)、计价单位(如PCS vs PC)等细节也需逐一核对。",
        "info"
    ))


# ---------- 第三章：单据要求 ----------


def _parse_doc_items(doc_text):
    """
    增强版单据文本解析器 — 按46A条目分割并提取每份单据的结构化字段。

    返回 list[dict]，每个元素包含:
      - type_cn: 单据中文名
      - type_en: 单据英文关键词
      - raw_content: 原始完整文本
      - copies: 份数描述 (如 "ORIGINAL PLUS 3 COPIES")
      - header: 抬头/签发方要求 (如 "ISSUED BY BENEFICIARY")
      - details: 详细要求列表
      - special_req: 特殊要求标记 (如 "SIGNED", "NOTIFIED", "IN ENGLISH")
    """
    if not doc_text or not doc_text.strip():
        return []

    # ---- 第一步：按条目分割 ----
    items_raw = []
    current = ""
    for line in doc_text.split("\n"):
        stripped = line.strip()
        # 新条目检测：数字开头如 "+ 1/" 或 "1." 或 "1)" 等
        if re.match(r'^[+]?\s*\d+[./)\-]', stripped) or \
           (re.match(r'^[A-Z][A-Z\s]{3,}', stripped) and current and not stripped.startswith("+")):
            if current.strip():
                items_raw.append(current.strip())
            current = stripped
        else:
            current += "\n" + line if current else line
    if current.strip():
        items_raw.append(current.strip())
    if not items_raw and doc_text.strip():
        items_raw = [doc_text.strip()]

    # ---- 第二步：对每个条目提取结构化字段 ----
    result = []
    for item_text in items_raw:
        fields = _extract_doc_fields(item_text)
        result.append(fields)

    return result


def _extract_doc_fields(item_text):
    """
    从单个单据条目文本中提取结构化字段。

    返回 dict:
      - type_cn / type_en / raw_content / copies / header /
        details (list[str]) / special_req (list[str])
    """
    text = item_text.strip()
    upper_t = text.upper()

    # --- 单据类型识别 ---
    type_cn = _doc_type_cn(text[:120])
    type_en = type_cn  # fallback，下面会尝试提取英文原名
    # 尝试提取英文原名（通常在句首）
    en_match = re.match(r'^([A-Z][A-Za-z\s/&]+?(?:LIST|CERTIFICATE|INVOICE|BILL|'
                        r'DRAFT|DECLARATION|STATEMENT|RECEIPT|REPORT|LICENSE|'
                        r'PERMIT|POLICY|AWB|BL|DOCUMENT))', text)
    if en_match:
        type_en = en_match.group(1).strip()

    # --- 提取份数 ---
    copies = _extract_copies(text)

    # --- 提取抬头/签发方 ---
    header = _extract_header(text)

    # --- 提取特殊要求标记 ---
    special_req = _extract_special_marks(text)

    # --- 提取详细要求（拆分为列表） ---
    details = _extract_detail_items(text)

    return {
        "type_cn": type_cn,
        "type_en": type_en,
        "raw_content": text,
        "copies": copies,
        "header": header,
        "details": details,
        "special_req": special_req,
    }


def _extract_copies(text):
    """从单据文本中提取份数要求
    
    增强版：支持更多格式
    - "3 ORIGINALS" -> "3 ORIGINALS"
    - "1 ORIGINAL + 1 COPY" -> "1 ORIGINAL + 1 COPY"  
    - "ORIGINAL PLUS 3 COPIES" -> "ORIGINAL PLUS 3 COPIES"
    - "FULL SET (3/3) ORIGINAL" -> "FULL SET (3/3) ORIGINAL"
    - "1 ORIGINAL SIGNED" -> "1 ORIGINAL SIGNED"
    """
    upper_t = text.upper()
    
    # ---- 优先级1：精确匹配完整份数模式 ----
    
    # Pattern: N ORIGINAL[S] [+/- N COPY/COPIES]
    m = re.search(r'(\d\s*ORIGINAL(?:S)?(?:\s*(?:SIGNED|UNSIGNED))?(?:\s*[\+\-]\s*\d*\s*(?:COPY|COPIES)(?:\s*[\+\-].*)?)?)', text, re.I)
    if m and len(m.group(1).strip()) > 2:
        return m.group(1).strip()
    
    # Pattern: FULL SET (N/N) ORIGINAL
    m = re.search(r'FULL\s+SET\s*\(\s*\d+\s*/\s*\d+\s*\)\s*(ORIGINAL|ORIGINALS)', text, re.I)
    if m:
        # 提取更完整的上下文
        m2 = re.search(r'(FULL\s+SET\s*\([^)]+\)\s*ORIGINALS?\b[^.]*)', text, re.I)
        if m2:
            return m2.group(1).strip().rstrip('.')
        return m.group(0).strip()
    
    # Pattern: ONE/1 ORIGINAL [PLUS ...]
    m = re.search(r'(?:ONE|1)\s+ORIGINAL(?:S)?(?:\s+(?:PLUS|AND)\s+.+)?', text, re.I)
    if m and len(m.group(0).strip()) > 8:
        return m.group(0).strip()
    
    # Pattern: N-FOLD / DUPLICATE / TRIPLICATE
    for pat_name in [r'\d[\-\+]?\s*-?FOLD', r'DUPLICATE', r'TRIPLICATE']:
        m = re.search(pat_name, text)
        if m:
            return m.group(0).strip()
    
    # ---- 优先级2：查找任何包含 ORIGINAL/COPY 的份数短语 ----
    
    # 查找 "N ORIGINAL(S)" 或 "N COPY(COPIES)"
    m = re.search(r'(\d+)\s*(ORIGINALS?|COPIES?)(?:\s|$|[,\)])', text, re.I)
    if m:
        num = m.group(1)
        doc_type = m.group(2)
        # 向前向后扩展以获取更完整的描述
        start = max(0, m.start() - 20)
        end = min(len(text), m.end() + 15)
        context = text[start:end].strip()
        # 清理开头可能的截断词
        context = re.sub(r'^\S+\s+', '', context)
        return context.rstrip('.,:;')
    
    # ---- 优先级3：fallback ----
    if 'ORIGINAL' in upper_t or 'COPY' in upper_t:
        cm = re.search(r'.{0,25}\bORIGINAL.{0,20}\b', text, re.I)
        if cm:
            return cm.group(0).strip()
        cm = re.search(r'.{0,10}\bCOPIE[S]?.{0,20}\b', text, re.I)
        if cm:
            return cm.group(0).strip()

    return "-"


def _extract_header(text):
    """从单据文本中提取抬头/签发方要求"""
    header_patterns = [
        r'(?:ISSUED|MADE\s+OUT|SIGNED|PREPARED)\s+(?:OUT\s+)?(?:BY|TO|AT)\s+(.+?)(?:\.|\n|$)',
        r'(?:INDICATING|SHOWING|STATING|BEARING|MARKED)\s+(.+?)(?:\.|\n|$)',
        r'ADDRESSED\s+TO\s+(.+?)(?:\.|\n|$)',
        r'BENEFICIAL?Y\'?S?\s+(.+?)(?:\.|\n|$)',
    ]
    for pat in header_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            h = m.group(1).strip()
            if len(h) > 3 and len(h) < 200:
                return h
    return "-"


def _extract_special_marks(text):
    """提取单据中的特殊要求标记
    
    增强版：对提单等运输单据提取更完整的关键信息（Notify/Consignee/Freight等）
    """
    marks = []
    
    # 基础标记
    mark_patterns = [
        ("须签字", r'\bSIGNED\b'),
        ("须公证", r'\bLEGALIZ(E|ED)|NOTARIZ(E|ED)\b'),
        ("须认证", r'\b(AUTHENTICATE|CONSULARIZE|ATTEST)\b'),
        ("须英文制作", r'\bIN\s+ENGLISH\b'),
        ("须单独寄送", r'\bSEPARATE\s+COURIER|MAIL(?:ED)?\s+DIRECTLY\b'),
        ("正本要求", r'\bORIGINAL\b'),
        ("副本要求", r'\bCOPIE?[SY]?\b'),
        ("须通知", r'\bNOTIF(Y|IED|ICATION)\b'),
        ("须证明/声明", r'\b(CERTIFY|DECLARE|STATE|CONFIRM)\s+THAT\b'),
    ]
    for label, pat in mark_patterns:
        if re.search(pat, text, re.IGNORECASE):
            marks.append(label)
    
    # ---- 提单特殊标记增强 ----
    upper_t = text.upper()
    
    if 'BILL OF LADING' in upper_t or 'B/L' in upper_t or 'TRANSPORT DOCUMENT' in upper_t:
        # Consignee 信息
        m = re.search(r'CONSIGNED?\s+(?:TO\s+)?(.{5,80}?)(?:NOTIF|MARKED|FREIGHT|::|\.)', text, re.I)
        if m:
            marks.append(f"Consignee: {m.group(1).strip()[:50]}")
        
        # Notify 方信息
        m = re.search(r'NOTIF[YIES]+[:\s]+(.{5,80}?)(?:MARKED|FREIGHT|::|\.|$)', text, re.I)
        if m:
            marks.append(f"Notify: {m.group(1).strip()[:50]}")
        
        # Freight 条款
        m = re.search(r'(?:MARKED|FREIGHT)[:\s]*(?:PAYABLE\s+)?(AT\s+(?:DESTINATION|PREPAID|COLLECT))', text, re.I)
        if m:
            marks.append(f"Freight: {m.group(1).strip()}")
        
        # Multimodal 可接受
        if re.search(r'MULTIMODAL', upper_t):
            marks.append("Multimodal acceptable")
        
        # Full Set
        if re.search(r'FULL\s+SET', upper_t):
            m = re.search(r'FULL\s+SET[^)]*\)', text, re.I)
            if m:
                marks.append(f"Full set: {m.group(0).strip()}")

    return marks


def _extract_detail_items(text):
    """将单据文本拆分为详细要求的列表"""
    # 先清理前导的编号
    cleaned = re.sub(r'^[+]\s*\d+[./)]\s*', '', text.strip())
    cleaned = re.sub(r'^\d+[.\)]\s*', '', cleaned)

    # 按分隔符拆分
    separators = [r'\.\s+', r';\s*', r'\n\s*(?=[A-Z])']
    items = []
    for sep in separators:
        parts = re.split(sep, cleaned)
        if len(parts) > 1:
            for p in parts:
                p_stripped = p.strip()
                if len(p_stripped) > 5:  # 过滤太短的片段
                    items.append(p_stripped)
            break  # 只用第一个成功拆分的模式

    if not items:
        # 整体作为一项
        items = [cleaned]

    # 截断过长的项目
    return [item[:300] for item in items[:10]]


def _doc_47a_notes(doc_fields, cond_47a):
    """
    增强版47A关联条件查找 — 基于单据类型关键词 + 内容语义匹配。
    参数 doc_fields 为 _extract_doc_fields 的返回值(dict)。
    返回 list[(label, snippet_text, relevance)]。
    """
    if not cond_47a or not doc_fields:
        return []

    doc_text = doc_fields.get("raw_content", "")
    type_en = doc_fields.get("type_en", "")
    type_cn = doc_fields.get("type_cn", "")

    related = []

    # 构建多级关键词匹配
    keywords_map = {
        # 商业发票
        "commercial invoice": ["COMMERCIAL INVOICE", "INVOICE VALUE", "INVOICE AMOUNT",
                               "INVOICE MUST", "ALL INVOICES"],
        "invoice": ["INVOICE", "COMMERCIAL"],
        # 装箱单/重量单
        "packing list": ["PACKING LIST", "WEIGHT LIST", "PACKING", "MEASUREMENT LIST"],
        # 提单/运输单据
        "bill of lading": ["BILL OF LADING", "B/L", "ON BOARD DATE", "TRANSPORT DOCUMENT",
                           "MULTIMODAL", "PORT OF LOADING", "PORT OF DISCHARGE"],
        # 航空运单
        "airway bill": ["AIRWAY BILL", "AWB", "AIR CARGO", "FLIGHT NO"],
        # 原产地证
        "certificate of origin": ["CERTIFICATE OF ORIGIN", "GSP FORM A", "ORIGIN CERTIFIED",
                                  "C.O.", "CERT OF ORIGIN"],
        # 保险
        "insurance policy": ["INSURANCE POLICY", "INSURANCE CERTIFICATE", "COVER NOTE",
                             "INSURANCE DOCUMENT", "INSURED VALUE"],
        # 汇票
        "draft": ["DRAFT", "BILL OF EXCHANGE", "EXCHANGE FOR", "USANCE DRAFT", "SIGHT DRAFT"],
        # 质量证书
        "quality certificate": ["QUALITY CERTIFICATE", "CERTIFICATE OF QUALITY",
                                "INSPECTION CERTIFICATE", "QUALITY REPORT"],
        # 证明/声明类
        "certificate": ["CERTIFICATE", "CERTIFICATION"],
        "beneficiary statement": ["BENEFICIARY STATEMENT", "BENEFICIARY DECLARATION",
                                   "BENEFICIARY'S CERT"],
        # 通知/快递
        "shipping advice": ["SHIPPING ADVICE", "ADVICE OF SHIPMENT", "SHIPMENT ADVICE"],
        "courier receipt": ["COURIER RECEIPT", "PROOF OF DISPATCH", "POSTAL RECEIPT"],
    }

    # 根据单据类型选择关键词
    matched_keywords = []
    lower_type = (type_en + " " + type_cn).lower()
    for key_group, kws in keywords_map.items():
        if isinstance(kws, list):
            if any(kw.lower() in lower_type for kw in kws):
                matched_keywords.extend(kws)
        elif isinstance(kws, str):
            if kws.lower() in lower_type:
                matched_keywords.append(kws)

    # 补充：直接从文本内容提取关键词
    upper_doc = doc_text.upper()
    if "INVOICE" in upper_doc and "INVOICE" not in " ".join(matched_keywords):
        matched_keywords.extend(keywords_map.get("commercial invoice", []))
    if "PACKING" in upper_doc and "PACKING" not in " ".join(matched_keywords):
        matched_keywords.extend(keywords_map.get("packing list", []))
    if "B/L" in upper_doc or "BILL OF LADING" in upper_doc:
        matched_keywords.extend(keywords_map.get("bill of lading", []))
    if "ORIGIN" in upper_doc:
        matched_keywords.extend(keywords_map.get("certificate of origin", []))
    if "INSURANCE" in upper_doc:
        matched_keywords.extend(keywords_map.get("insurance policy", []))
    if "DRAFT" in upper_doc or "EXCHANGE" in upper_doc:
        matched_keywords.extend(keywords_map.get("draft", []))

    if not matched_keywords:
        return []

    # 在47A中搜索相关内容（带上下文窗口扩大 + 去重）
    seen_snippets = set()
    cond_upper = cond_47a.upper()
    for kw in set(matched_keywords):  # 去重关键词
        start_pos = 0
        while True:
            idx = cond_upper.find(kw, start_pos)
            if idx < 0:
                break
            # 动态上下文窗口：关键词越长窗口越小
            window_before = min(60, max(20, len(kw) * 3))
            window_after = min(180, max(80, len(kw) * 6))
            start = max(0, idx - window_before)
            end = min(len(cond_47a), idx + len(kw) + window_after)
            snippet = cond_47a[start:end].strip()
            # 用前40字符做去重key
            dedup_key = snippet[:40].upper().replace("\n", " ")
            if len(snippet) > 25 and dedup_key not in seen_snippets:
                seen_snippets.add(dedup_key)
                # 判断相关性级别
                relevance = _judge_relevance(snippet, kw, doc_text)
                related.append((f"[47A → {kw}]", snippet, relevance))
            start_pos = idx + len(kw)

    # 按相关性排序
    related.sort(key=lambda x: x[2], reverse=True)
    return related


def _judge_relevance(snippet_47a, keyword, doc_text):
    """判断47A片段与本单据的相关性分数 (0-100)"""
    score = 50  # 基础分（因为已命中关键词）

    # 关键词出现在片段前部 → 更相关
    pos = snippet_47a.upper().find(keyword.upper())
    if pos is not None and pos < 20:
        score += 15

    # 片段中出现更多与该单据同类型的词汇
    doc_words = set(re.findall(r'[A-Z]{3,}', doc_text.upper()))
    snippet_words = set(re.findall(r'[A-Z]{3,}', snippet_47a.upper()))
    overlap = doc_words & snippet_words
    score += min(25, len(overlap) * 8)

    # 片段长度适中（太短可能是误命中，太长则可能不聚焦）
    if 40 <= len(snippet_47a) <= 200:
        score += 10

    return min(100, score)


def _build_chapter3_docs_required(story, S, analysis, clauses):
    """
    第三章：单据要求 (46A Documents Required) — 按模板逐单据展开

    新模板格式（每份单据4段式）：
      ┌─────────────────────────────────────────────┐
      │ [序号] 单据中文名 (English Name)              │ ← 标题栏
      ├──────────┬──────────┬────────────────────────┤
      │ 份数     │ 抬头/签发 │ 特殊要求               │ ← 结构化字段行
      ├──────────┴──────────┴────────────────────────┤
      │                                             │
      │  详细条款原文展示框                            │ ← 原文区域
      │                                             │
      ├─────────────────────────────────────────────┤
      │ [47A附加要求汇总]                             │ ← 47A关联区（如有）
      └─────────────────────────────────────────────┘
    """
    story.append(Paragraph("三、单据要求 / Documents Required (46A)", S["h1"]))

    doc_46a = clauses.get("46A", "").strip()
    cond_47a = clauses.get("47A", "").strip()

    if not doc_46a:
        story.append(note_box("无单据要求", "本信用证未包含46A单据要求字段。", "info"))
        return

    # ---- 解析单据列表 ----
    docs_parsed = []
    try:
        from utils.lc_analyzer import parse_doc_list as _pdl
        external_docs = _pdl(doc_46a)
        if external_docs:
            # 外部解析器返回的也转换为统一格式
            for ed in external_docs:
                if isinstance(ed, dict):
                    docs_parsed.append(_extract_doc_fields(ed.get("raw_content", str(ed))))
                else:
                    docs_parsed.append(_extract_doc_fields(str(ed)))
    except Exception:
        pass

    if not docs_parsed:
        docs_parsed = _parse_doc_items(doc_46a)

    # ---- 统计概览 ----
    total_docs = len(docs_parsed)
    orig_count = sum(1 for d in docs_parsed if "original" in d.get("copies", "").lower() or d.get("copies") != "-")
    has_draft_check, draft_reasons = _check_needs_draft(
        clauses.get("42C", ""), clauses.get("42A", ""),
        clauses.get("42M", ""), doc_46a, cond_47a
    )

    overview_lines = [
        f"<b>单据种类：</b>{total_docs} 项",
        f"<b>含正本要求：</b>{orig_count} 项",
        f"<b>需提交汇票：</b>{'是' if has_draft_check else '否'}",
    ]
    story.append(Paragraph(" | ".join(overview_lines), S["small"]))
    story.append(HRFlowable(width="100%", thickness=0.4, color=hex_color(C.BORDER), spaceAfter=6*mm))

    # ---- 逐单据展开 ----
    for idx, doc_fields in enumerate(docs_parsed):
        _render_single_doc_card(story, S, doc_fields, idx + 1, cond_47a, clauses)

    # ---- 汇票专项说明块 ----
    _render_draft_section(story, S, has_draft_check, draft_reasons, clauses)


def _render_single_doc_card(story, S, doc_fields, seq_no, cond_47a, clauses=None):
    """
    渲染单份单据的卡片组件（4段式模板）。

    参数:
        doc_fields: _extract_doc_fields 返回的 dict
        seq_no: 序号（从1开始）
        cond_47a: 47A全文（用于匹配关联条件）
    """
    type_cn = doc_fields.get("type_cn", "其他单据")
    type_en = doc_fields.get("type_en", "")
    copies = doc_fields.get("copies", "-")
    header = doc_fields.get("header", "-")
    special_req = doc_fields.get("special_req", [])
    details = doc_fields.get("details", [])
    raw_content = doc_fields.get("raw_content", "")

    # ===== 第一段：标题栏 =====
    title_text = f"<b>[{seq_no}]</b> {type_cn}"
    if type_en and type_en.lower() != type_cn.lower():
        title_text += f"  <font color='#6B7280' size=8.5>({type_en})</font>"
    story.append(Paragraph(title_text, S["h2"]))

    # ===== 第二段：结构化字段表（份数 | 抬头 | 特殊要求）=====
    field_rows = [[
        Paragraph("<b>份数 (Copies)</b>", S["th"]),
        Paragraph("<b>抬头/签发方 (Header)</b>", S["th"]),
        Paragraph("<b>特殊要求 (Special Requirements)</b>", S["th"]),
    ]]

    # 格式化特殊要求标签 — 提单(B/L)相关用黄色标签，其他用蓝色
    special_tags = []
    for sr in special_req:
        # 判断是否为提单相关特殊要求
        is_bl = type_en and any(kw in type_en.upper() for kw in ['BILL OF LADING', 'B/L', 'TRANSPORT DOCUMENT'])
        tag_color = C.AMBER_BD if is_bl else C.BLUE
        special_tags.append(tag_cell(sr, tag_color, C.WHITE))
    special_display = special_tags if special_tags else [Paragraph("<i>-</i>", S["small"])]

    field_rows.append([
        Paragraph(_esc(copies), S["bl"]),
        Paragraph(_esc(header[:200]) if len(header) > 200 else _esc(header), S["bl"]),
        special_display[0] if len(special_display) == 1 else special_display,
    ])

    # 处理特殊要求多标签情况
    if len(special_req) > 1:
        # 多标签时用换行连接
        is_bl = type_en and any(kw in type_en.upper() for kw in ['BILL OF LADING', 'B/L', 'TRANSPORT DOCUMENT'])
        tag_color = C.AMBER_BD if is_bl else C.BLUE
        field_rows[-1][2] = Table(
            [[tag_cell(sr, tag_color, C.WHITE) for sr in special_req]],
            colWidths=[None] * len(special_req)
        )
        field_rows[-1][2].setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ]))

    field_table = Table(field_rows, colWidths=[32*mm, 68*mm, 62*mm])
    field_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), hex_color(C.NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), hex_color(C.WHITE)),
        ("BACKGROUND", (0, 1), (-1, -1), hex_color(C.LGREY)),
        ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.NAVY)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(field_table)
    story.append(Spacer(1, 1.5*mm))

    # ===== 第三段：详细条款原文 =====
    # 如果有拆分的详细项，先展示简要列表，再展示完整原文
    if details and len(details) > 1:
        detail_items = []
        for di in details[:8]:
            detail_items.append(Paragraph(f"• {_esc(di)}", S["bl"]))
        detail_table = Table([[di] for di in detail_items], colWidths=[162*mm])
        detail_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(detail_table)
        story.append(Spacer(1, 1*mm))

    # 完整原文框（清理无意义冒号分隔符）
    story.append(Paragraph("<font size=8 color='#6B7280'>[条款原文]</font>", S["small"]))
    clean_raw = _clean_lc_colons(raw_content)
    story.append(box_para(Paragraph(_esc(clean_raw), S["body"]), C.WHITE, C.BORDER))

    # ===== 第四段：47A附加要求汇总 =====
    notes_47a = _doc_47a_notes(doc_fields, cond_47a)
    if notes_47a:
        story.append(Spacer(1, 1.5*mm))
        # 显示所有关联条目（不再限制为3条）
        shown = notes_47a
        count_badge = f" ({len(notes_47a)} 条关联)" if len(notes_47a) > 1 else ""
        story.append(Paragraph(
            f"<font color='#D97706'><b>[!] 47A 附加要求汇总{count_badge}</b></font>", S["h2"]
        ))
        for label, snippet, rel_score in shown:
            # 相关性颜色编码
            if rel_score >= 75:
                badge_color = C.RED_BD
                badge_text = "高相关"
            elif rel_score >= 55:
                badge_color = C.AMBER_BD
                badge_text = "中相关"
            else:
                badge_color = C.GREY
                badge_text = "参考"

            content = (
                f"<b>{label}</b> "
                f"{tag_cell(badge_text, badge_color, C.WHITE) if isinstance(tag_cell('', C.GREY).__class__, Table) else f'<font color=\"{badge_color}\">[{badge_text}]</font>'}"
                f"<br/>{_esc(snippet)}"
            )
            # 直接用 note_box 展示
            clean_snippet = _clean_lc_colons(snippet)
            story.append(note_box(label, clean_snippet, "warning"))
            story.append(Spacer(1, 1*mm))

    # 单据间间隔
    story.append(Spacer(1, 2*mm))


def _render_draft_section(story, S, needs_draft, draft_reasons, clauses):
    """渲染汇票专项说明区块"""
    story.append(Paragraph("汇票专项说明 (Draft/Bill of Exchange)", S["h2"]))

    if needs_draft:
        # 构建汇票详细信息表
        clause_42c = clauses.get("42C", "") if clauses else ""
        clause_42a = clauses.get("42A", "") if clauses else ""
        clause_42m = clauses.get("42M", "") if clauses else ""

        draft_info_rows = [[
            Paragraph("<b>要素</b>", S["th"]),
            Paragraph("<b>L/C 条款要求</b>", S["th"]),
            Paragraph("<b>制单提示</b>", S["th"]),
        ]]
        draft_info_rows.append([
            Paragraph("期限 (42C)", S["tc"]),
            Paragraph(_esc(clause_42c) if clause_42c else "<i>未明确</i>", S["bl"]),
            Paragraph("汇票期限须与42C一致（如 AT SIGHT / 90 DAYS AFTER SIGHT 等）", S["small"]),
        ])
        draft_info_rows.append([
            Paragraph("付款人 (42A)", S["tc"]),
            Paragraph(_esc(clause_42a) if clause_42a else "<i>默认开证行</i>", S["bl"]),
            Paragraph("付款人填写42A指定银行；若空白则以开证行为付款人", S["small"]),
        ])
        draft_info_rows.append([
            Paragraph("混付 (42M)", S["tc"]),
            Paragraph(_esc(clause_42m) if clause_42m else "<i>无混付条款</i>", S["bl"]),
            Paragraph("注意混付条款对金额的影响", S["small"]),
        ])

        draft_table = Table(draft_info_rows, colWidths=[24*mm, 64*mm, 74*mm])
        draft_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), hex_color(C.NAVY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), hex_color(C.WHITE)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [hex_color(C.WHITE), hex_color(C.LGREY)]),
            ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.NAVY)),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(draft_table)

        story.append(Spacer(1, 2*mm))
        # 清理 draft_reasons 中可能残留的 HTML/格式乱码
        clean_reasons = []
        for dr in draft_reasons:
            cr = re.sub(r'</?(?:br|b|i|font|/?[^>]+)>', '', str(dr))
            cr = re.sub(r'\s+', ' ', cr).strip()
            if cr:
                clean_reasons.append(cr)
        story.append(note_box(
            "[!] 需要提交汇票",
            "<br/>".join(clean_reasons) +
            "<br/><br/>"
            "<b>制单核心检查清单：</b><br/>"
            "• 汇票金额不得超过信用证金额<br/>"
            "• 汇票期限须与42C一致<br/>"
            "• 付款人(Drawee)须与42A指定一致<br/>"
            "• 收款人(Payee)一般为受益人<br/>"
            "• 日期应在交单有效期内<br/>"
            "• 汇票上应注明信用证编号",
            "warning"
        ))
    else:
        story.append(note_box(
            "[OK] 本信用证未要求提交汇票",
            "根据条款分析（42C/42A/42M + 46A/47A综合判断），本信用证没有明确要求提交汇票(draft/bill of exchange)。<br/><br/>"
            "注意：如果付款方式为承兑或议付，即使未明确列明汇票条款，银行也可能要求提供汇票。建议与通知行确认。",
            "success"
        ))


# ---------- 第四章：附加条件要点 ----------

def _extract_addresse_from_47a(cond_47a):
    """从47A中提取受益人联系地址/通知方式要求"""
    results = []
    patterns = [
        (r'(BENEFICIARY(?:\'S)?\s*(?:ADDRESS|FAX|TELEX|EMAIL|PHONE|CONTACT).*?)(?:\+\n|\n\n|\Z)',
         "受益人联系方式要求"),
        (r'(ALL\s+DOCUMENTS?\s*MUST\s*(?:INDICATE|SHOW|BEAR|STATE).*?)(?:\+\n|\n\n|\Z)',
         "单据标注要求"),
        (r'(ORIGINALS?\s+(?:OF\s+)?THIS\s+CREDIT.*?PRESENTED.*?)(?:\+\n|\n\n|\Z)',
         "信用证正本交单要求"),
        (r'(DOCUMENTS?\s*MUST\s+BE\s+(?:SENT|FORWARDED|DESPATCHED).*?)(?:\+\n|\n\n|\Z)',
         "寄单指示"),
    ]
    for pat, label in patterns:
        m = re.search(pat, cond_47a, re.IGNORECASE | re.DOTALL)
        if m:
            text = m.group(1).strip()
            if len(text) > 10:
                results.append((label, text[:300]))
    return results


def _split_47a_sections(cond_47a):
    """将47A文本按逻辑分类拆分为多个子区域
    
    增强版：
    - 同时支持 "+" 和 "::" 作为分隔符
    - 对过长的单条进行二次拆分
    - 确保每条完整展示不被截断
    """
    if not cond_47a or not cond_47a.strip():
        return []

    sections = []
    
    # 先按 "+" 开头的子句分割
    parts = re.split(r'\n(?=\+)', cond_47a)
    
    # 如果没有按 + 分割成功（可能文本不含 +），尝试 :: 分割
    if len(parts) <= 1 and '::' in cond_47a:
        parts = cond_47a.split('::')
    
    # 如果还是没有分割成功，整段作为一项
    if len(parts) <= 1:
        parts = [cond_47a]

    categories = {
        "document_req": [],
        "insurance": [],
        "charges": [],
        "presentation": [],
        "bank_instruction": [],
        "other": [],
    }

    for part in parts:
        p_stripped = part.strip()
        if not p_stripped or len(p_stripped) < 3:
            continue
        
        # 清理前导的 "+"
        if p_stripped.startswith("+"):
            p_stripped = p_stripped[1:].strip()
        
        # 如果一条非常长(>200字符)且包含 ::，进一步拆分
        if len(p_stripped) > 200 and '::' in p_stripped:
            sub_parts = [s.strip() for s in p_stripped.split('::') if s.strip()]
            for sp in sub_parts:
                _categorize_47a_item(sp, categories)
        else:
            _categorize_47a_item(p_stripped, categories)

    cat_labels = {
        "document_req": "单据制作/提交要求",
        "insurance": "保险相关条款",
        "charges": "费用承担条款",
        "presentation": "时限/交单要求",
        "bank_instruction": "银行寄单指示",
        "other": "其他附加条件",
    }

    for cat_key, cat_items in categories.items():
        if cat_items:
            sections.append((cat_labels[cat_key], cat_items))

    return sections


def _categorize_47a_item(item_text, categories):
    """将单个 47A 子条目归入对应类别"""
    pu = item_text.upper()

    if any(k in pu for k in ["INSURANCE", "POLICY", "COVER NOTE"]):
        categories["insurance"].append(item_text)
    elif any(k in pu for k in ["CHARGE", "FEE", "ACCOUNT", "FOR YOUR ACC"]):
        categories["charges"].append(item_text)
    elif any(k in pu for k in ["DOCUMENT", "PRESENT", "ORIGINAL", "COPY", "ISSUED"]):
        categories["document_req"].append(item_text)
    elif any(k in pu for k in ["WITHIN", "DAYS", "BEFORE", "AFTER", "LATEST"]):
        categories["presentation"].append(item_text)
    elif any(k in pu for k in ["SEND", "MAIL", "COURIER", "SWIFT", "IN ONE LOT"]):
        categories["bank_instruction"].append(item_text)
    else:
        categories["other"].append(item_text)


def _build_chapter4_47a_conditions(story, S, analysis, clauses):
    """第四章：附加条件要点 (47A Key Additional Conditions)"""
    story.append(Paragraph("四、附加条件要点 / Additional Conditions (47A)", S["h1"]))

    cond_47a = clauses.get("47A", "").strip()

    if not cond_47a:
        story.append(note_box("无附加条件", "本信用证未包含47A附加条件字段。", "info"))
        return

    # 分类展示
    sections = _split_47a_sections(cond_47a)

    if not sections:
        # fallback: 整体显示
        story.append(Paragraph(_bf("47A 原文:"), S["h2"]))
        story.append(box_para(Paragraph(_esc(cond_47a), S["body"]), C.WHITE, C.BORDER))
        return

    for sec_title, sec_items in sections:
        story.append(Paragraph(_bf(sec_title + ":"), S["h2"]))
        for item in sec_items:
            story.append(Spacer(1, 1*mm))
            # 每个子条目用浅灰框包裹
            clean_item = item.strip()
            if clean_item.startswith("+"):
                clean_item = clean_item[1:].strip()
            story.append(box_para(Paragraph(_esc(clean_item), S["bl"]), C.LGREY, C.BORDER))
        story.append(Spacer(1, 2*mm))

    # 特别提取：受益人联系地址要求
    addresse_items = _extract_addresse_from_47a(cond_47a)
    if addresse_items:
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(_bf("重点提示 - 受益人须注意的47A条款:"), S["h2"]))
        for label, text in addresse_items:
            story.append(note_box(label, text, "warning"))
            story.append(Spacer(1, 2*mm))


# ---------- 第五章：条款异常分析 ----------


# ---- 异常类型配置常量 ----

ANOMALY_TYPE_CONFIG = {
    "T1-自相矛盾": {
        "label_cn": "自相矛盾",
        "short_code": "T1",
        "color": C.RED_BD,
        "bg_color": C.RED_BG,
        "style_name": "risk_high",
        "icon": "[!]",  # 纯ASCII，避免CJK字体渲染乱码
        "desc_template": "信用证内两个或多个条款之间存在直接逻辑矛盾，导致无法同时满足。",
    },
    "T2-操作不合理": {
        "label_cn": "操作不合理",
        "short_code": "T2",
        "color": C.AMBER_BD,
        "bg_color": C.AMBER_BG,
        "style_name": "risk_med",
        "icon": "[T]",  # Time/操作
        "desc_template": "条款要求在实际操作中难以满足或存在极紧的时间压力。",
    },
    "T3-模糊/不完整": {
        "label_cn": "模糊/不完整",
        "short_code": "T3",
        "color": C.AMBER_BD,
        "bg_color": C.AMBER_BG,
        "style_name": "risk_med",
        "icon": "[?]",
        "desc_template": "条款表述不够明确或缺少关键信息，可能导致不同解读。",
    },
    "T4-非常规财务": {
        "label_cn": "非常规财务",
        "short_code": "T4",
        "color": C.RED_BD,
        "bg_color": C.RED_BG,
        "style_name": "risk_high",
        "icon": "[$]",  # Financial
        "desc_template": "涉及非标准金融条款（如自动扣款/罚金），可能影响实际收款金额。",
    },
    "T5-疑似软条款": {
        "label_cn": "疑似软条款",
        "short_code": "T5",
        "color": C.RED_BD,
        "bg_color": C.RED_BG,
        "style_name": "risk_high",
        "icon": "[S]",  # Soft clause
        "desc_template": "条款要求依赖申请人配合或主观判断，受益人无法自主控制。",
    },
    "T6-单据冲突风险": {
        "label_cn": "单据冲突风险",
        "short_code": "T6",
        "color": C.AMBER_BD,
        "bg_color": C.AMBER_BG,
        "style_name": "risk_med",
        "icon": "[D]",  # Document
        "desc_template": "46A单据要求与47A附加条件之间存在潜在的不一致或不匹配。",
    },
    "T7-UCP600偏离": {
        "label_cn": "UCP600偏离",
        "short_code": "T7",
        "color": C.BLUE,
        "bg_color": C.LIGHT_BLUE,
        "style_name": "body",
        "icon": "[U]",  # UCP
        "desc_template": "条款与UCP600国际惯例存在偏离，需特别注意其影响。",
    },
}

# 严重度级别定义
SEVERITY_LEVELS = {
    "critical": {"order": 4, "label": "严重(Critical)", "color": "#991B1B", "bd": C.RED_BD},
    "high":     {"order": 3, "label": "高(High)",       "color": "#DC2626", "bd": C.RED_BD},
    "medium":   {"order": 2, "label": "中(Medium)",     "color": "#D97706", "bd": C.AMBER_BD},
    "low":      {"order": 1, "label": "低(Low)",        "color": "#059669", "bd": C.GREEN_BD},
}


def _build_chapter5_anomaly_review(story, S, analysis, clauses, anomalies):
    """
    第五章：条款异常分析 / Clause Anomaly Review — 增强5列表格

    列结构:
      ┌──────────┬──────┬──────────────┬──────────┬──────────┐
      │ 异常类型  │涉及字段│  原始条文摘录  │ 问题描述  │  建议措施  │
      └──────────┴──────┴──────────────┴──────────┴──────────┘

    增强特性:
      - 统计概览面板（总数/各等级计数/各类型分布）
      - 严重项整行红色高亮背景
      - 类型分组显示（可选）
      - 智能原文摘取（关键词加粗）
      - 差异化建议措施
    """
    story.append(Paragraph("五、条款异常分析 / Clause Anomaly Review", S["h1"]))

    # ---- 数据收集：外部传入 + 自动扫描 + 合并去重 ----
    external_anomalies = list(anomalies or [])
    auto_anomalies = _auto_detect_anomalies_v2(clauses, analysis)

    # 合并去重（基于 description 前80字符）
    all_anomalies = list(external_anomalies)
    seen_keys = set()
    for a in all_anomalies:
        key = str(a.get("description", "") or a.get("detail", ""))[:80].strip().lower()
        seen_keys.add(key)

    for aa in auto_anomalies:
        aa_key = str(aa.get("description", "") or aa.get("detail", ""))[:80].strip().lower()
        if aa_key not in seen_keys:
            all_anomalies.append(aa)
            seen_keys.add(aa_key)

    # ---- 无异常时快速返回 ----
    if not all_anomalies:
        story.append(note_box(
            "[OK] 未发现条款异常",
            "本信用证条款经全面自动扫描（含7大类15+检测规则）后，"
            "未发现自相矛盾、操作不合理、模糊/不完整、非常规财务、"
            "软条款、单据冲突或UCP600偏离等类型的异常条款。<br/><br/>"
            "<i>注：本检测覆盖 SWIFT MT700 各主要字段及46A/47A全文内容。"
            "如需更深入的人工审核，建议逐条核对。</i>",
            "success"
        ))
        return

    # ---- 统计概览面板 ----
    _render_anomaly_stats_panel(story, S, all_anomalies)
    story.append(Spacer(1, 2*mm))

    # ---- 按 severity 排序：critical → high → medium → low ----
    def _sort_key(a):
        sev = str(a.get("severity", "")).lower()
        if sev in SEVERITY_LEVELS:
            return (-SEVERITY_LEVELS[sev]["order"], len(all_anomalies))
        return (0, len(all_anomalies))

    all_anomalies.sort(key=_sort_key)

    # ---- 渲染5列主表格 ----
    _render_anomaly_table(story, S, all_anomalies, clauses)

    # ---- 底部行动建议汇总 ----
    _render_action_summary(story, S, all_anomalies)


def _render_anomaly_stats_panel(story, S, anomalies):
    """渲染统计概览面板 — 饼图式文字统计"""
    total = len(anomalies)

    # 按严重度统计
    sev_counts = {}
    for sev_key in ["critical", "high", "medium", "low"]:
        cnt = sum(
            1 for a in anomalies
            if str(a.get("severity", "")).lower() == sev_key
        )
        if cnt > 0:
            sev_counts[sev_key] = cnt

    # 按类型统计
    type_counts = {}
    for a in anomalies:
        atype = _normalize_anomaly_type(a)
        type_counts[atype] = type_counts.get(atype, 0) + 1

    # 构建概览文本
    lines = []

    # 总数 + 严重度分布
    sev_display = []
    for sev_key in ["critical", "high", "medium", "low"]:
        if sev_key in sev_counts:
            cfg = SEVERITY_LEVELS[sev_key]
            sev_display.append(
                f"<font color='{cfg['color']}'><b>{cfg['label']}: "
                f"{sev_counts[sev_key]}</b></font>"
            )
    lines.append(_bf(f"总计 {total} 项异常") + " | " + " | ".join(sev_display))

    # 类型分布
    type_parts = []
    sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])
    for atype, cnt in sorted_types[:7]:
        atype_cfg = ANOMALY_TYPE_CONFIG.get(atype)
        short = atype_cfg["short_code"] if atype_cfg else atype.split("-")[0]
        label = atype_cfg["label_cn"] if atype_cfg else atype
        type_parts.append(f"{short}({label}): {cnt}")
    lines.append(_bf("类型分布:") + " " + ", ".join(type_parts))

    # 用 info box 展示
    content = "<br/>".join(lines)
    story.append(box_para(Paragraph(content, S["body"]), C.LIGHT_BLUE, C.BLUE))


def _render_anomaly_table(story, S, anomalies, clauses=None):
    """
    渲染增强版5列异常表格。

    列定义：
      Col 1: 异常类型标签（带颜色编码）
      Col 2: 涉及字段/条款号
      Col 3: 原始条文摘录（智能截取+关键词保留）
      Col 4: 问题描述（自然语言）
      Col 5: 建议措施（可操作的具体建议）
    """
    # ---- 表头 ----
    header_row = [
        Paragraph("<b>异常类型</b>", S["th"]),
        Paragraph("<b>涉及字段</b>", S["th"]),
        Paragraph("<b>原始条文摘录</b>", S["th"]),
        Paragraph("<b>问题描述</b>", S["th"]),
        Paragraph("<b>建议措施</b>", S["th"]),
    ]

    rows = [header_row]

    # ---- 构建数据行 ----
    for a in anomalies:
        # 归一化异常类型
        atype = _normalize_anomaly_type(a)

        # 获取类型样式配置
        atype_cfg = ANOMALY_TYPE_CONFIG.get(atype)
        if atype_cfg:
            bd_col = atype_cfg["color"]
            style_name = atype_cfg["style_name"]
            type_label = f"{atype_cfg['icon']} {atype_cfg['label_cn']}"
        else:
            bd_col = C.GREY
            style_name = "body"
            type_label = str(atype)

        # 严重度（用于决定是否高亮整行）
        sev_raw = str(a.get("severity", "")).lower()
        is_critical_or_high = sev_raw in ("critical", "high")

        # Col 1: 异常类型标签
        col1 = tag_cell(type_label, bd_col, C.WHITE)

        # Col 2: 涉及字段/条款号
        fields_val = a.get("fields", a.get("clause_ref", "-"))
        col2 = Paragraph(str(fields_val), S["tc"])

        # Col 3: 原始条文摘录（智能处理）
        raw_text = a.get("original_text", a.get("detail", ""))
        col3 = _format_original_excerpt(raw_text, max_len=160)

        # Col 4: 问题描述
        desc_text = a.get("description", a.get("detail", ""))
        col4 = Paragraph(_esc(str(desc_text)[:180]), S["bl"])

        # Col 5: 建议措施
        suggestion = a.get("suggestion", _default_suggestion_for_type(atype))
        col5 = Paragraph(_esc(str(suggestion)[:140]), S["small"])

        row_data = [col1, col2, col3, col4, col5]
        rows.append(row_data)

    # ---- 表格样式 ----
    # A4 可用宽度 = 210mm - 18mm*2(margin) = 174mm
    # 分配: 类型20 | 字段15 | 摘录46 | 问题48 | 剩余45 → 总计174mm
    col_widths = [19*mm, 14*mm, 45*mm, 47*mm, 39*mm]

    t = Table(rows, colWidths=col_widths)

    # 基础样式 — 紧凑型padding防止颜色区域溢出
    base_style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), hex_color(C.NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), hex_color(C.WHITE)),
        ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.NAVY)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]

    # 斑马纹 + 高危行特殊背景
    for i in range(1, len(rows)):
        a_item = anomalies[i - 1] if i - 1 < len(anomalies) else {}
        sev_raw = str(a_item.get("severity", "")).lower()

        if sev_raw in ("critical", "high"):
            # 高危行：浅红背景
            base_style.append(("BACKGROUND", (0, i), (-1, i), hex_color(C.RED_BG)))
        elif i % 2 == 0:
            base_style.append(("BACKGROUND", (0, i), (-1, i), hex_color(C.LGREY)))
        else:
            base_style.append(("BACKGROUND", (0, i), (-1, i), hex_color(C.WHITE)))

    t.setStyle(TableStyle(base_style))
    story.append(t)


def _format_original_excerpt(raw_text, max_len=160):
    """
    格式化原始条文摘录：
    - 截断过长文本
    - 清理多余空白
    - 如果包含SWIFT字段标记则保留
    """
    if not raw_text:
        return Paragraph("<i>-</i>", make_styles()["small"])

    text = str(raw_text).strip()
    # 清理连续空行和首尾空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace('\t', ' ').strip()

    if len(text) > max_len:
        # 尝试在句号或换行处断开
        cut_pos = text.rfind('.', 0, max_len)
        if cut_pos > max_len * 0.6:
            text = text[:cut_pos + 1] + "..."
        else:
            text = text[:max_len - 3] + "..."

    S = make_styles()
    return Paragraph(_esc(text), S["small"])


def _normalize_anomaly_type(anomaly_dict):
    """
    归一化异常类型名称到标准格式。
    兼容多种输入格式: "Type 1-自相矛盾", "T1-自相矛盾", "type1", "自相矛盾" 等。
    """
    raw = anomaly_dict.get("anomaly_type", "") \
         or anomaly_dict.get("type", "") \
         or anomaly_dict.get("anomaly_type_cn", "") \
         or "T3-模糊/不完整"

    upper_raw = raw.upper().strip()

    # 直接匹配
    mapping = {
        "T1": "T1-自相矛盾", "TYPE 1": "T1-自相矛盾",
        "TYPE1-自相矛盾": "T1-自相矛盾", "TYPE 1-自相矛盾": "T1-自相矛盾",
        "自相矛盾": "T1-自相矛盾", "CONTRADICTION": "T1-自相矛盾",

        "T2": "T2-操作不合理", "TYPE 2": "T2-操作不合理",
        "TYPE2-操作不合理": "T2-操作不合理", "TYPE 2-操作不合理": "T2-操作不合理",
        "操作不合理": "T2-操作不合理", "UNREASONABLE": "T2-操作不合理",

        "T3": "T3-模糊/不完整", "TYPE 3": "T3-模糊/不完整",
        "TYPE3-模糊/不完整": "T3-模糊/不完整", "TYPE 3-模糊/不完整": "T3-模糊/不完整",
        "模糊": "T3-模糊/不完整", "不完整": "T3-模糊/不完整", "INCOMPLETE": "T3-模糊/不完整",

        "T4": "T4-非常规财务", "TYPE 4": "T4-非常规财务",
        "TYPE4-非常规财务": "T4-非常规财务", "FINANCIAL": "T4-非常规财务",

        "T5": "T5-疑似软条款", "SOFT": "T5-疑似软条款",
        "软条款": "T5-疑似软条款", "SOFT CLAUSE": "T5-疑似软条款",

        "T6": "T6-单据冲突风险", "DOC CONFLICT": "T6-单据冲突风险",
        "单据冲突": "T6-单据冲突风险",

        "T7": "T7-UCP600偏离", "UCP": "T7-UCP600偏离",
        "UCP600": "T7-UCP600偏离",
    }

    # 先尝试完全匹配
    if upper_raw in [k.upper() for k in mapping]:
        for k, v in mapping.items():
            if k.upper() == upper_raw:
                return v

    # 再尝试子串匹配
    for k, v in mapping.items():
        if k.upper() in upper_raw or upper_raw in k.upper():
            return v

    # fallback
    return raw


def _default_suggestion_for_type(atype):
    """根据异常类型返回默认建议措施"""
    defaults = {
        "T1-自相矛盾": "立即联系开证行澄清矛盾条款，取得书面确认后方可继续操作。",
        "T2-操作不合理": "评估可行性后考虑申请修改此条款，或提前做好应对准备。",
        "T3-模糊/不完整": "主动联系开证行获取补充说明或修改为明确表述。",
        "T4-非常规财务": "计算实际收款金额对利润的影响；若不可接受应立即申请修改。",
        "T5-疑似软条款": "[!] 软条款属高风险项。强烈建议在发货前要求申请人删除或修改该条款。",
        "T6-单据冲突风险": "仔细核对46A与47A中相关单据的要求差异，制单时以更严格者为准。",
        "T7-UCP600偏离": "了解该偏离条款的实际含义和对业务的影响范围。",
    }
    return defaults.get(atype, "建议与开证行或通知行确认该条款的具体含义和执行方式。")


def _render_action_summary(story, S, anomalies):
    """渲染底部行动建议汇总"""
    # 只列出 high/critical 级别的行动项
    critical_items = [
        a for a in anomalies
        if str(a.get("severity", "")).lower() in ("critical", "high")
    ]

    if not critical_items:
        return

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(_bf("[!] 必须在发货前处理的异常项:"), S["h2"]))

    for i, item in enumerate(critical_items):
        desc = (item.get("description", "") or item.get("detail", ""))[:200]
        suggestion = item.get("suggestion", "")[:150]
        atype = _normalize_anomaly_type(item)
        atype_cfg = ANOMALY_TYPE_CONFIG.get(atype, {})
        type_badge = atype_cfg.get("label_cn", atype)

        body = (
            f"<b>[#{i+1}] {type_badge}</b>"
            f"<br/>{_esc(desc)}"
        )
        if suggestion:
            body += f"<br/><br/><b>▶ 建议：</b>{_esc(suggestion)}"

        story.append(note_box(f"高优先级 #{i+1}", body, "danger"))
        story.append(Spacer(1, 2*mm))


# ==============================================================================
#  自动异常检测引擎 V2（15+ 条规则，7大类型）
# ==============================================================================

def _auto_detect_anomalies_v2(clauses, analysis):
    """
    增强版自动异常检测引擎 — 基于15+规则扫描SWIFT MT700全部字段。

    返回 list[dict]，每个元素包含:
      - anomaly_type: 标准类型码 (T1~T7)
      - fields: 涉及的SWIFT字段号
      - original_text: 原始条文摘录
      - description: 自然语言描述
      - suggestion: 可操作的建议
      - severity: 严重度 (critical/high/medium/low)
    """
    found = []
    c_upper = {}  # 各字段的大写缓存
    for key in clauses:
        c_upper[key] = str(clauses.get(key, "")).upper()

    cond_47a = c_upper.get("47A", "")

    # ════════════════════════════════════════════
    # T1: 自相矛盾 (Contradiction)
    # ════════════════════════════════════════════

    # T1-a: 43P允许分批 vs 47A禁止分批
    _check_t1_partial(found, clauses, c_upper)

    # T1-b: 39A有容差 vs 47A要求精确金额
    _check_t1_tolerance(found, clauses, c_upper)

    # T1-c: 41A付款方式与42C汇票期限不匹配
    _check_t1_payment_mismatch(found, clauses, c_upper)

    # T1-d: 44C装船日晚于31D到期日
    _check_t1_dates(found, clauses, analysis)

    # ════════════════════════════════════════════
    # T2: 操作不合理 (Operationally Unreasonable)
    # ════════════════════════════════════════════

    # T2-a: 有效期过短 (<21天)
    _check_t2_short_validity(found, analysis, clauses)

    # T2-b: 交单期过短 (<10天)
    _check_t2_presentation_period(found, clauses)

    # T2-c: 到期地在受益人国外
    _check_t2_expiry_abroad(found, analysis, clauses)

    # T2-d: 装船日与到期日间隔过短(<15天)
    _check_t2_ship_expiry_gap(found, clauses)

    # ════════════════════════════════════════════
    # T3: 模糊/不完整 (Vague/Incomplete)
    # ════════════════════════════════════════════

    # T3-a: 引用不存在附件
    _check_t3_missing_attachment(found, cond_47a, clauses)

    # T3-b: 关键字段缺失
    _check_t3_missing_fields(found, clauses)

    # T3-c: 金额为0或空
    _check_t3_zero_amount(found, clauses)

    # ════════════════════════════════════════════
    # T4: 非常规财务 (Unusual Financial Terms)
    # ════════════════════════════════════════════

    # T4-a: 自动扣款/罚金
    _check_t4_auto_deduction(found, cond_47a, clauses)

    # T4-b: 费用由受益人承担（71B/71D异常）
    _check_t4_beneficiary_charges(found, clauses, c_upper)

    # ════════════════════════════════════════════
    # T5: 疑似软条款 (Suspected Soft Clauses)
    # ════════════════════════════════════════════

    _check_t5_soft_clauses(found, cond_47a, clauses)

    # ════════════════════════════════════════════
    # T6: 单据冲突风险 (Document Conflict Risk)
    # ════════════════════════════════════════════

    _check_t6_doc_conflict(found, clauses, c_upper)

    # ════════════════════════════════════════════
    # T7: UCP600偏离 (UCP600 Deviation)
    # ════════════════════════════════════════════

    _check_t7_ucp_deviation(found, clauses, c_upper)

    return found


# ===== T1 检测函数 =====

def _check_t1_partial(found, clauses, cu):
    """T1-a: 分批装运条款矛盾"""
    partial = cu.get("43P", "")
    if ("ALLOWED" in partial or "PERMITTED" in partial) and \
       re.search(r'(PARTIAL\s+(?:SHIPMENT|)?|PARTIAL)\s*(?:PROHIBITED|NOT\s+ALLOWED|NOT\s+PERMITTED|FORBIDDEN)',
                 cu.get("47A", "")):
        found.append(_make_anomaly(
            "T1-自相矛盾", "43P / 47A",
            f"43P: {clauses.get('43P', '')}\n47A: {clauses.get('47A', '')[:120]}",
            "43P允许分批装运(ALLOWED/PERMITTED)，但47A中有禁止分批(PROHIBITED/NOT ALLOWED)的表述，两条款互相矛盾。",
            "请与开证行书面确认：究竟允许还是禁止分批装运？以哪个条款为准？",
            "high"))


def _check_t1_tolerance(found, clauses, cu):
    """T1-b: 金额容差与精确金额要求矛盾"""
    tol_39a = clauses.get("39A", "").strip()
    if tol_39a and re.search(
        r'(EXACT\s+AMOUNT|NO\s+TOLERANCE|ONLY\s+THE\s+INVOICE\s*(?:VALUE|AMOUNT)?|STRICTLY)\b',
        cu.get("47A", "")
    ):
        found.append(_make_anomaly(
            "T1-自相矛盾", "39A / 47A",
            f"39A: {tol_39a}\n47A excerpt: {clauses.get('47A', '')[:130]}",
            "39A规定了溢短装容差(如05/05=±5%)，但47A中要求精确金额(EXACT AMOUNT/NO TOLERANCE)或仅限发票金额，两者存在潜在冲突。",
            "确认开证行意图：是否可以按39A容差比例浮动发票金额？建议取得书面澄清。",
            "high"))


def _check_t1_payment_mismatch(found, clauses, cu):
    """T1-c: 付款方式与汇票期限潜在不匹配"""
    pay_method = cu.get("41A", "")
    draft_term = clauses.get("42C", "")

    # BY PAYMENT 方式下不应要求远期汇票
    if "BY PAYMENT" in pay_method and draft_term:
        dm_upper = draft_term.upper()
        if any(x in dm_upper for x in ["DAYS AFTER", "SIGHT", "USANCE", "DEFERRED"]):
            if "AT SIGHT" not in dm_upper or "DAYS" in dm_upper:
                found.append(_make_anomaly(
                    "T1-自相矛盾", "41A / 42C",
                    f"41A: {clauses.get('41A', '')}\n42C: {draft_term}",
                    f"41A付款方式为BY PAYMENT（即期付款），但42C规定了汇票期限({draft_term})。即期付款通常不需提交远期汇票。",
                    "确认是否确实需要提交汇票？如需要，付款方式是否应为 BY ACCEPTANCE 或 BY NEGOTIATION？",
                    "medium"))

    # BY ACCEPTANCE 但没有42C期限
    if "ACCEPT" in pay_method and not draft_term.strip():
        found.append(_make_anomaly(
            "T1-自相矛盾", "41A / 42C",
            f"41A: {clauses.get('41A', '')}\n42C: (空)",
            "41A付款方式包含承兑(ACCEPTANCE)，但42C汇票期限为空。承兑付款必须规定汇票期限。",
            "请确认42C汇票期限是否遗漏，并与开证行补充完整。",
            "medium"))


def _check_t1_dates(found, clauses, analysis):
    """T1-d: 最迟装船日晚于到期日"""
    ship_raw = clauses.get("44C", "")
    exp_raw = clauses.get("31D", "")
    ship_m = re.search(r'(\d{6})', ship_raw)
    exp_m = re.search(r'(\d{6})', exp_raw)
    if ship_m and exp_m:
        try:
            from datetime import date as _d
            ss = ship_m.group(1); es = exp_m.group(1)
            ship_dt = _d(2000 + int(ss[:2]), int(ss[2:4]), int(ss[4:6]))
            exp_dt = _d(2000 + int(es[:2]), int(es[2:4]), int(es[4:6]))
            if ship_dt > exp_dt:
                gap_days = (ship_dt - exp_dt).days
                found.append(_make_anomaly(
                    "T1-自相矛盾", "44C / 31D",
                    f"44C (装船日): {ship_raw}\n31D (到期日): {exp_raw}",
                    f"最迟装船日({_format_date_yymmdd(ss)})晚于到期日({_format_date_yymmdd(es)})，差距{gap_days}天。这在逻辑上不可能满足。",
                    "这是一个致命矛盾——装船不可能在信用证过期之后发生。必须要求开证行修改44C或31D。",
                    "critical"))
        except (ValueError, IndexError):
            pass


# ===== T2 检测函数 =====

def _check_t2_short_validity(found, analysis, clauses):
    """T2-a: 有效期过短"""
    issue_dt = analysis.get("issue_date", "")
    exp_dt = analysis.get("expiry_date", "")
    if issue_dt and exp_dt:
        gap = _days_between(issue_dt, exp_dt)
        if gap is not None and gap < 21:
            urgency = "极度紧急" if gap < 14 else "紧张"
            found.append(_make_anomaly(
                "T2-操作不合理", "31C / 31D",
                f"Issue Date: {issue_dt}\nExpiry Date: {exp_dt}",
                f"信用证有效期仅{gap}天（从开证日到到期日），{urgency}。正常贸易流程需要生产+订舱+装运+制单+寄送，时间极难满足。",
                "强烈建议立即申请延长有效期至少60天以上。" +
                (" 若无法修改，需确保所有环节零延误。" if gap < 14 else ""),
                "critical" if gap < 14 else "high"))


def _check_t2_presentation_period(found, clauses):
    """T2-b: 交单期过短"""
    pres = clauses.get("48", "")
    pres_m = re.search(r'(\d+)\s*DAYS?', pres, re.I) if pres else None
    if pres_m and int(pres_m.group(1)) < 10:
        days = int(pres_m.group(1))
        found.append(_make_anomaly(
            "T2-操作不合理", "48",
            pres,
            f"交单期(48)仅{days}天。根据UCP600第14条c款，单据必须在装运日后{days}天内提交。留给单据制作、审核、寄送的时间极为有限。",
            f"建议提前准备好所有单据模板（发票、箱单、提单格式等）。如果实际操作中{days}天内难以完成，应申请延长交单期至21天左右。",
            "medium"))


def _check_t2_expiry_abroad(found, analysis, clauses):
    """T2-c: 到期地在受益人国外"""
    exp_place = analysis.get("expiry_place", "")
    beneficiary = analysis.get("beneficiary", "")
    if exp_place and beneficiary:
        if exp_place.upper() not in beneficiary.upper():
            # 进一步检查：是否在中国
            cn_keywords = ["CHINA", "PEOPLE'S REPUBLIC OF CHINA", "PRC", "BEIJING",
                           "SHANGHAI", "GUANGZHOU", "SHENZHEN"]
            is_foreign = not any(kw in exp_place.upper() for kw in cn_keywords)
            risk_level = "high" if is_foreign else "medium"
            found.append(_make_anomaly(
                "T2-操作不合理", "31D",
                f"Expiry Place: {exp_place}",
                f"到期地为 {_esc(exp_place)}{'（境外）' if is_foreign else ''}，而受益人位于 {_esc(beneficiary[:60])}。" +
                ("跨境交单需要额外邮寄时间，存在逾期风险。" if is_foreign else "异地交单需预留邮寄时间。"),
                "确认从受益人所在地寄单到到期地所需天数（含清关），确保留有足够余量。" +
                ("如可能，建议将到期地改为受益人国家或本国。" if is_foreign else ""),
                risk_level))


def _check_t2_ship_expiry_gap(found, clauses):
    """T2-d: 装船日与到期日间隔过短"""
    ship_raw = clauses.get("44C", "")
    exp_raw = clauses.get("31D", "")
    ship_m = re.search(r'(\d{6})', ship_raw)
    exp_m = re.search(r'(\d{6})', exp_raw)
    if ship_m and exp_m:
        try:
            from datetime import date as _d
            ss = ship_m.group(1); es = exp_m.group(1)
            gd = (_d(2000 + int(es[:2]), int(es[2:4]), int(es[4:6])) -
                  _d(2000 + int(ss[:2]), int(ss[2:4]), int(ss[4:6]))).days
            if 0 <= gd < 15:
                found.append(_make_anomaly(
                    "T2-操作不合理", "44C / 31D",
                    f"44C: {ship_raw}\n31D: {exp_raw}",
                    f"最迟装船日({_format_date_yymmdd(ss)})与到期日({_format_date_yymmdd(es)})之间仅间隔约<b>{gd}</b>天。" +
                    "扣除制单和寄送时间后几乎没有缓冲余地。",
                    "建议申请延展有效期，使装船日与到期日间隔至少保持21天以上。",
                    "high"))
        except (ValueError, IndexError):
            pass


# ===== T3 检测函数 =====

def _check_t3_missing_attachment(found, cond_47a, clauses):
    """T3-a: 引用不存在的附件"""
    if re.search(r'(AS\s+PER\s+ANNEX(?:\s+\w+)?|REFER\s+TO\s+(?:THE\s+)?ATTACHMENT|SEE\s+(?:THE\s+)?APPENDIX|AS\s+DEFINED\s+IN\s+(?:SEPARATE\s+)?DOCUMENT)',
                 cond_47a):
        found.append(_make_anomaly(
            "T3-模糊/不完整", "47A",
            clauses.get("47A", "")[:160],
            "47A引用了附件(Annex/Attachment/Appendix/Separate Document)，但MT700报文本身不含附件内容。缺少附件将导致无法准确理解或执行该条款要求。",
            "请立即向开证行索取所引用的附件副本，并在收到前暂停后续操作。",
            "high"))


def _check_t3_missing_fields(found, clauses):
    """T3-b: 关键字段缺失"""
    missing = []
    required_fields = {
        "32B": "金额货币",
        "31D": "到期日/地",
        "50": "申请人",
        "59": "受益人",
        "46A": "单据要求",
    }
    for field, label in required_fields.items():
        val = clauses.get(field, "")
        if not val or not val.strip():
            missing.append(f"{field}({label})")

    if missing:
        found.append(_make_anomaly(
            "T3-模糊/不完整", ", ".join(missing),
            f"以下关键字段值为空: {', '.join(missing)}",
            f"信用证缺少 {'/'.join(missing[:3])}{'等字段' if len(missing)>3 else ''} 的内容，属于格式不完整的L/C。",
            "请联系通知行核实是否为传输丢失，并要求开证行补发完整报文。",
            "high" if "32B" in missing or "59" in missing else "medium"))


def _check_t3_zero_amount(found, clauses):
    """T3-c: 金额为0或空"""
    amt = clauses.get("32B", "")
    if amt and amt.strip():
        num = _extract_amount_number(amt)
        if num == 0:
            found.append(_make_anomaly(
                "T3-模糊/不完整", "32B",
                amt,
                f"32B金额字段解析结果为0或无法识别有效数值。原值: '{amt}'",
                "金额为0的信用证不具备可操作性。请核实原始报文中32B字段的正确值。",
                "critical"))


# ===== T4 检测函数 =====

def _check_t4_auto_deduction(found, cond_47a, clauses):
    """T4-a: 自动扣款/罚金条款"""
    if re.search(r'(AUTOMATIC\s+(?:DEDUCTION|WITHHOLDING)|PENALTY\s+(?:OF|OF\s*USD?\s*)\d+%?|'
                 r'DEDUCT\s*(?:USD?\s*)?\d+%|\d+%\s*PENALTY|LESS\s*\d+%|HOLD\s*\d+%)',
                 cond_47a):
        found.append(_make_anomaly(
            "T4-非常规财务", "47A",
            clauses.get("47A", "")[:170],
            "47A包含自动扣款(AUTOMATIC DEDUCTION)、罚金(PENALTY)或百分比扣减(HOLD/DEDUCT X%)条款。" +
            "此类条款将导致实际收款金额低于L/C面额。",
            "务必精确计算扣款金额对利润的影响。如果净收款低于可接受水平，应在发货前申请删除或修改此条款。",
            "high"))


def _check_t4_beneficiary_charges(found, clauses, cu):
    """T4-b: 费用由受益人承担"""
    charges_71b = cu.get("71B", "")
    charges_71d = cu.get("71D", "")
    combined = charges_71b + " " + charges_71d
    if ("BENEFICIARY" in combined and ("ACCOUNT" in combined or "FOR YOUR A/C" in combined)) or \
       "ALL BANKING CHARGES OUTSIDE" in combined.upper():
        found.append(_make_anomaly(
            "T4-非常规财务", "71B / 71D",
            f"71B: {clauses.get('71B', '')[:100]}\n71D: {clauses.get('71D', '')[:100]}",
            "费用承担条款(71B/71D)表明部分或全部费用由受益人承担（特别是境外银行费用）。这将增加交易成本。",
            "预估额外费用金额并将其计入成本核算。通常境外银行费用约为USD 50-200/笔。",
            "medium"))


# ===== T5 检测函数 =====

def _check_t5_soft_clauses(found, cond_47a, clauses):
    """T5: 疑似软条款扫描（10类模式）"""
    soft_patterns = [
        # (正则, 描述, 默认建议)
        (
            r'INSPECTION\s+CERTIFICATE.*?(?:ISSUED|SIGNED)\s+(?:BY|TO\s+BE)?\s*(?:THE\s+)?(?:APPLICANT|BUYER|OPENER)',
            "检验证书须由申请人签发",
            "受益人完全无法控制检验证书的获取——申请人可以拒绝签发从而阻止交单。这是典型的软条款。",
            "强烈建议要求将该条款改为'由独立的法定检验机构(如CCIC/SGS)签发'或直接删除。",
        ),
        (
            r'(?:APPLICANT\'?S?\s+(?:CERTIFICATION|CONFIRMATION|APPROVAL|ACCEPTANCE)|'
            r'MUST\s+(?:BE\s+)?(?:CERTIFIED|CONFIRMED|APPROVED|ACCEPTED)\s+(?:BY)?\s*(?:THE\s+)?(?:APPLICANT|BUYER))',
            "需要申请人确认/批准/认证",
            "条款要求申请人提供某种形式的确认或批准，赋予申请人单方面拒绝付款的权利。",
            "要求删除此条款或将确认方改为第三方（如商会/检验公司/通知行）。",
        ),
        (
            r'COPY\s+(?:OF\s+)?(?:FAX|TELEX)?\s*.*?(?:APPROVAL|ACCEPTANCE|GOOD\s+ORDER|SATISFACTORY)',
            "传真确认/满意证明",
            "需要申请人通过传真等方式确认某些事项，受益人控制不了对方的行为和时间。",
            "改为要求受益人自行出具声明书（如'BENEFICIARY'S CERTIFICATE STATING THAT...'）。",
        ),
        (
            r"(?:BENEFICIARY'?S?)?\s*(?:DECLARATION|STATEMENT|CERTIFICATE).*?"
            r"(?:TO\s+THE\s+)?SATISFACTION\s+OF\s+(?:THE\s+)?(?:APPLICANT|BUYER)",
            "'致申请人满意'条款",
            "条款使用'TO THE SATISFACTION OF APPLICANT'这类主观判断标准，无客观衡量依据。",
            "要求改为具体可验证的标准（如'COMPLYING WITH ISO XXXX'或'INSPECTED BY SGS'）。",
        ),
        (
            r'DOCUMENTS?\s+(?:RELEASED|ISSUED)\s+(?:AGAINST|ON)\s+(?:INDemnity|UNDERTAKING|LETTER\s+OF\s+INDEMNITY|LOI)',
            '担保放单/赔偿担保',
            "条款提到在单据不符点情况下凭担保放单(INDEMNITY/UNDERTAKING)，增加收汇风险。",
            "注意：这虽不是典型软条款，但意味着即使有不符点也可能被放单，受益人追索权受限。",
        ),
        (
            r'CLEAN\s+ON\s+BOARD.*?(?:BEARING|SHOWING|INDICATING|MARKED).*?'
            r'(?:DATE|VESSEL|NAME\s+OF\s+(?:VESSEL|CARRIER)|PORT)',
            "提单细节过度指定",
            "条款对提单上的具体细节（如确切日期、船名、港口标注方式）做了超出UCP600惯例的详细要求。",
            "仔细核对每个要求是否能与实际运输情况一致。如有疑问，建议申请放宽要求。",
        ),
        (
            r'(?:ORIGINAL\s+)?(?:TELEX|FAX|EMAIL|E-MAIL)\s+(?:COPY|ADVICE|REPORT)\s+FROM\s+(?:THE\s+)?(?:APPLICANT|BUYER)',
            "须申请人发送的电传/传真/邮件副本",
            "要求申请人主动发送某类证明文件给银行，受益人无法保证申请人会按时发送。",
            "改为要求受益人自己出具一份声明即可（如'BENEFICIARY CERTIFYING THAT COPY SENT TO APPLICANT'）。",
        ),
        (
            r'GOOD[S]?\s+IN\s+(?:ALL|EVERY)\s+RESPECT',
            "全好式主观条款",
            "使用'GOOD IN ALL RESPECT'等笼统措辞，缺乏具体判断标准。",
            "要求替换为可量化的具体指标。",
        ),
        (
            r'(?:SHIPPING\s+)?SAMPLES?\s+(?:MUST|TO\s+BE)\s+(?:SENT|FORWARDED|DISPATCHED)\s+(?:TO\s+)?(?:APPLICANT|BUYER)',
            "样品须先寄申请人",
            "要求在装运前或装运后将样品寄送给申请人，可能导致申请人以样品为由拖延或拒绝。",
            "明确样品审核时限（如'WITHIN 5 DAYS AFTER RECEIPT'），超时视为默认合格。",
        ),
        (
            r'(?:PAYMENT|NEGOTIATION)\s+(?:WILL\s+BE)?\s*(?:EFFECTED|MADE)?.*?'
            r'(?:UPON\s+RECEIPT|SUBJECT TO|CONDITIONAL\s+UPON|ONLY\s+AFTER).*?'
            r'(?:APPLICANT|BUYER)',
            "付款条件依赖于申请人行为",
            "付款/议付条件与申请人的行为挂钩，而非单纯基于单据相符性。",
            "审查此条款是否实质上改变了信用证的独立性原则。如确有问题，要求删除。",
        ),
    ]

    full_47a_text = clauses.get("47A", "")
    for pattern, short_desc, detail_desc, suggestion in soft_patterns:
        if re.search(pattern, full_47a_text, re.IGNORECASE | re.DOTALL):
            # 提取匹配片段作为原文摘录
            m = re.search(pattern, full_47a_text, re.IGNORECASE | re.DOTALL)
            snippet = m.group(0)[:180] if m else full_47a_text[:180]

            found.append(_make_anomaly(
                "T5-疑似软条款", "47A",
                snippet,
                f"[{short_desc}] {detail_desc}",
                suggestion,
                "high"))


# ===== T6 检测函数 =====

def _check_t6_doc_conflict(found, clauses, cu):
    """T6: 46A单据要求与47A附加条件之间的潜在冲突"""
    doc_46a = clauses.get("46A", "")
    cond_47a = clauses.get("47A", "")
    if not doc_46a or not cond_47a:
        return

    conflicts = []

    # 46A要求正本 but 47A说只需副本
    if re.search(r'\bORIGINAL\b', doc_46a.upper()) and \
       re.search(r'(?:COPY|COPIES?)\s+ONLY|(?:NO\s+)?ORIGINAL\s+(?:NOT\s+)?REQUIRED|COPY\s+SUFFICIENT',
                 cond_47a):
        conflicts.append("46A要求正本(ORIGINAL)，但47A似乎接受仅副本(COPY ONLY)")

    # 46A没提保险 but 47A有详细保险要求
    if not re.search(r'INSURANCE|POLICY|COVER NOTE', doc_46a.upper()) and \
       re.search(r'INSURANCE', cond_47a):
        conflicts.append("46A未列入保险单据，但47A有详细的保险要求")

    # 46A没提汇票 but 47A要求汇票
    has_draft_in_46a = bool(re.search(r'DRAFT|BILL\s+OF\s+EXCHANGE', doc_46a.upper()))
    draft_in_47a = bool(re.search(r'DRAFT|BILL\s+OF\s+EXCHANGE', cond_47a))
    if not has_draft_in_46a and draft_in_47a:
        conflicts.append("46A未要求汇票(DRAFT)，但47A提到了汇票相关内容")

    # 46A要求特定语言 but 47A要求另一语言
    lang_in_46a = re.search(r'(?:IN|WRITTEN)\s+(?:THE\s+)?(ENGLISH|CHINESE|FRENCH|SPANISH|ARABIC)\b', doc_46a, re.I)
    lang_in_47a = re.search(r'(?:IN|WRITTEN)\s+(?:THE\s+)?(ENGLISH|CHINESE|FRENCH|SPANISH|ARABIC)\b', cond_47a, re.I)
    if lang_in_46a and lang_in_47a:
        if lang_in_46a.group(1).upper() != lang_in_47a.group(1).upper():
            conflicts.append(
                f"46A要求用{lang_in_46a.group(1)}制作，但47A要求用{lang_in_47a.group(1)}")

    # 输出发现的冲突
    for conflict_desc in conflicts:
        found.append(_make_anomaly(
            "T6-单据冲突风险", "46A / 47A",
            f"46A excerpt: {doc_46a[:100]}...\n47A excerpt: {cond_47a[:100]}...",
            conflict_desc + "。46A和47A之间的不一致可能在审单时引发不符点。",
            "建议以两个条款中更严格的要求为准来准备单据，或联系开证行统一表述。",
            "medium"))


# ===== T7 检测函数 =====

def _check_t7_ucp_deviation(found, clauses, cu):
    """T7: UCP600 国际惯例偏离检测"""
    deviations = []

    # 7a: 40A 不是 IRREVOCABLE
    form_40a = cu.get("40A", "")
    if "IRREVOCABLE" not in form_40a and form_40a.strip():
        deviations.append((
            "40A",
            clauses.get("40A", ""),
            "信用证形式(40A)并非'IRREVOCABLE'(不可撤销)。可撤销信用证意味着开证行可以在不通知受益人的情况下随时修改或撤销。",
            "强烈建议要求修改为'IRREVOCABLE'。可撤销信用证对受益人几乎无保护作用。",
            "critical"
        ))

    # 7b: 到期地点不在通知行/指定银行所在国
    # （已在T2-c中部分覆盖，此处侧重于UCP600合规角度）

    # 7c: 交单期超过21天（UCP600第14条c款上限是21天，但实务中常见30天）
    pres = clauses.get("48", "")
    pres_m = re.search(r'(\d+)\s*DAYS?', pres, re.I) if pres else None
    if pres_m and int(pres_m.group(1)) > 21:
        days = int(pres_m.group(1))
        deviations.append((
            "48",
            pres,
            f"交单期(48)规定为{days}天，超过了UCP600第14条c款的默认21天限制。虽然UCP600允许L/C另行规定更长期间，但超过21天的交单期在实践中较少见。",
            f"确认{days}天交单期是否为开证行的真实意图。如果是，确保所有参与方知晓此非标准条款。",
            "low"
        ))

    # 7d: 包含 "UNLESS OTHERWISE STIPULATED IN THE CREDIT" 类型的排除UCP适用
    all_clause_text = " ".join(v for v in clauses.values() if isinstance(v, str))
    if re.search(r'(?:(?:NOT|EXCLUDED|NOT\s+APPLICABLE|SUBJECT\s+TO).{0,30}(?:UCP|UNIFORM|ARTICLE))|'
                 r'(UCP.{0,20}(?:DOES\s+NOT\s+APPLY|EXCEPT|NOT\s+BINDING))',
                 all_clause_text, re.I):
        deviations.append((
            "General",
            "[见条款原文]",
            "信用证中出现排除或修改UCP600适用的条款表述。这可能改变了某些UCP600默认规则的效力。",
            "仔细阅读该排除条款的范围和影响，特别关注其是否排除了对受益人有利的保护条款。",
            "medium"
        ))

    for field, orig_text, desc, sug, sev in deviations:
        found.append(_make_anomaly(
            "T7-UCP600偏离", field, orig_text, desc, sug, sev))


# ===== 工具函数 =====

def _make_anomaly(atype, fields, original_text, description, suggestion, severity):
    """构造标准化的异常记录dict"""
    return {
        "anomaly_type": atype,
        "fields": fields,
        "original_text": original_text,
        "description": description,
        "suggestion": suggestion,
        "severity": severity,
    }


# ==============================================================================
#  第六章：风险矩阵（增强版）— 业务风险视角，4列表格
# ==============================================================================

# ---- 风险维度配置常量 ----

RISK_CATEGORIES = {
    "time":      {"label_cn": "时间风险",       "icon": "[T]",   "color": C.AMBER_BD,  "bg": C.AMBER_BG},
    "payment":   {"label_cn": "收汇风险",       "icon": "[$]",   "color": C.RED_BD,     "bg": C.RED_BG},
    "operation": {"label_cn": "操作风险",       "icon": "[O]",   "color": C.AMBER_BD,  "bg": C.AMBER_BG},
    "compliance":{"label_cn": "合规风险",       "icon": "[R]",   "color": C.RED_BD,     "bg": C.RED_BG},
    "financial": {"label_cn": "财务风险",       "icon": "[$]",   "color": C.RED_BD,     "bg": C.RED_BG},
    "document":  {"label_cn": "单据风险",       "icon": "[D]",   "color": C.AMBER_BD,  "bg": C.AMBER_BG},
}

RISK_SEVERITY_CONFIG = {
    "critical": {"order": 4, "label": "CRITICAL", "color": "#7F1D1D", "bd": C.RED_BD, "bg": "#FEE2E2"},
    "high":     {"order": 3, "label": "HIGH",   "color": "#DC2626", "bd": C.RED_BD, "bg": "#FEE2E2"},
    "medium":   {"order": 2, "label": "MEDIUM",  "color": "#D97706", "bd": C.AMBER_BD,"bg": "#FEF3C7"},
    "low":      {"order": 1, "label": "LOW",     "color": "#059669", "bd": C.GREEN_BD,"bg": "#D1FAE5"},
}


def _build_chapter6_risk_matrix(story, S, analysis, clauses, anomalies):
    """
    第六章：风险矩阵 / Risk Matrix — 增强版4列业务风险表格

    列结构:
      \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u252c\u2500\u2500\u2500\u2500\u2500\u2500\u252c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u252c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
      \u2502 \u98ce\u9e9a\u9879\u76ee  \u2502 \u4e25\u91cd\u5ea6 \u2502 \u6765\u6e90\u5b57\u6bb5 \u2502   \u8bf4\u660e              \u2502
      \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2534\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2534\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2534\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518

    增强特性:
      - 12+ 维度风险扫描引擎（业务视角，非重复第五章的条款矛盾）
      - 每个风险项带 0-100 分量化评分
      - 综合风险得分 & 热力统计面板
      - 按 severity 降序排列，高危行红色背景高亮
      - 与第五章 V2 异常引擎联动（复用检测结果）
    """
    story.append(Paragraph("六、风险矩阵 / Risk Matrix", S["h1"]))

    # ---- 执行全面风险扫描 ----
    risk_items = _scan_risk_items(analysis, clauses, anomalies)

    # ---- 无风险时快速返回 ----
    if not risk_items:
        story.append(note_box(
            "[OK] 未检测到显著风险",
            "本信用证条款经 12+ 维度业务风险扫描后，"
            "未发现时间/收汇/操作/合规/财务/单据类型的高风险。<br/><br/>"
            "<i>注：风险矩阵从业务视角出发，专注于实际操作中可能遇到的困难。</i>",
            "success"
        ))
        return

    # ---- 综合风险统计面板 ----
    _render_risk_stats_panel(story, S, risk_items)
    story.append(Spacer(1, 2*mm))

    # ---- 按 severity + score 降序排列 ----
    def _risk_sort_key(ri):
        sev_cfg = RISK_SEVERITY_CONFIG.get(ri.get("severity", "low"), {})
        return (-sev_cfg.get("order", 0), -ri.get("score", 0))

    risk_items.sort(key=_risk_sort_key)

    # ---- 渲染4列主表格 ----
    _render_risk_matrix_table(story, S, risk_items)

    # ---- 底部风险应对策略汇总 ----
    _render_risk_mitigation_summary(story, S, risk_items)


def _render_risk_stats_panel(story, S, risk_items):
    """渲染综合风险统计面板 — 得分 + 等级分布 + 类别热力图"""
    total = len(risk_items)

    # 综合风险得分 (加权平均)
    if total > 0:
        weighted_sum = sum(ri.get("score", 50) * _severity_weight(ri.get("severity", "low")) for ri in risk_items)
        weight_sum = sum(_severity_weight(ri.get("severity", "low")) for ri in risk_items)
        overall_score = int(weighted_sum / weight_sum) if weight_sum > 0 else 0
    else:
        overall_score = 0

    # 等级分布
    sev_counts = {}
    for sev_key in ["critical", "high", "medium", "low"]:
        cnt = sum(1 for ri in risk_items if ri.get("severity") == sev_key)
        if cnt > 0:
            sev_counts[sev_key] = cnt

    # 类别分布
    cat_counts = {}
    for ri in risk_items:
        cat = ri.get("category", "operation")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    # 最高风险项预览
    top_risks = sorted(risk_items, key=lambda r: r.get("score", 0), reverse=True)[:3]

    lines = []

    # Line 1: 综合得分 + 总数
    score_color = _score_color(overall_score)
    lines.append(
        _bf(f"综合风险得分: ")
        + f"<font color='{score_color}' size='11'><b>{overall_score}/100</b></font>"
        + f"  |  "
        + _bf(f"共 {total} 项风险")
    )

    # Line 2: 等级分布
    sev_parts = []
    for sev_key in ["critical", "high", "medium", "low"]:
        if sev_key in sev_counts:
            cfg = RISK_SEVERITY_CONFIG[sev_key]
            sev_parts.append(
                f"<font color='{cfg['color']}'><b>{cfg['label']}: {sev_counts[sev_key]}</b></font>"
            )
    lines.append(_bf("等级分布:") + "  " + "  ".join(sev_parts))

    # Line 3: 类别分布
    cat_parts = []
    sorted_cats = sorted(cat_counts.items(), key=lambda x: -x[1])
    for cat, cnt in sorted_cats:
        cat_cfg = RISK_CATEGORIES.get(cat, {})
        cat_label = cat_cfg.get("label_cn", cat)
        cat_icon = cat_cfg.get("icon", "?")
        cat_parts.append(f"{cat_icon}{cat_label}({cnt})")
    lines.append(_bf("类别分布:") + "  " + ", ".join(cat_parts))

    # 用 info box 展示
    content = "<br/>".join(lines)
    story.append(box_para(Paragraph(content, S["body"]), C.LIGHT_BLUE, C.BLUE))


def _render_risk_matrix_table(story, S, risk_items):
    """渲染4列风险矩阵主表格"""
    header_row = [
        Paragraph("<b>风险项目</b>", S["th"]),
        Paragraph("<b>严重度</b>", S["th"]),
        Paragraph("<b>来源字段</b>", S["th"]),
        Paragraph("<b>说明</b>", S["th"]),
    ]

    rows = [header_row]

    for ri in risk_items:
        # Col 1: 风险项目名称 + 类别图标
        cat = ri.get("category", "operation")
        cat_cfg = RISK_CATEGORIES.get(cat, {})
        cat_icon = cat_cfg.get("icon", "")
        item_name = ri.get("name", "未知风险")
        score_val = ri.get("score", 50)
        col1_html = f"{cat_icon} <b>{_esc(item_name)}</b><br/><font size='7' color='#6B7280'>Score:{score_val}/100</font>"
        col1 = Paragraph(col1_html, S["body"])

        # Col 2: 严重度标签
        sev = ri.get("severity", "low")
        sev_cfg = RISK_SEVERITY_CONFIG.get(sev, RISK_SEVERITY_CONFIG["low"])
        col2 = tag_cell(sev_cfg["label"], sev_cfg["bd"], C.WHITE)

        # Col 3: 来源SWIFT字段号
        fields_val = ri.get("fields", "-")
        col3 = Paragraph(str(fields_val), S["tc"])

        # Col 4: 详细说明（含影响描述）
        desc_text = ri.get("description", "")
        impact = ri.get("impact", "")
        body_html = _esc(desc_text[:220])
        if impact:
            body_html += f"<br/><br/><font color='#4B5563' size='7.5'>Impact: {_esc(impact[:120])}</font>"
        col4 = Paragraph(body_html, S["bl"])

        row_data = [col1, col2, col3, col4]
        rows.append(row_data)

    # 表格样式
    # A4 可用宽度 = 174mm; 分配: 风险项目36 | 严重度15 | 来源17 | 剩余106 = 174mm
    col_widths = [34*mm, 14*mm, 16*mm, 100*mm]
    t = Table(rows, colWidths=col_widths)

    base_style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), hex_color(C.NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), hex_color(C.WHITE)),
        ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.NAVY)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]

    # 斑马纹 + 高危行特殊背景
    for i in range(1, len(rows)):
        ri_item = risk_items[i - 1] if i - 1 < len(risk_items) else {}
        sev_raw = ri_item.get("severity", "")

        if sev_raw in ("critical", "high"):
            base_style.append(("BACKGROUND", (0, i), (-1, i), hex_color(C.RED_BG)))
        elif i % 2 == 0:
            base_style.append(("BACKGROUND", (0, i), (-1, i), hex_color(C.LGREY)))
        else:
            base_style.append(("BACKGROUND", (0, i), (-1, i), hex_color(C.WHITE)))

    t.setStyle(TableStyle(base_style))
    story.append(t)


def _render_risk_mitigation_summary(story, S, risk_items):
    """渲染底部风险应对策略汇总 — 仅显示 high/critical 项的操作建议"""
    priority_items = [ri for ri in risk_items if ri.get("severity") in ("critical", "high")]

    if not priority_items:
        return

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(_bf("[!] 必须在发走前应对的风险:"), S["h2"]))

    for i, ri in enumerate(priority_items):
        name = ri.get("name", "")
        desc = ri.get("description", "")[:200]
        mitigation = ri.get("mitigation", ri.get("suggestion", ""))
        sev = ri.get("severity", "high")

        body = f"<b>[#{i+1}] {_esc(name)}</b>"
        body += f"<br/>{_esc(desc)}"
        if mitigation:
            body += f"<br/><br/>[>] <b>应对措施:</b> {_esc(mitigation[:180])}"

        level = "danger" if sev == "critical" else "warning"
        story.append(note_box(f"高优先级 #{i+1}", body, level))
        story.append(Spacer(1, 2*mm))


# ==============================================================================
#  风险扫描引擎（12+ 维度，业务视角）
# ==============================================================================

def _scan_risk_items(analysis, clauses, anomalies):
    """
    全方位风险扫描引擎 — 从业务操作角度识别12类风险。

    返回 list[dict]，每项包含:
      - name: str          风险项中文名称
      - category: str      风险类别 (time/payment/operation/compliance/financial/document)
      - severity: str      严重度 (critical/high/medium/low)
      - score: int         0-100分量化评分
      - fields: str        来源SWIFT字段号
      - description: str   风险详细说明
      - impact: str        业务影响描述
      - mitigation: str    应对措施建议
    """
    found = []
    cu = {}  # 大写缓存
    for k in clauses:
        cu[k] = str(clauses.get(k, "")).upper()

    cond_47a = cu.get("47A", "")

    # ══════════════════════════════════════
    # R1: 时间风险类
    # ══════════════════════════════════════

    # R1-a: 有效期极短 (<30天)
    issue_dt = analysis.get("issue_date", "")
    exp_dt = analysis.get("expiry_date", "")
    if issue_dt and exp_dt:
        gap = _days_between(issue_dt, exp_dt)
        if gap is not None and gap < 30 and gap > 0:
            urgency = "\u6781\u5ea6\u7d27\u5f20" if gap < 15 else "\u7d27\u5f20"
            score = 95 if gap < 15 else (80 if gap < 21 else 65)
            sev = "critical" if gap < 15 else "high"
            found.append(_make_risk(
                "\u4fe1\u7528\u8bc1\u6709\u6548\u671f\u6781\u77ed", "time", sev, score,
                "31C / 31D",
                f"\u4ece\u5f00\u8bc1\u65e5\u5230\u5230\u671f\u65e5\u4ec5 <b>{gap}</b> \u5929\uff0c{urgency}\u3002"
                f"\u6b63\u5e38\u8d38\u6613\u6d41\u7a0b\u9700\u751f\u4ea7+\u8ba2\u8231+\u88c5\u8fd0+\u5236\u5355+\u5bc4\u9001\uff0c\u65f6\u95f4\u6781\u96be\u6ee1\u8db3\u3002",
                "\u53ef\u80fd\u5bfc\u81f4\u65e0\u6cd5\u5728\u6709\u6548\u671f\u5185\u5b8c\u6210\u88c5\u8fd0\u548c\u4ea4\u5355\uff0c\u8d39\u7528\u6d41\u5931\u3002",
                "\u5f3a\u70c8\u5efa\u8bae\u7acb\u5373\u7533\u8bf7\u5ef6\u957f\u6709\u6548\u671f\u81f3\u5c11 60 \u5929\u4ee5\u4e0a\u3002"
            ))

    # R1-b: 装船-到期间隔紧
    ship_raw = clauses.get("44C", "")
    exp_raw = clauses.get("31D", "")
    ship_m = re.search(r'(\d{6})', ship_raw)
    exp_m = re.search(r'(\d{6})', exp_raw)
    if ship_m and exp_m:
        try:
            from datetime import date as _d
            ss = ship_m.group(1); es = exp_m.group(1)
            gd = (_d(2000+int(es[:2]), int(es[2:4]), int(es[4:6])) -
                  _d(2000+int(ss[:2]), int(ss[2:4]), int(ss[4:6]))).days
            if 0 <= gd < 21:
                score = 90 if gd < 10 else (75 if gd < 16 else 55)
                sev = "critical" if gd < 10 else ("high" if gd < 16 else "medium")
                found.append(_make_risk(
                    "\u88c5\u8239\u65e5-\u5230\u671f\u65e5\u95f4\u9694\u6781\u7d27", "time", sev, score,
                    "44C / 31D",
                    f"\u6700\u8fdf\u88c5\u8239\u65e5({_format_date_yymmdd(ss)})\u4e0e\u5230\u671f\u65e5({_format_date_yymmdd(es)})\u4e4b\u95f4\u4ec5\u95f4\u9694\u7ea6 <b>{gd}</b> \u5929\u3002",
                    "\u6263\u9664\u5236\u5355\u548c\u5bc4\u9001\u65f6\u95f4\u540e\u51e0\u4e4e\u6ca1\u6709\u7f13\u51b2\u4f59\u5730\uff0c\u4efb\u4f55\u73af\u8282\u5ef6\u8bef\u90fd\u53ef\u80fd\u5bfc\u81f4\u4ea4\u5355\u8d85\u671f\u3002",
                    "\u5efa\u8bae\u7533\u8bf7\u5ef6\u5c55\u6709\u6548\u671f\uff0c\u4f7f\u95f4\u9694\u81f3\u5c11\u4fdd\u6301 21 \u5929\u4ee5\u4e0a\u3002"
                ))
        except (ValueError, IndexError):
            pass

    # R1-c: 交单期偏短 (<14天)
    pres = clauses.get("48", "")
    pres_m = re.search(r'(\d+)\s*DAYS?', pres, re.I) if pres else None
    if pres_m and int(pres_m.group(1)) < 14:
        days = int(pres_m.group(1))
        score = 70 if days < 7 else 55
        found.append(_make_risk(
            "\u4ea4\u5355\u671f\u504f\u77ed", "time", "medium", score,
            "48",
            f"\u4ea4\u5355\u671f(48)\u4ec5 <b>{days}</b> \u5929\u3002UCP600 \u9ed8\u8ba4 21 \u5929\uff0c\u8fc7\u77ed\u7684\u4ea4\u5355\u671f\u5bf9\u5355\u636e\u5236\u4f5c\u3001\u5ba1\u6838\u3001\u66f4\u6b63\u90fd\u662f\u6311\u6218\u3002",
            "\u5982\u679c\u88c5\u8239\u540e\u5355\u636e\u4fee\u6539\u3001\u8865\u8bc1\u7b49\u9700\u8981\u989d\u5916\u65f6\u95f4\uff0c\u5bb9\u6613\u8d85\u8fc7\u4ea4\u5355\u671f\u9650\u3002",
            "\u63d0\u524d\u51c6\u5907\u597d\u6240\u6709\u5355\u636e\u6a21\u677f\uff0c\u786e\u4fdd\u88c5\u8239\u540e\u5feb\u901f\u5b8c\u6210\u5236\u5355\u3002"
        ))

    # ══════════════════════════════════════
    # R2: 收汇风险类
    # ══════════════════════════════════════

    # R2-a: 到期地在境外
    exp_place = analysis.get("expiry_place", "")
    beneficiary = analysis.get("beneficiary", "")
    if exp_place and beneficiary and exp_place.upper() not in beneficiary.upper():
        cn_kws = ["CHINA", "PRC", "BEIJING", "SHANGHAI", "GUANGZHOU", "SHENZHEN"]
        is_abroad = not any(kw in exp_place.upper() for kw in cn_kws)
        score = 85 if is_abroad else 60
        sev = "high" if is_abroad else "medium"
        location_tag = "\u5883\u5916" if is_abroad else "\u5f02\u5730"
        found.append(_make_risk(
            "\u5230\u671f\u5730\u5728\u53d7\u76ca\u4eba\u56fd\u5916", "payment", sev, score,
            "31D",
            f"\u5230\u671f\u5730\u4e3a <b>{_esc(exp_place)}</b>\uff08{location_tag}\uff09\uff0c\u800c\u53d7\u76ca\u4eba\u4f4d\u4e8e {_esc(beneficiary[:50])}\u3002",
            f"\u8de8\u5883/\u5f02\u5730\u4ea4\u5355\u9700\u989d\u5916\u90ae\u5bc4\u65f6\u95f4\uff0c\u589e\u52a0\u665a\u5230\u98ce\u9669\u3002\u5982\u679c\u90ae\u4ef6\u5728\u6708\u672a\u5230\u8fbe\uff0c\u5c06\u5bfc\u81f4\u4ea4\u5355\u88ab\u62d2\u3002",
            f"\u786e\u8ba4\u4ece\u53d7\u76ca\u4eba\u5230\u5230\u671f\u5730\u7684\u90ae\u5bc4\u5929\u6570\uff08\u542b\u6e05\u5173\uff09\uff0c\u9884\u7559\u81f3\u5c11 7 \u5929\u4f59\u91cf\u3002"
            f"\u5982\u53ef\u80fd\uff0c\u5efa\u8bae\u5c06\u5230\u671f\u5730\u6539\u4e3a\u53d7\u76ca\u4eba\u6240\u5728\u56fd\u3002"
        ))

    # R2-b: 非IRREVOCABLE形式
    form_40a = cu.get("40A", "") or cu.get("40B", "")
    if form_40a and "IRREVOCABLE" not in form_40a:
        found.append(_make_risk(
            "\u4fe1\u7528\u8bc1\u975e\u4e0d\u53ef\u64a4\u9500", "payment", "critical", 98,
            "40A / 40B",
            f"\u4fe1\u7528\u8bc1\u5f62\u5f0f\u4e3a '{clauses.get('40A', clauses.get('40B', ''))}'\uff0c"
            f"\u5e76\u975e IRREVOCABLE\uff08\u4e0d\u53ef\u64a4\u9500\uff09\u3002",
            "\u5f00\u8bc1\u884c\u53ef\u4ee5\u5728\u4e0d\u901a\u77e5\u53d7\u76ca\u4eba\u7684\u60c5\u51b5\u4e0b\u968f\u65f6\u4fee\u6539\u6216\u64a4\u9500\u4fe1\u7528\u8bc1\uff0c\u53d7\u76ca\u4eba\u6743\u76ca\u51e0\u4e4e\u96f6\u4fdd\u62a4\u3002",
            "\u5f3a\u70c8\u5efa\u8bae\u8981\u6c42\u4fee\u6539\u4e3a 'IRREVOCABLE'\uff0c\u5426\u5219\u4e0d\u5efa\u8bae\u64cd\u4f5c\u6b64\u4fe1\u7528\u8bc1\u3002"
        ))

    # R2-c: 转让条款限制
    transferrable = clauses.get("47", "") or ""
    if "TRANSFERABLE" not in transferrable.upper() and "WITHOUT" not in cu.get("49", ""):
        # 不是可转让且未明确禁止 — 中等提示
        pass  # 不作为风险项，只是信息

    # ══════════════════════════════════════
    # R3: 操作风险类
    # ══════════════════════════════════════

    # R3-a: 软条款存在（从V2引擎获取）
    soft_count = sum(1 for a in (anomalies or []) if "T5" in str(a.get("anomaly_type", "")))
    if soft_count > 0:
        score = min(80 + soft_count * 5, 98)
        sev = "critical" if soft_count >= 3 else ("high" if soft_count >= 2 else "medium")
        found.append(_make_risk(
            f"\u68c0\u6d4b\u5230 {soft_count} \u9879\u7591\u4f3c\u8f6f\u6761\u6b3e", "operation", sev, score,
            "47A",
            f"\u5728 47A \u9644\u52a0\u6761\u6b3e\u4e2d\u68c0\u6d4b\u5230 {soft_count} \u9879\u53ef\u80fd\u7684\u8f6f\u6761\u6b3e\uff08"
            f"\u5982\u7533\u8bf7\u4eba\u7b7e\u53d1\u68c0\u9a8c\u8bc1\u4e66\u3001\u9700\u7533\u8bf7\u4eba\u786e\u8ba4\u7b49\uff09\u3002",
            "\u8f6f\u6761\u6b3e\u8d4b\u4e88\u7533\u8bf7\u4eba\u5355\u65b9\u9762\u62d2\u7edd\u4ed8\u6b3e\u7684\u6743\u529b\uff0c\u53d7\u76ca\u4eba\u65e0\u6cd5\u81ea\u4e3b\u63a7\u5236\u4ea4\u5355\u7ed3\u679c\u3002",
            "\u5f3a\u70c8\u5efa\u8bae\u5728\u53d1\u8d70\u524d\u8981\u6c42\u5220\u9664\u6216\u4fee\u6539\u8f6f\u6761\u6b3e\u3002\u82e5\u5f00\u8bc1\u884c\u62d2\u7edd\uff0c\u5e94\u91cd\u65b0\u8bc4\u4f30\u662f\u5426\u63a5\u5355\u3002"
        ))

    # R3-b: 分批装运矛盾（从V2引擎映射）
    partial_issues = [a for a in (anomalies or []) if "T1" in str(a.get("anomaly_type", ""))
                      and "PARTIAL" in str(a.get("original_text", "")).upper()]
    if partial_issues:
        found.append(_make_risk(
            "\u5206\u6279\u88c5\u8fd0\u6761\u6b3e\u77db\u76fe", "operation", "high", 78,
            "43P / 47A",
            "\u5206\u6279\u88c5\u8fd0\u8981\u6c42\u5728 43P \u4e0e 47A \u4e4b\u95f4\u5b58\u5728\u77db\u76fe\u8868\u8ff0\u3002",
            "\u5982\u679c\u5b9e\u9645\u64cd\u4f2d\u4e2d\u9700\u8981\u5206\u6279\u88c5\u8fd0\uff0c\u53ef\u80fd\u5bfc\u81f4\u5355\u636e\u88ab\u8ba4\u5b9a\u4e3a\u4e0d\u7b26\u70b9\u3002",
            "\u5fc5\u987b\u4e0e\u5f00\u8bc1\u884c\u66f7\u6e05\u771f\u610f\u56fe\uff1a\u5171\u7adf\u5141\u8bb8\u8fd8\u662f\u7981\u6b62\u5206\u6279\uff1f\u4ee5\u54ea\u4e2a\u6761\u6b3e\u4e3a\u51c6\uff1f"
        ))

    # R3-c: 货物描述模糊
    goods_desc = analysis.get("goods_description", "")
    if goods_desc and len(goods_desc) < 30:
        found.append(_make_risk(
            "\u8d27\u7269\u63cf\u8ff0\u8fc7\u7b80\u6216\u6a21\u7cca", "operation", "medium", 50,
            "45A",
            f"\u8d27\u7269\u63cf\u8ff0(45A)\u5185\u5bb9\u8fc7\u7b80\uff1a'{_esc(goods_desc)}'\u3002",
            "\u6a21\u7cca\u7684\u8d27\u7269\u63cf\u8ff0\u53ef\u80fd\u5bfc\u81f4\u5236\u5355\u65f6\u53d1\u7968/\u7bb1\u5355\u4e0e\u5b9e\u9645\u88c5\u8fd0\u8d27\u7269\u4e0d\u5339\u914d\u3002",
            "\u786e\u8ba4\u5408\u540c\u4e2d\u7684\u8d27\u7269\u8be6\u7ec6\u89c4\u683c\uff0c\u5236\u5355\u65f6\u4fdd\u6301\u4e00\u81f4\u6027\u3002"
        ))

    # ══════════════════════════════════════
    # R4: 合规风险类
    # ══════════════════════════════════════

    # R4-a: 制裁/禁运国家
    all_text_lower = " ".join(str(v).lower() for v in clauses.values())
    sanction_keywords = ["iran", "north korea", "syria", "crimea", "cuban", "sudan", "donetsk"]
    detected_sanctions = [kw for kw in sanction_keywords if kw in all_text_lower]
    if detected_sanctions:
        found.append(_make_risk(
            "\u53ef\u80fd\u6d89\u53ca\u5236\u88c1/\u7981\u8fd0\u56fd\u5bb6\u6216\u5730\u533a", "compliance", "critical", 99,
            "Multiple",
            f"\u68c0\u6d4b\u5230\u53ef\u80fd\u6d89\u53ca\u5236\u88c1\u7684\u5173\u952e\u8bcd: {', '.join(detected_sanctions)}\u3002",
            "\u6d89\u53ca\u5236\u88c1\u56fd\u5bb6/\u5730\u533a\u7684\u8d38\u6613\u53ef\u807d\u4ee4\u4f01\u4e1a\u906d\u5230\u91d1\u878d\u5236\u88c1\uff0c\u94f6\u884c\u53ef\u80fd\u62d2\u7edd\u529e\u7406\u3002",
            "\u7acb\u5373\u505c\u6b62\u64cd\u4f5c\u5e76\u5411\u5408\u89c4\u90e8\u95e8\u54a8\u8be2\uff0c\u786e\u8ba4\u662f\u5426\u5728\u5236\u88c1\u8303\u56f4\u5185\u3002"
        ))

    # R4-b: UCP600偏离（从V2引擎映射）
    ucp_devs = [a for a in (anomalies or []) if "T7" in str(a.get("anomaly_type", ""))]
    if ucp_devs:
        dev_titles = [a.get("description", "")[:60] for a in ucp_devs[:3]]
        found.append(_make_risk(
            f"\u5b58\u5728 UCP600 \u504f\u79bb\u6761\u6b3e ({len(ucp_devs)}\u9879)", "compliance",
            "medium" if len(ucp_devs) <= 1 else "high",
            50 + len(ucp_devs) * 10,
            "Multiple / 47A",
            f"\u4fe1\u7528\u8bc1\u4e2d\u542b\u6709 {len(ucp_devs)} \u9879\u4e0e UCP600 \u56fd\u9645\u60ef\u4f8b\u504f\u79bb\u7684\u6761\u6b3e\u3002"
            f"; ".join(dev_titles),
            "\u504f\u79bb\u6761\u6b3e\u53ef\u807d\u6539\u53d8\u67d0\u4e9b UCP600 \u9ed8\u8ba4\u89c4\u5219\u7684\u6548\u529b\uff0c\u5f71\u54cd\u53d7\u76ca\u4eba\u6743\u76ca\u3002",
            "\u4ed4\u7ec6\u9605\u8bfb\u6bcf\u4e2a\u504f\u79bb\u6761\u6b3e\u7684\u8303\u56f4\u548c\u5f71\u54cd\uff0c\u7279\u522b\u5173\u6ce8\u662f\u5426\u6392\u9664\u4e86\u5bf9\u53d7\u76ca\u4eba\u6709\u5229\u7684\u4fdd\u62a4\u6761\u6b3e\u3002"
        ))

    # ══════════════════════════════════════
    # R5: 财务风险类
    # ══════════════════════════════════════

    # R5-a: 自动扣款/罚金
    if re.search(r'(AUTOMATIC\s+(?:DEDUCTION|WITHHOLDING)|PENALTY|DEDUCT\s*\d+%|\d+%\s*PENALTY)', cond_47a):
        found.append(_make_risk(
            "\u542b\u81ea\u52a8\u6263\u6b3e/\u7f5a\u91d1\u6761\u6b3e", "financial", "high", 80,
            "47A",
            "47A \u5305\u542b\u81ea\u52a8\u6263\u6b3e(AUTOMATIC DEDUCTION)\u3001\u7f5a\u91d1(PENALTY)\u6216\u767e\u5206\u6bd4\u6263\u51cf\u6761\u6b3e\u3002",
            "\u5b9e\u9645\u6536\u6b3e\u91d1\u989d\u5c06\u4f4e\u4e8e L/C \u9762\u989d\uff0c\u53ef\u807d\u5f71\u54cd\u5229\u6da6\u7387\u751a\u81f3\u4e8f\u635f\u3002",
            "\u5fc5\u987b\u7cbe\u786e\u8ba1\u7b97\u6263\u6b3e\u91d1\u989d\u5bf9\u5229\u6da6\u7684\u5f71\u54cd\uff0c\u5982\u4e0d\u53ef\u63a5\u53d7\u5e94\u5728\u53d1\u8d70\u524d\u7533\u8bf7\u5220\u9664\u3002"
        ))

    # R5-b: 受益人承担费用
    charge_combined = (clauses.get("71B", "") + " " + clauses.get("71D", "")).upper()
    if ("BENEFICIARY" in charge_combined and "ACCOUNT" in charge_combined) or \
       "ALL BANKING CHARGES OUTSIDE" in charge_combined:
        found.append(_make_risk(
            "\u90e8\u5206\u6216\u51616\u90e8\u94f6\u884c\u8d39\u7528\u8f6c\u5ac1\u53d7\u76ca\u4eba", "financial", "medium", 55,
            "71B / 71D",
            "\u8d39\u7528\u627f\u62c5\u6761\u6b3e(71B/71D)\u8868\u660e\u5883\u5916\u94f6\u884c\u8d39\u7528\u7531\u53d7\u76ca\u4eba\u627f\u62c5\u3002",
            "\u589e\u52a0\u4ea4\u6613\u6210\u672c\uff0c\u901a\u5e38\u5883\u5916\u94f6\u884c\u8d39\u7528\u7ea6 USD 50-200/\u7b14\u3002",
            "\u9884\u4f30\u989d\u5916\u8d39\u7528\u5e76\u8ba5\u5165\u6210\u672c\u6838\u7b97\u3002"
        ))

    # R5-c: 金额容差异常
    tol_39a = clauses.get("39A", "").strip()
    if tol_39a:
        # 解析容差值
        tol_m = re.search(r'(\d{2})/(\d{2})', tol_39a)
        if tol_m:
            pct = int(tol_m.group(1))
            if pct >= 20:
                found.append(_make_risk(
                    f"\u6ea2\u77ed\u88c5\u5bb9\u5dee\u8fbe \xb1{pct}% (\u8f83\u5927)", "financial", "medium", 52,
                    "39A",
                    f"39A \u89c4\u5b9a\u7684\u6ea2\u77ed\u88c5\u5bb9\u5dee\u4e3a \xb1{pct}%\uff0c\u8d85\u8fc7\u5e38\u89c1\u7684 \xb15% \u6c34\u5e73\u3002",
                    "\u5927\u5bb9\u5dee\u610f\u5473\u7740\u53d1\u7968\u91d1\u989d\u53ef\u6d6e\u52a8\u8303\u56f4\u8f83\u5927\uff0c\u5bf9\u8d44\u91d1\u56de\u7b97\u6709\u5f71\u54cd\u3002",
                    "\u786e\u8ba4\u662f\u5426\u771f\u7684\u9700\u8981\u8fd9\u4e59\u5927\u7684\u5bb9\u5dee\u7a7a\u95f4\u3002"
                ))

    # ══════════════════════════════════════
    # R6: 单据风险类
    # ══════════════════════════════════════

    # R6-a: 46A vs 47A 冲突（从V2引擎映射）
    doc_conflicts = [a for a in (anomalies or []) if "T6" in str(a.get("anomaly_type", ""))]
    if doc_conflicts:
        found.append(_make_risk(
            f"\u5355\u636e\u8981\u6c42\u5b58\u5728\u5185\u90e8\u51b2\u7a81 ({len(doc_conflicts)}\u9879)", "document",
            "medium", 58,
            "46A / 47A",
            "46A \u5355\u636e\u8981\u6c42\u4e0e 47A \u9644\u52a0\u6761\u4ef6\u4e4b\u95f4\u5b58\u5728\u6f5c\u5728\u4e0d\u4e00\u81f4\u3002",
            "\u5236\u5355\u65f6\u53ef\u80fd\u9646\u5165\u201c\u4ee5\u8c01\u4e3a\u51c6\u201d\u7684\u56f0\u5883\uff0c\u5bb9\u6613\u4ea7\u751f\u4e0d\u7b26\u70b9\u3002",
            "\u5efa\u8bae\u4ee5\u4e24\u4e2a\u6761\u6b3e\u4e2d\u66f4\u4e25\u683c\u7684\u8981\u6c42\u4e3a\u51c6\u6765\u51c6\u5907\u5355\u636e\uff0c\u6216\u8054\u7cfb\u5f00\u8bc1\u884c\u7edf\u4e00\u8868\u8ff0\u3002"
        ))

    # R6-b: 正本单据要求多但无明确签发标准
    doc_46a = clauses.get("46A", "")
    orig_count = len(re.findall(r'\bORIGINAL\b', doc_46a.upper()))
    if orig_count >= 3:
        found.append(_make_risk(
            f"\u8981\u6c42 {orig_count} \u4efd\u6b63\u5355\u5355\u636e", "document", "low", 40,
            "46A",
            f"46A \u8981\u6c42\u63d0\u4ea4 {orig_count} \u4efd\u6b63\u5355\u5355\u636e\uff0c\u5bf9\u7b7e\u53d1\u3001\u516c\u8bc1\u7b49\u8981\u6c42\u8f83\u591a\u3002",
            "\u6b63\u5355\u5355\u636e\u591a\u610f\u5473\u7740\u66f4\u9ad8\u7684\u5236\u5355\u6210\u672c\u548c\u66f4\u957f\u7684\u51c6\u5907\u65f6\u95f4\u3002",
            "\u63d0\u524d\u4e86\u89e3\u6bcf\u4efd\u5355\u636e\u7684\u7b7e\u53d1\u8981\u6c42\u548c\u516c\u8bc1\u9700\u6c42\u3002"
        ))

    # R6-c: 需要第三方证明文件但未指定机构
    third_party_patterns = [
        (r'INSPECTION CERTIFICATE', '\u68c0\u9a8c\u8bc1\u4e66'),
        (r'CERTIFICATE OF ORIGIN', '\u539f\u4ea7\u5730\u8bc1'),
        (r'ANALYSIS CERTIFICATE', '\u5206\u6790\u8bc1\u4e66'),
        (r'WEIGHT LIST / CERTIFICATE', '\u91cd\u91cf\u5355/\u8bc1'),
        (r'HEALTH CERTIFICATE', '\u5065\u5eb7\u8bc1\u4e66'),
        (r'FUMIGATION CERTIFICATE', '\u84b8\u8eb2\u8bc1\u4e66'),
    ]
    for pattern, label in third_party_patterns:
        if re.search(pattern, doc_46a, re.I):
            # 检查是否指定了具体签发机构
            issued_by = re.search(r'ISSUED BY?\s*(.+?)(?:\.|AND|\+|$)', doc_46a, re.I)
            generic_words = ["COMPETENT AUTHORITY", "RECOGNIZED AUTHORITY", "AUTHORITY",
                            "ANY", "APPLICANT"]
            is_generic = False
            if issued_by:
                issuer_upper = issued_by.group(1).strip().upper()
                if any(gw in issuer_upper for gw in generic_words):
                    is_generic = True
            else:
                is_generic = True

            if is_generic:
                found.append(_make_risk(
                    f"{label}\u7b7e\u53d1\u673a\u6784\u672a\u660e\u786e\u6307\u5b9a", "document", "medium", 48,
                    "46A",
                    f"46A \u8981\u6c42\u63d0\u4ea4 {label}\uff0c\u4f46\u672a\u660e\u786e\u6307\u5b9a\u7b7e\u53d1\u673a\u6784\u3002",
                    f"\u4e0d\u660e\u786e\u7684\u7b7e\u53d1\u673a\u6784\u53ef\u80fd\u5bfc\u81f4\u94f6\u884c\u5bf9\u8bc1\u4e66\u7684\u53ef\u63a5\u53d7\u6027\u5b58\u5728\u4e0d\u540c\u89e3\u91ca\u3002",
                    f"\u5efa\u8bae\u4e8e\u5236\u5355\u524d\u786e\u8ba4\u5408\u7406\u7684\u7b7e\u53d1\u673a\u6784\u5e76\u53d6\u5f97\u5176\u786e\u8ba4\u3002"
                ))
                break  # 只报告一个即可避免重复

    # ---- 从第五章V2引擎映射剩余高优异常 ----
    seen_risk_keys = set()
    for ri in found:
        seen_risk_keys.add(ri["name"][:40].lower())

    for a in (anomalies or []):
        sev = str(a.get("severity", "")).lower()
        if sev in ("critical", "high"):
            a_name = str(a.get("anomaly_type", ""))
            a_desc = str(a.get("description", ""))[:60]
            check_key = (a_name + a_desc)[:40].lower()

            if check_key not in seen_risk_keys:
                # 映射到风险类别
                atype_norm = _normalize_anomaly_type({"anomaly_type": a_name})
                cat_map = {
                    "T1-自相矛盾": "operation", "T2-操作不合理": "time",
                    "T3-模糊/不完整": "compliance", "T4-非常规财务": "financial",
                    "T5-疑似软条款": "operation", "T6-单据冲突风险": "document",
                    "T7-UCP600偏离": "compliance",
                }
                risk_cat = cat_map.get(atype_norm, "operation")

                found.append(_make_risk(
                    a_name.replace("T1-", "").replace("T2-", "").replace("T3-", "")
                           .replace("T4-", "").replace("T5-", "").replace("T6-", "")
                           .replace("T7-", ""),
                    risk_cat, sev,
                    70 if sev == "high" else 85,
                    a.get("fields", a.get("clause_ref", "-")),
                    a.get("description", a.get("detail", ""))[:200],
                    a.get("description", "")[:120],
                    a.get("suggestion", "\u53c2\u8003\u4e0a\u8ff0\u5efa\u8bae\u64cd\u4f5c\u3002")
                ))
                seen_risk_keys.add(check_key)

    return found


# ===== 工具函数 =====

def _make_risk(name, category, severity, score, fields, description, impact, mitigation):
    """构造标准化风险记录dict"""
    return {
        "name": name,
        "category": category,
        "severity": severity,
        "score": max(0, min(100, score)),
        "fields": fields,
        "description": description,
        "impact": impact,
        "mitigation": mitigation,
    }


def _severity_weight(severity):
    """返回严重度的权重系数（用于综合得分计算）"""
    weights = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.5}
    return weights.get(severity, 1.0)


def _score_color(score):
    """根据分数返回颜色"""
    if score >= 80: return "#DC2626"   # 红
    if score >= 60: return "#D97706"   # 琥珀
    if score >= 35: return "#059669"   # 绿
    return "#6B7280"                   # 灰


# ---------- 第七章：交单备查清单 ----------

def _build_chapter7_checklist(story, S, analysis, clauses):
    """第七章：交单备查清单 / Compliance Checklist — 按单据分组checkbox格式
    
    按理想模板优化：
    - 按单据类别分组（商业发票/装箱单/提单/通用要求）
    - 条款要求内容截断为合理长度避免溢出
    - 列宽适配A4页面
    """
    story.append(Paragraph("七、交单备查清单 / Compliance Checklist", S["h1"]))

    checklist_items = []

    # --- 从各字段逐条提取明确的交单要求 ---

    # 1. 单据要求 (46A) - 按单据类型展开
    doc_46a = clauses.get("46A", "")
    if doc_46a and doc_46a.strip():
        try:
            from utils.lc_analyzer import parse_doc_list as _pdl2
            docs_p = _pdl2(doc_46a)
        except Exception:
            docs_p = _parse_docs_simple(doc_46a)

        for idx, doc in enumerate(docs_p):
            if isinstance(doc, dict):
                raw = doc.get("raw_content", str(doc))
                dtype = doc.get("type_cn", "其他单据")
                copies = doc.get("copies", "")
                # 组合份数和原文，更清晰
                if copies and copies != "-":
                    display_text = f"[{copies}] {raw[:200]}"
                else:
                    display_text = raw[:250]
            else:
                raw = str(doc)
                dtype = _doc_type_cn(raw[:80])
                display_text = raw[:250]

            checklist_items.append({
                "category": f"单据: {dtype}",
                "requirement": display_text,
                "clause_ref": f"46A 第{idx+1}项",
                "priority": "必须",
            })

    # 2. 运输相关
    transport_fields = [
        ("44E", "装船港/发货地", clauses.get("44E", "")),
        ("44F", "卸货港/目的地", clauses.get("44F", "")),
        ("44C", "最迟装船日", clauses.get("44C", "")),
        ("43P", "分批装运", clauses.get("43P", "")),
        ("43T", "转运", clauses.get("43T", "")),
    ]
    for tag, label, val in transport_fields:
        if val and val.strip():
            checklist_items.append({
                "category": "运输要求",
                "requirement": f"{label}: {_esc(val.strip())}",
                "clause_ref": tag,
                "priority": "必须",
            })

    # 3. 时间要求
    time_fields = [
        ("48", "交单期限", clauses.get("48", "")),
        ("31D", "到期日/地", clauses.get("31D", "")),
    ]
    for tag, label, val in time_fields:
        if val and val.strip():
            checklist_items.append({
                "category": "时间要求",
                "requirement": f"{label}: {_esc(val.strip())}",
                "clause_ref": tag,
                "priority": "必须",
            })

    # 4. 47A 中与交单直接相关的条件
    cond_47a = clauses.get("47A", "")
    if cond_47a and cond_47a.strip():
        doc_kw = ['DOCUMENT', 'PRESENT', 'ISSUED', 'ORIGINAL', 'COPY',
                   'CERTIFICATE', 'ENGLISH', 'ACCEPTABLE']
        seen_47a = set()
        for sub in re.split(r'\n(?=\+)|(?<=\.)\s*(?=\+[A-Z])', cond_47a):
            sub_s = sub.strip()
            if not sub_s or len(sub_s) < 10:
                continue
            sub_u = sub_s.upper()
            if any(kw in sub_u for kw in doc_kw):
                key = sub_s[:50]
                if key not in seen_47a:
                    seen_47a.add(key)
                    checklist_items.append({
                        "category": "附加条件 (47A)",
                        "requirement": sub_s[:200],  # 截断过长文本
                        "clause_ref": "47A",
                        "priority": "必须",
                    })

    # 5. 78 寄单指示（截断过长文本）
    inst_78 = clauses.get("78", "")
    if inst_78 and len(inst_78.strip()) > 10:
        checklist_items.append({
            "category": "付款/寄单指示",
            "requirement": inst_78[:200],
            "clause_ref": "78",
            "priority": "必须",
        })

    # 6. 费用条款提醒
    charges = (clauses.get("71B", "") + " " + clauses.get("71D", "")).strip()
    if charges:
        checklist_items.append({
            "category": "费用注意",
            "requirement": charges[:150],
            "clause_ref": "71B/71D",
            "priority": "注意",
        })

    # --- 渲染清单表格 ---
    if not checklist_items:
        story.append(note_box("无交单要求", "未提取到交单要求。", "info"))
        return

    rows = [[
        Paragraph("<b>序号</b>", S["th"]),
        Paragraph("<b>类别</b>", S["th"]),
        Paragraph("<b>条款要求内容</b>", S["th"]),
        Paragraph("<b>依据</b>", S["th"]),
        Paragraph("<b>重要</b>", S["th"]),
    ]]

    pri_map = {
        "必须": (C.RED_BD, "[!]"),
        "注意": (C.AMBER_BD, "[*]"),
    }

    for i, item in enumerate(checklist_items):
        pri = item.get("priority", "注意")
        bd_col, tag = pri_map.get(pri, (C.GREY, "[ ]"))

        req_text = item.get("requirement", "")
        cat_text = item.get("category", "")

        rows.append([
            Paragraph(str(i + 1), S["tc"]),
            Paragraph(_esc(cat_text), S["small"]),
            Paragraph(_esc(req_text), S["bl"]),
            Paragraph(_esc(item.get("clause_ref", "-")), S["tc"]),
            tag_cell(tag, bd_col, C.WHITE),
        ])

    # A4 可用宽度 174mm; 分配: 序号10 | 类别28 | 要求92 | 依据16 | 重要28 = 174mm
    t = Table(rows, colWidths=[10*mm, 28*mm, 92*mm, 16*mm, 28*mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), hex_color(C.NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), hex_color(C.WHITE)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [hex_color(C.WHITE), hex_color(C.LGREY)]),
        ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.NAVY)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(t)

    story.append(Spacer(1, 2*mm))
    # 范围说明
    story.append(Spacer(1, 2*mm))
    story.append(note_box(
        "[i] 提示",
        "本备查清单仅包含本信用证明确写入的条款要求。未出现在本证中的行业惯例要求不在此列。",
        "info"
    ))


# ---------- 第八章：审核总结与建议 ----------

def conclusion_level(anomalies):
    """根据异常情况决定结论框的颜色级别"""
    if not anomalies:
        return "success"
    has_high = any(str(a.get("severity", "")).lower() in ("high", "critical", "严重") for a in anomalies)
    if has_high:
        return "danger"
    has_med = any(str(a.get("severity", "")).lower() in ("medium", "warning", "警告") for a in anomalies)
    if has_med:
        return "warning"
    return "success"


def conclusion_bg(level):
    return {"danger": C.RED_BG, "warning": C.AMBER_BG, "success": C.GREEN_BG}.get(level, C.LIGHT_BLUE)


def conclusion_bd(level):
    return {"danger": C.RED_BD, "warning": C.AMBER_BD, "success": C.GREEN_BD}.get(level, C.BLUE)


def _make_conclusion_v4(analysis, anomalies, clauses):
    """生成v4版审核总结结论文字"""
    lc_no = analysis.get("lc_no", "未知")

    if not anomalies:
        return (
            f"<b>审核结果：通过 (无明显异常)</b><br/><br/>"
            f"信用证编号：{_esc(lc_no)}<br/>"
            f"本次审核未检测到严重或中等风险项目。"
            f"条款格式正确，未发现自相矛盾或不合理要求。<br/><br/>"
            f"<font size=8.5 color='#6B7280'>"
            f"免责声明：本报告基于提供的信用证文件生成，"
            f"仅供参考，不代表法律意见。"
            f"建议结合实际业务和 UCP600 规则进行综合判断。</font>"
        )

    high_count = sum(1 for a in anomalies
                     if str(a.get("severity", "")).lower() in ("high", "critical", "严重"))
    med_count = sum(1 for a in anomalies
                     if str(a.get("severity", "")).lower() in ("medium", "warning", "警告"))
    low_count = len(anomalies) - high_count - med_count

    result_word = "不通过" if high_count > 0 else ("有条件通过" if med_count > 0 else "基本通过")
    summary_parts = []
    if high_count > 0:
        summary_parts.append(f"<font color='#DC2626'>{high_count} 个严重问题</font>")
    if med_count > 0:
        summary_parts.append(f"<font color='#D97706'>{med_count} 个警告</font>")
    if low_count > 0:
        summary_parts.append(f"{low_count} 个提示")
    summary = "、".join(summary_parts)

    ops = []
    if high_count > 0:
        ops.append("1. 严重问题必须在发走前解决。<br/>")
    if med_count > 0:
        ops.append("2. 警告项目建议提前准备对策方案。<br/>")
    ops.append("3. 所有异常项目建议与开证行/申请人确认。<br/>")

    return (
        f"<b>审核结果：{result_word}</b><br/><br/>"
        f"信用证编号：{_esc(lc_no)}<br/>"
        f"核心发现：{summary}<br/><br/>"
        f"<b>建议操作：</b><br/>"
        + "".join(ops) +
        f"<br/><font size=8.5 color='#6B7280'>"
        f"免责声明：本报告基于提供的信用证文件生成，"
        f"仅供参考，不代表法律意见。</font>"
    )


def _build_chapter8_summary(story, S, analysis, clauses, anomalies):
    """第八章：审核总结与建议 / Summary & Recommendations"""
    story.append(PageBreak())
    story.append(Paragraph("八、审核总结与建议 / Summary & Recommendations", S["h1"]))

    # 总体结论
    level = conclusion_level(anomalies)
    conclusion_text = _make_conclusion_v4(analysis, anomalies, clauses)
    story.append(box_para(Paragraph(conclusion_text, S["body"]), conclusion_bg(level), conclusion_bd(level)))

    # 重点行动项
    story.append(Spacer(1, 3*mm))
    high_items = [a for a in (anomalies or [])
                  if str(a.get("severity", "")).lower() in ("high", "critical", "严重")]
    med_items = [a for a in (anomalies or [])
                 if str(a.get("severity", "")).lower() in ("medium", "warning", "警告")]

    if high_items:
        story.append(Paragraph(_bf("必须在发货前解决的事项:"), S["h2"]))
        for i, a in enumerate(high_items):
            detail = (a.get("description", "") or a.get("detail", ""))[:200]
            suggestion = a.get("suggestion", "请联系开证行修改")[:120]
            story.append(note_box(
                f"[X] 高优先级 #{i+1}",
                f"{_esc(detail)}<br/><br/><b>建议:</b> {_esc(suggestion)}",
                "danger"
            ))
            story.append(Spacer(1, 2*mm))

    if med_items:
        story.append(Paragraph(_bf("建议提前准备的应对方案:"), S["h2"]))
        for i, a in enumerate(med_items):
            detail = (a.get("description", "") or a.get("detail", ""))[:200]
            story.append(note_box(
                f"[!] 中优先级 #{i+1}",
                _esc(detail),
                "warning"
            ))
            story.append(Spacer(1, 2*mm))


# =============================================================================
# 主报告生成入口
# =============================================================================

def generate_lc_review_report(analysis, output_path):
    """
    生成 LC 条款审核报告 PDF — 理想模板版 v4.0（8章节结构）

    参数:
        analysis: dict，来自 lc_analyzer.analyze_lc() 的分析结果
        output_path: PDF 输出路径

    章节结构:
        一、信用证基本信息 (Basic Info with SWIFT field numbers)
        二、货物描述 (45A Goods Description)
        三、单据要求 (46A Documents Required)
        四、附加条件要点 (47A Key Additional Conditions)
        五、条款异常分析 (Clause Anomaly Review)
        六、风险矩阵 (Risk Matrix)
        七、交单备查清单 (Compliance Checklist)
        八、审核总结与建议 (Summary & Recommendations)
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=18*mm, leftMargin=18*mm,
        topMargin=20*mm, bottomMargin=18*mm,
        title=f"信用证审核报告 - {analysis.get('lc_no', 'N/A')}",
        author="LC Audit System",
    )
    S = make_styles()
    story = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ========== 封面/标题区 ==========
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("信用证(L/C)条款审核报告", S["title"]))
    story.append(Spacer(1, 1*mm))

    subtitle_parts = [analysis.get("lc_no") or "未知"]
    if analysis.get("amount"):
        subtitle_parts.append(f"金额：{_fmt_amount(analysis['amount'])}")
    story.append(Paragraph(" | ".join(subtitle_parts), S["subtitle"]))
    story.append(Paragraph(f"报告生成时间：{now}", S["small"]))
    story.append(HRFlowable(width="100%", thickness=1, color=hex_color(C.BORDER), spaceAfter=4*mm))

    # ========== 提取关键数据 ==========
    clauses = analysis.get("clauses", {})
    anomalies = analysis.get("anomalies", [])

    # ========== 一、基本信息 ==========
    _build_chapter1_basic_info(story, S, analysis, clauses)

    # ========== 二、货描 ==========
    story.append(PageBreak())
    _build_chapter2_goods_desc(story, S, analysis, clauses)

    # ========== 三、单据要求 ==========
    story.append(PageBreak())
    _build_chapter3_docs_required(story, S, analysis, clauses)

    # ========== 四、附加条件 ==========
    story.append(PageBreak())
    _build_chapter4_47a_conditions(story, S, analysis, clauses)

    # ========== 五、条款异常分析 ==========
    story.append(PageBreak())
    _build_chapter5_anomaly_review(story, S, analysis, clauses, anomalies)

    # ========== 六、风险矩阵 ==========
    story.append(PageBreak())
    _build_chapter6_risk_matrix(story, S, analysis, clauses, anomalies)

    # ========== 七、交单备查清单 ==========
    story.append(PageBreak())
    _build_chapter7_checklist(story, S, analysis, clauses)

    # ========== 八、总结与建议 ==========
    _build_chapter8_summary(story, S, analysis, clauses, anomalies)

    # ========== 页脚 ==========
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=hex_color(C.BORDER), spaceAfter=4*mm))
    footer_text = f"""<font size=7.5 color="#9CA3AF">
    本报告由 LC Audit 系统自动生成，仅供参考。
    生成时间：{now} | 系统版本：v4.0 (Ideal Template CN) | 审核模式：条款审核
    </font>"""
    story.append(Paragraph(footer_text, S["small"]))

    doc.build(story)


# =============================================================================
# 报告 2：交单合规审核报告（Compliance Report）— 全中文版（保持不变）
# =============================================================================

def generate_compliance_report(check_result, output_path):
    """
    生成中文版交单合规审核报告 PDF。

    check_result 来自 compliance.check_compliance()，包含：
      - lc_info: dict
      - documents: {doc_type: {text, ocr, ...}}
      - results: [{doc_type, check_item, status, detail, suggestion}]
      - time_checks: list
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=18*mm, leftMargin=18*mm,
        topMargin=20*mm, bottomMargin=18*mm,
        title="交单合规审核报告",
        author="LC Audit System",
    )
    S = make_styles()
    story = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ========== 标题 ==========
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("交单合规审核报告", S["title"]))
    story.append(Paragraph("(Documentary Compliance Check Report)", S["subtitle"]))
    story.append(Paragraph(f"报告生成时间：{now}", S["small"]))
    story.append(HRFlowable(width="100%", thickness=1, color=hex_color(C.BORDER), spaceAfter=8*mm))

    # ========== 基本信息 ==========
    lc_info = check_result.get("lc_info", {})
    if lc_info:
        story.append(Paragraph("信用证基本信息", S["h1"]))
        bi_data = [
            ("信用证号码", lc_info.get("lc_no")),
            ("开证行", lc_info.get("issuing_bank")),
            ("申请人", _wrap_long(lc_info.get("applicant"), 200)),
            ("受益人", _wrap_long(lc_info.get("beneficiary"), 200)),
            ("金额", _fmt_amount(lc_info.get("amount"))),
            ("最迟装船日", lc_info.get("latest_shipment")),
            ("到期日", lc_info.get("expiry_date")),
        ]
        story.append(info_tbl(bi_data))
        story.append(Spacer(1, 6*mm))

    # ========== 各单据审核结果 ==========
    documents = check_result.get("documents", {})
    results = check_result.get("results", [])

    if results:
        # 汇总
        summary = summarize_checks(results)
        story.append(Paragraph(
            f"<b>审核汇总：</b>共 <b>{summary['total']}</b> 项检查 | "
            f"<font color='#059669'>通过 {summary['passed']}</font> | "
            f"<font color='#D97706'>警告 {summary['warned']}</font> | "
            f"<font color='#DC2626'>不通过 {summary['failed']}</font>",
            S["body"]
        ))
        story.append(Spacer(1, 4*mm))

        # 按单据分组
        from collections import defaultdict
        grouped = defaultdict(list)
        for r in results:
            grouped[r.get("doc_type", "其他")].append(r)

        for doc_type, checks in grouped.items():
            story.append(Paragraph(f"单据：{_esc(doc_type)}", S["h2"]))

            rows = [[
                Paragraph("<b>检查项</b>", S["th"]),
                Paragraph("<b>状态</b>", S["th"]),
                Paragraph("<b>详情</b>", S["th"]),
                Paragraph("<b>建议</b>", S["th"]),
            ]]

            for chk in checks:
                status = chk.get("status", "INFO")
                status_map = {
                    "PASS": (C.GREEN_BD, "PASS", C.GREEN_BG),
                    "WARN": (C.AMBER_BD, "WARN", C.AMBER_BG),
                    "FAIL": (C.RED_BD, "FAIL", C.RED_BG),
                    "INFO": (C.GREY, "INFO", C.LGREY),
                }
                bd, txt, bg = status_map.get(status, (C.GREY, status, C.LGREY))

                rows.append([
                    Paragraph(_esc(chk.get("check_item", "")), S["body"]),
                    tag_cell(txt, bd, C.WHITE),
                    Paragraph(_esc(chk.get("detail", "")), S["bl"]),
                    Paragraph(_esc(chk.get("suggestion", "")), S["small"]),
                ])

            t = Table(rows, colWidths=[34*mm, 16*mm, 68*mm, 46*mm])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), hex_color(C.NAVY)),
                ("TEXTCOLOR", (0, 0), (-1, 0), hex_color(C.WHITE)),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [hex_color(C.WHITE), hex_color(C.LGREY)]),
                ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.NAVY)),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t)
            story.append(Spacer(1, 4*mm))

    # ========== 时间合规检查 ==========
    time_checks = check_result.get("time_checks", [])
    if time_checks:
        story.append(Paragraph("时间合规检查", S["h1"]))
        tc_rows = [[
            Paragraph("<b>检查项</b>", S["th"]),
            Paragraph("<b>L/C 要求</b>", S["th"]),
            Paragraph("<b>单据日期</b>", S["th"]),
            Paragraph("<b>结果</b>", S["th"]),
        ]]
        for tc in time_checks:
            result = tc.get("result", "UNKNOWN")
            rc = C.GREEN_BD if result == "PASS" else (C.RED_BD if result == "FAIL" else C.AMBER_BD)
            rt = "PASS" if result == "PASS" else ("FAIL" if result == "FAIL" else "WARN")
            tc_rows.append([
                Paragraph(_esc(tc.get("item", "")), S["body"]),
                Paragraph(_esc(tc.get("lc_requirement", "")), S["tc"]),
                Paragraph(_esc(tc.get("doc_value", "")), S["tc"]),
                tag_cell(rt, rc, C.WHITE),
            ])
        tc_table = Table(tc_rows, colWidths=[40*mm, 45*mm, 45*mm, 24*mm])
        tc_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), hex_color(C.NAVY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), hex_color(C.WHITE)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [hex_color(C.WHITE), hex_color(C.LGREY)]),
            ("BOX", (0, 0), (-1, -1), 0.5, hex_color(C.NAVY)),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, hex_color(C.BORDER)),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tc_table)

    # ========== 差异汇总 ==========
    discrepancies = [r for r in results if r.get("status") in ("FAIL", "WARN")]
    if discrepancies:
        story.append(PageBreak())
        story.append(Paragraph("差异汇总 (Discrepancy Summary)", S["h1"]))
        for disc in discrepancies:
            story.append(note_box(
                disc.get("status", "WARN"),
                f"[{disc.get('doc_type', '')}] {disc.get('check_item', '')}: "
                f"{_esc(disc.get('detail', ''))[:200]}",
                "danger" if disc.get("status") == "FAIL" else "warning"
            ))
            story.append(Spacer(1, 2*mm))

    # ========== 结论 ==========
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("审核结论", S["h1"]))

    fail_count = sum(1 for r in results if r.get("status") == "FAIL")
    warn_count = sum(1 for r in results if r.get("status") == "WARN")

    if fail_count > 0:
        conclusion_level_compliance = "danger"
        conclusion_text = (
            f"<b>审核结果：不通过 (FAIL)</b><br/><br/>"
            f"共发现 <b>{fail_count}</b> 项不通过，"
            f"<b>{warn_count}</b> 项警告。<br/><br/>"
            f"建议修正所有 FAIL 项目后重新提交审核。"
        )
    elif warn_count > 0:
        conclusion_level_compliance = "warning"
        conclusion_text = (
            f"<b>审核结果：有条件通过 (CONDITIONAL PASS)</b><br/><br/>"
            f"所有必查项均已通过，但有 <b>{warn_count}</b> 项需要注意。<br/><br/>"
            f"请评估 WARN 项目的影响后决定是否接受。"
        )
    else:
        conclusion_level_compliance = "success"
        conclusion_text = (
            f"<b>审核结果：通过 (PASS)</b><br/><br/>"
            f"所有 <b>{len(results)}</b> 项检查均通过，未发现显著差异。<br/><br/>"
            f"建议在正式交单前再次人工复核关键信息（特别是OCR识别的字段）。"
        )

    story.append(box_para(
        Paragraph(conclusion_text, S["body"]),
        conclusion_bg(conclusion_level_compliance),
        conclusion_bd(conclusion_level_compliance)
    ))

    # 页脚
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=hex_color(C.BORDER), spaceAfter=4*mm))
    footer = f"""<font size=7.5 color="#9CA3AF">
    本报告由 LC Audit 系统自动生成，仅供参考。
    生成时间：{now} | 系统版本：v4.0 (CN) | 审核模式：交单合规
    </font>"""
    story.append(Paragraph(footer, S["small"]))

    doc.build(story)
