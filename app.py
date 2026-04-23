# -*- coding: utf-8 -*-
"""
LC Audit Web Application - Main Flask App

A web-based Letter of Credit audit tool for team use.
Upload LC PDF + documents -> Get professional PDF audit report.

Deployment:
    Local:     python start_server.py          # http://localhost:5000
    Cloud:     Render / Railway (auto-deploy)   # auto from git push
"""

import os
import sys
import io
import tempfile
import uuid
import shutil
from datetime import datetime

# ── SKILL 同步机制：启动时从 skill 目录加载最新规则 ─────────────────────
# 部署到云端时，skill 文件作为项目的一部分打包进去。
# 本地开发时，自动从 ~/.workbuddy/skills/lc-audit/references/ 同步。
SKILL_DIR = os.path.join(os.path.dirname(__file__), "references")
if not os.path.isdir(SKILL_DIR):
    os.makedirs(SKILL_DIR, exist_ok=True)
    _local_skill = os.path.expanduser("~/.workbuddy/skills/lc-audit")
    if os.path.isdir(_local_skill):
        for f in ("lc_audit_guide.md", "cipl_template_guide.md"):
            src = os.path.join(_local_skill, "references", f)
            dst = os.path.join(SKILL_DIR, f)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

# Add utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))

from flask import (
    Flask, render_template, request, jsonify,
    send_file, send_from_directory
)

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────
# Cloud platforms set PORT env var; local defaults to 5000
PORT = int(os.environ.get("PORT", 5000))
HOST = os.environ.get("HOST", "0.0.0.0")

UPLOAD_FOLDER = tempfile.gettempdir()
REPORT_FOLDER = os.path.join(tempfile.gettempdir(), "lc-audit-reports")
os.makedirs(REPORT_FOLDER, exist_ok=True)

MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size

def sanitize_filename(name: str, max_len: int = 120) -> str:
    """
    Sanitize a string for use as a Windows filename.

    Removes/replaces characters that are illegal on Windows:
      < > : " / \\ | * ? ' and control chars (0x00-0x1F)
    Also strips leading/trailing spaces and dots.
    """
    import re
    # Windows illegal chars: < > : " / \ | * ? '
    ILLEGAL = '<>:"/\\|*?\' '
    # Remove control characters
    s = ''.join(c for c in name if ord(c) >= 32)
    # Replace illegal chars with underscore
    for ch in ILLEGAL:
        s = s.replace(ch, '_')
    # Collapse multiple underscores
    s = re.sub(r'_+', '_', s)
    # Strip leading/trailing whitespace/dots/underscores
    s = s.strip(' ._')
    # Truncate (keep extension room if needed)
    if len(s) > max_len:
        s = s[:max_len].rstrip('_')
    return s or "unknown"


def generate_report_filename(lc_no: str) -> str:
    """Generate report filename: LC_{lc_no}_report.pdf (short, clean naming)."""
    import re
    # Extract just the numeric/alphanumeric LC number - strip any label text
    clean_lc = sanitize_filename(lc_no)
    # Remove common label patterns that got included in the LC number
    clean_lc = re.sub(r'(?i)^(Documentary_Credit_Number|Documentary_Credit_No|LC_No?|Number|No\.?)_?', '', clean_lc)
    clean_lc = clean_lc.strip('_')
    return f"LC_{clean_lc}_report.pdf"


ALLOWED_EXTENSIONS = {"PDF"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].upper() in ALLOWED_EXTENSIONS


# ── Routes ──

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(os.path.join(app.root_path, "static"), filename)


@app.route("/api/audit", methods=["POST"])
def api_audit():
    """
    Main audit API endpoint.
    
    Accepts:
        - lc_file: PDF of Letter of Credit (required)
        - doc_bl / doc_ci / doc_pl / doc_draft / doc_other: document PDFs (optional)
        - mode: 'full' or 'lc-only' (default: full)
    
    Returns JSON:
        - success: bool
        - report_url: URL to download the generated PDF
        - summary: dict with check counts
        - detail_html: HTML summary for preview
    """
    try:
        # Check required files
        if "lc_file" not in request.files:
            return jsonify({"success": False, "error": "Missing L/C file"}), 400

        lc_file = request.files["lc_file"]
        if not lc_file.filename or not allowed_file(lc_file.filename):
            return jsonify({"success": False, "error": "L/C must be a PDF file"}), 400

        mode = request.form.get("mode", "full")

        # Save uploaded files temporarily
        job_id = uuid.uuid4().hex[:12]
        work_dir = os.path.join(UPLOAD_FOLDER, f"lc-audit-{job_id}")
        os.makedirs(work_dir, exist_ok=True)

        # Save LC file
        lc_path = os.path.join(work_dir, "lc.pdf")
        lc_file.save(lc_path)
        app.logger.info(f"[{job_id}] Saved LC file: {lc_file.filename}")

        # Save optional doc files
        doc_paths = []
        doc_labels = []

        doc_type_map = {
            "doc_bl": ("BL", "B/L"),
            "doc_ci": ("CI", "Commercial Invoice"),
            "doc_pl": ("PL", "Packing List"),
            "doc_draft": ("DRAFT", "Draft"),
            "doc_other": ("OTHER", "Other Document"),
        }

        for form_key, (type_code, type_label) in doc_type_map.items():
            if form_key in request.files:
                uploaded_files = request.files.getlist(form_key)
                for i, f in enumerate(uploaded_files):
                    if f and f.filename and allowed_file(f.filename):
                        ext = ".pdf"
                        fname = f"{type_code.lower()}_{i}{ext}" if len(uploaded_files) > 1 else f"{type_code.lower()}.pdf"
                        fpath = os.path.join(work_dir, fname)
                        f.save(fpath)
                        doc_paths.append(fpath)
                        label = f"{type_label} ({f.filename})" if i > 0 else type_label
                        doc_labels.append(label)
                        app.logger.info(f"[{job_id}] Saved doc: {form_key}={f.filename}")

        # === Phase 1: Extract text from all PDFs ===
        app.logger.info(f"[{job_id}] Phase 1: Extracting text...")

        from utils.pdf_extractor import extract_text, detect_lc_type

        # Detect if the uploaded file is an original LC or a previously generated report
        lc_type, lc_detect_text, _ = detect_lc_type(lc_path)
        if lc_type == 'report':
            app.logger.warning(f"[{job_id}] Uploaded file appears to be a report PDF, not original LC!")
            return jsonify({
                "success": False,
                "error": ("您上传的文件似乎是之前生成的审核报告PDF，而不是原始信用证文件。"
                          "请上传开证行发出的原始信用证（MT700格式）PDF文件。"),
                "detect_type": "report_pdf",
            }), 400

        lc_text, lc_is_ocr = extract_text(lc_path)
        app.logger.info(f"[{job_id}] LC text extracted ({len(lc_text)} chars, OCR={lc_is_ocr})")

        # Validate that we extracted meaningful LC content
        if not lc_text or len(lc_text.strip()) < 30:
            return jsonify({
                "success": False,
                "error": ("无法从PDF中提取到足够的文本内容。"
                          "该文件可能是扫描件图片、加密PDF或空文件。请确保上传的是可提取文本的信用证PDF。"),
                "detect_type": "empty_content",
            }), 400

        # Warn if no SWIFT MT700 fields found (likely not a real LC)
        import re as _re
        has_swift = bool(_re.search(r':\d{2}[A-Z]?\s*:', lc_text))
        if not has_swift:
            app.logger.warning(f"[{job_id}] No MT700 format detected in uploaded PDF")

        doc_texts = []
        doc_ocr_flags = []
        for dp in doc_paths:
            dt, is_ocr = extract_text(dp)
            doc_texts.append(dt)
            doc_ocr_flags.append(is_ocr)
            app.logger.info(f"[{job_id}] Doc extracted ({len(dt)} chars, OCR={is_ocr})")

        # === Phase 2: Analyze LC terms ===
        app.logger.info(f"[{job_id}] Phase 2: Analyzing LC terms...")

        from utils.lc_analyzer import analyze_lc

        lc_analysis = analyze_lc(lc_text)
        app.logger.info(f"[{job_id}] LC analysis complete. No: {lc_analysis.get('lc_no')}")

        # Generate output path (using unified naming: LC_{lc_no}_report.pdf)
        report_filename = generate_report_filename(lc_analysis.get("lc_no", "unknown"))
        report_path = os.path.join(REPORT_FOLDER, report_filename)

        # === Phase 3 & 4: Compliance Check + Report Generation ===
        if mode == "full" and doc_texts:
            # Full compliance check mode
            app.logger.info(f"[{job_id}] Phase 3-4: Running compliance check...")
            from utils.compliance import check_compliance, summarize_checks

            checks = check_compliance(lc_text, lc_analysis, doc_texts, doc_labels)
            summary = summarize_checks(checks)

            from utils.report_builder import generate_compliance_report
            generate_compliance_report(
                lc_analysis, checks, summary, doc_labels, report_path
            )

            # Build detail HTML for web preview
            detail_html = _build_detail_html(lc_analysis, checks, summary, doc_labels)

        else:
            # LC-only review mode
            app.logger.info(f"[{job_id}] Generating LC-only review report...")
            summary = {
                "lc_no": lc_analysis.get("lc_no", "N/A"),
                "total_checks": len(lc_analysis.get("anomalies", [])),
                "pass_count": 0,
                "warn_count": sum(1 for a in lc_analysis.get("anomalies", []) if a.get("severity") != "HIGH"),
                "fail_count": sum(1 for a in lc_analysis.get("anomalies", []) if a.get("severity") == "HIGH"),
            }

            from utils.report_builder import generate_lc_review_report
            generate_lc_review_report(lc_analysis, report_path)

            detail_html = _build_lc_detail_html(lc_analysis)

        # Clean up temp files but keep report
        try:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception as e:
            app.logger.warning(f"[{job_id}] Cleanup error: {e}")

        # Return success response
        report_url = f"/api/download/{report_filename}"

        result = {
            "success": True,
            "report_url": report_url,
            "summary": summary,
            "detail_html": detail_html,
        }

        app.logger.info(f"[{job_id}] Audit complete! Report: {report_path}")
        return jsonify(result)

    except Exception as e:
        app.logger.exception("Audit failed")
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app.route("/api/download/<path:filename>")
def api_download(filename):
    """Serve generated PDF reports."""
    # Security: prevent directory traversal
    safe_name = os.path.basename(filename)
    # Reject any path components with .. or separators
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    # Must be a PDF
    if not safe_name.lower().endswith(".pdf"):
        return jsonify({"success": False, "error": "Not a PDF file"}), 400

    filepath = os.path.join(REPORT_FOLDER, safe_name)

    if os.path.exists(filepath):
        return send_file(
            filepath,
            as_attachment=True,
            download_name=safe_name,
            mimetype="application/pdf",
        )
    else:
        app.logger.warning(f"Download requested but file not found: {filepath}")
        app.logger.info(f"Available files: {os.listdir(REPORT_FOLDER)[-5:]}")
        return jsonify({"success": False, "error": "Report not found"}), 404


@app.route("/health")
def health():
    """Health check endpoint for cloud platforms."""
    return jsonify({"status": "ok", "service": "LC Audit Web"})


# ── Helpers for building web preview HTML ──

def _build_detail_html(lc_analysis, checks, summary, doc_labels):
    """Build HTML snippet for the result page detail section."""
    html_parts = [
        '<div class="detail-section">',
        '  <div class="detail-title">Basic Info</div>',
    ]

    info_items = [
        ("L/C Number", lc_analysis.get("lc_no", "N/A")),
        ("Amount", lc_analysis.get("amount", "N/A")),
        ("Expiry Date", lc_analysis.get("expiry_date", "N/A")),
        ("Latest Shipment", lc_analysis.get("latest_shipment", "N/A")),
        ("Applicant", lc_analysis.get("applicant", "N/A")[:80]),
        ("Beneficiary", lc_analysis.get("beneficiary", "N/A")[:80]),
    ]
    for label, value in info_items:
        html_parts.append(
            f'<div class="detail-row"><div class="detail-label">{label}</div>'
            f'<div class="detail-value">{_esc(value)}</div></div>'
        )
    html_parts.append("</div>")

    # Anomalies
    anomalies = lc_analysis.get("anomalies", [])
    if anomalies:
        html_parts.append('<div class="detail-section"><div class="detail-title">Clause Anomalies</div>')
        for a in anomalies:
            sev_class = "discrepancy-item" if a.get("severity") == "HIGH" else "discrepancy-item warn"
            html_parts.append(
                f'<div class="{sev_class}">'
                f'[{"FAIL" if a.get("severity")=="HIGH" else "WARN"}] '
                f'{_esc(a.get("type",""))}: {_esc(a.get("detail",""))}'
                f'</div>'
            )
        html_parts.append("</div>")

    # Checks
    if checks:
        html_parts.append('<div class="detail-section"><div class="detail-title">Document Checks</div>')
        fail_checks = [c for c in checks if c.get("status") == "FAIL"]
        warn_checks = [c for c in checks if c.get("status") == "WARN"]

        if fail_checks:
            html_parts.append("<p style='color:#CC0000;font-weight:bold;margin-bottom:6px;'>Discrepancies:</p>")
            for c in fail_checks:
                html_parts.append(
                    f'<div class="discrepancy-item">'
                    f'[{c.get("doc","")} - {c.get("item","")}] {_esc(c.get("detail",""))[:150]}'
                    f'</div>'
                )
        if warn_checks:
            html_parts.append("<p style='color:#856404;font-weight:bold;margin:10px 0 6px;'>Warnings:</p>")
            for c in warn_checks:
                html_parts.append(
                    f'<div class="discrepancy-item warn">'
                    f'[{c.get("doc","")} - {c.get("item","")}] {_esc(c.get("detail",""))[:150]}'
                    f'</div>'
                )

        pass_count = sum(1 for c in checks if c.get("status") == "PASS")
        if pass_count > 0:
            html_parts.append(
                f"<p style='color:#155724;margin-top:10px;'>{pass_count} items passed.</p>"
            )
        html_parts.append("</div>")

    return "\n".join(html_parts)


def _build_lc_detail_html(lc_analysis):
    """Build HTML for LC-only review mode."""
    html_parts = [
        '<div class="detail-section">',
        '  <div class="detail-title">L/C Basic Information</div>',
    ]

    info_items = [
        ("L/C Number", lc_analysis.get("lc_no", "N/A")),
        ("Form of LC", lc_analysis.get("form_of_lc", "N/A")),
        ("Amount", lc_analysis.get("amount", "N/A")),
        ("Expiry Date", lc_analysis.get("expiry_date", "N/A")),
        ("Issuing Bank", lc_analysis.get("issuing_bank", "N/A")[:80]),
        ("Applicant", lc_analysis.get("applicant", "N/A")[:80]),
        ("Beneficiary", lc_analysis.get("beneficiary", "N/A")[:80]),
        ("Latest Shipment", lc_analysis.get("latest_shipment", "N/A")),
        ("Presentation Period", lc_analysis.get("presentation_period", "N/A")),
    ]

    for label, value in info_items:
        html_parts.append(
            f'<div class="detail-row"><div class="detail-label">{label}</div>'
            f'<div class="detail-value">{_esc(value)}</div></div>'
        )
    html_parts.append("</div>")

    # Anomalies
    anomalies = lc_analysis.get("anomalies", [])
    if anomalies:
        html_parts.append('<div class="detail-section"><div class="detail-title">Clause Anomalies</div>')
        for a in anomalies:
            sev_class = "discrepancy-item" if a.get("severity") == "HIGH" else "discrepancy-item warn"
            html_parts.append(
                f'<div class="{sev_class}">'
                f'[{"FAIL" if a.get("severity")=="HIGH" else "WARN"}] '
                f'{_esc(a.get("type",""))}: {_esc(a.get("detail",""))}'
                f'</div>'
            )
        html_parts.append("</div>")
    else:
        html_parts.append(
            '<div class="detail-section"><div class="detail-title">Clause Anomalies</div>'
            '<p style="color:#155724;">No anomalies detected.</p></div>'
        )

    # Doc requirements
    docs = lc_analysis.get("doc_requirements", [])
    if docs:
        html_parts.append('<div class="detail-section"><div class="detail-title">Documents Required (46A)</div>')
        for d in docs:
            html_parts.append(
                f'<div class="detail-row"><div class="detail-label">{_esc(d.get("type",""))}</div>'
                f'<div class="detail-value">{_esc(d.get("detail",""))[:200]}</div></div>'
            )
        html_parts.append("</div>")

    return "\n".join(html_parts)


def _esc(s):
    """HTML escape."""
    if not s:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ── Run ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  LC Audit Web - Starting server...")
    print(f"  http://localhost:{PORT}")
    print("=" * 50)

    # Install dependencies on first run if needed
    try:
        import pdfplumber
    except ImportError:
        print("\nInstalling Python dependencies (first run only)...")
        import subprocess
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "-r", os.path.join(os.path.dirname(__file__), "requirements.txt"),
            "--quiet"
        ])
        print("Dependencies installed.\n")

    # Cloud: use waitress for production stability
    # Local: use Flask dev server with debug
    if os.environ.get("CLOUD") == "1":
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=4)
    else:
        app.run(host=HOST, port=PORT, debug=True)
