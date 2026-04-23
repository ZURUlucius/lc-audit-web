// ===== Global State =====
let currentMode = 'full';

// ===== Mode Selection =====
function selectMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    const docsArea = document.getElementById('docs-area');
    if (docsArea) {
        docsArea.classList.toggle('hidden', mode === 'lc-only');
    }
}

// ===== File Selection =====
function handleFileSelect(input, type) {
    const files = input.files;
    if (!files || files.length === 0) return;

    const previewId = type.toLowerCase() + '-preview';
    const previewEl = document.getElementById(previewId);
    if (previewEl) {
        let html = '';
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const sizeStr = formatFileSize(file.size);
            const count = files.length > 1 ? ` (${i+1}/${files.length})` : '';
            html += '<span class="file-item">&#x2705; ' +
                escapeHtml(file.name) + count + ' (' + sizeStr + ')' +
                '</span>';
        }
        previewEl.innerHTML = html;
    }

    // Mark parent slot as has-file
    const slot = input.closest('.doc-slot');
    if (slot) slot.classList.add('has-file');

    // For LC zone, update the preview (single file)
    if (type === 'lc') {
        const lcPreview = document.getElementById('lc-preview');
        if (lcPreview && files[0]) {
            lcPreview.innerHTML =
                '<span class="file-item">&#x2705; ' +
                escapeHtml(files[0].name) + ' (' + formatFileSize(files[0].size) + ')' +
                '</span>';
        }
    }
}

// ===== Drag & Drop =====
document.addEventListener('DOMContentLoaded', function() {
    const lcZone = document.getElementById('lc-zone');
    if (!lcZone) return;

    ['dragenter', 'dragover'].forEach(evt => {
        lcZone.addEventListener(evt, e => { e.preventDefault(); lcZone.classList.add('dragover'); });
    });
    ['dragleave', 'drop'].forEach(evt => {
        lcZone.addEventListener(evt, e => { e.preventDefault(); lcZone.classList.remove('dragover'); });
    });

    lcZone.addEventListener('drop', e => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const lcInput = document.getElementById('lc-file');
            if (lcInput) {
                lcInput.files = files;
                handleFileSelect(lcInput, 'lc');
            }
        }
    });
});

// ===== Form Submit =====
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('upload-form');
    if (!form) return;

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        const lcFile = document.getElementById('lc-file').files[0];
        if (!lcFile) {
            alert('请先上传信用证（L/C）PDF 文件');
            return;
        }

        showProgress();
        submitFiles();
    });
});

// ===== Submit Files to Backend =====
function submitFiles() {
    const formData = new FormData();
    formData.append('mode', currentMode);

    const lcFile = document.getElementById('lc-file').files[0];
    formData.append('lc_file', lcFile);

    // Add doc files (all support multiple files)
    const docTypes = ['bl', 'ci', 'pl', 'draft', 'fta', 'other'];
    docTypes.forEach(type => {
        const input = document.querySelector('[name="doc_' + type + '"]');
        if (input && input.files.length > 0) {
            for (let i = 0; i < input.files.length; i++) {
                formData.append('doc_' + type, input.files[i]);
            }
        }
    });

    fetch('/api/audit', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateProgress(100, 5, '审核完成！');
            setTimeout(() => showResult(data), 600);
        } else {
            showError(data.error || '处理过程中出现错误，请重试。');
        }
    })
    .catch(err => {
        console.error(err);
        showError('网络错误：' + err.message + '，请检查连接后重试。');
    });
}

// ===== Progress UI =====
function showProgress() {
    document.getElementById('upload-section').classList.add('hidden');
    document.getElementById('result-section').classList.add('hidden');
    document.getElementById('progress-section').classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });

    updateProgress(10, 1, '正在提取文件文本...');
    simulateProgressSteps();
}

function updateProgress(percent, step, detail) {
    const bar = document.getElementById('progress-bar');
    const detailEl = document.getElementById('progress-detail');

    if (bar) bar.style.width = percent + '%';
    if (detailEl) detailEl.textContent = detail;

    document.querySelectorAll('.step').forEach(el => {
        const s = parseInt(el.dataset.step);
        el.classList.remove('active', 'done');
        if (s < step) el.classList.add('done');
        else if (s === step) el.classList.add('active');
    });
}

function simulateProgressSteps() {
    // These are simulated; real progress comes from server
    setTimeout(() => updateProgress(25, 2, '正在进行 OCR 识别...'), 2000);
    setTimeout(() => updateProgress(50, 3, '正在分析信用证条款...'), 5000);
    setTimeout(() => updateProgress(75, 4, '正在交叉核对单据...'), 9000);
}

// ===== Result UI =====
function showResult(data) {
    document.getElementById('progress-section').classList.add('hidden');
    document.getElementById('result-section').classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Download link
    const dlLink = document.getElementById('download-link');
    if (dlLink && data.report_url) {
        dlLink.href = data.report_url;
    }

    // Summary
    renderSummary(data.summary || {});

    // Detail
    const detailContainer = document.getElementById('report-detail');
    if (detailContainer && data.detail_html) {
        detailContainer.innerHTML = data.detail_html;
    }
}

function renderSummary(summary) {
    const container = document.getElementById('report-summary');
    if (!container) return;

    const cards = [
        { key: 'lc_no', label: 'L/C 号码', cls: 'info', icon: '&#x1F4CB;' },
        { key: 'total_checks', label: '检查项总数', cls: 'info', icon: '&#x1F4DD;' },
        { key: 'pass_count', label: '通过项', cls: 'pass', icon: '&#x2705;' },
        { key: 'warn_count', label: '警告项', cls: 'warn', icon: '&#x26A0;&#xFE0F;' },
        { key: 'fail_count', label: '不符点', cls: 'fail', icon: '&#x274C;' },
    ];

    let html = '';
    cards.forEach(card => {
        const val = summary[card.key] !== undefined ? summary[card.key] : '--';
        html +=
            '<div class="summary-card ' + card.cls + '">' +
                '<span class="summary-value">' + card.icon + ' ' + escapeHtml(String(val)) + '</span>' +
                '<div class="summary-label">' + card.label + '</div>' +
            '</div>';
    });
    container.innerHTML = html;
}

// ===== Error State =====
function showError(message) {
    const section = document.getElementById('progress-section');
    if (section) {
        const detailEl = document.getElementById('progress-detail');
        if (detailEl) {
            detailEl.style.color = '#CC0000';
            detailEl.textContent = message;
        }
    }

    setTimeout(() => {
        resetForm();
        alert(message);
    }, 2500);
}

// ===== Reset Form =====
function resetForm() {
    const form = document.getElementById('upload-form');
    if (form) form.reset();

    document.querySelectorAll('.file-preview, .slot-preview').forEach(el => {
        el.innerHTML = '';
    });
    document.querySelectorAll('.doc-slot').forEach(slot => slot.classList.remove('has-file'));

    document.getElementById('upload-section').classList.remove('hidden');
    document.getElementById('progress-section').classList.add('hidden');
    document.getElementById('result-section').classList.add('hidden');

    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = '0%';

    const detailEl = document.getElementById('progress-detail');
    if (detailEl) {
        detailEl.style.color = '';
        detailEl.textContent = '';
    }

    selectMode('full');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ===== Utilities =====
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
