/**
 * Similarity.lk — Dashboard JS
 * Handles: drag-drop, file selection, AJAX upload, polling, delete, toasts.
 */

let selectedFile = null;

// ── Toast ─────────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const toast   = document.getElementById('toast');
  const inner   = document.getElementById('toast-inner');
  const msgEl   = document.getElementById('toast-msg');
  const iconEl  = document.getElementById('toast-icon');

  msgEl.textContent = msg;

  const styles = {
    success: { bg: 'bg-green-900/90 border border-green-700/50 text-green-200', icon: '✓' },
    error:   { bg: 'bg-red-900/90 border border-red-700/50 text-red-200',       icon: '✕' },
    info:    { bg: 'bg-indigo-900/90 border border-indigo-700/50 text-indigo-200', icon: 'ℹ' },
    warning: { bg: 'bg-amber-900/90 border border-amber-600/50 text-amber-200', icon: '⚠' },
  };

  const s = styles[type] || styles.info;
  inner.className = `rounded-xl px-4 py-3 shadow-2xl flex items-center gap-3 text-sm font-medium ${s.bg}`;
  iconEl.textContent = s.icon;

  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3500);
}


// ── Drop zone ─────────────────────────────────────────────────────────────
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});

['dragleave', 'dragend'].forEach(ev =>
  dropZone.addEventListener(ev, () => dropZone.classList.remove('drag-over'))
);

dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f) handleFileSelect(f);
});

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) handleFileSelect(fileInput.files[0]);
});


function handleFileSelect(file) {
  const allowed = ['application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'];
  const ext = file.name.split('.').pop().toLowerCase();

  if (!['pdf', 'docx', 'doc'].includes(ext)) {
    showToast('Only PDF and DOCX files are supported.', 'error');
    return;
  }

  selectedFile = file;

  document.getElementById('dz-idle').classList.add('hidden');
  document.getElementById('dz-selected').classList.remove('hidden');
  document.getElementById('selected-name').textContent = file.name;
  document.getElementById('selected-size').textContent = formatBytes(file.size);

  const btn = document.getElementById('upload-btn');
  btn.disabled = false;
}


function clearFile() {
  selectedFile = null;
  fileInput.value = '';
  document.getElementById('dz-idle').classList.remove('hidden');
  document.getElementById('dz-selected').classList.add('hidden');
  document.getElementById('upload-progress').classList.add('hidden');
  document.getElementById('upload-btn').disabled = true;
  document.getElementById('btn-text').classList.remove('hidden');
  document.getElementById('btn-spinner').classList.add('hidden');
  setProgress(0, 'Uploading…');
}


// ── Upload ────────────────────────────────────────────────────────────────
function uploadFile() {
  if (!selectedFile) return;

  const formData = new FormData();
  formData.append('file', selectedFile);

  // UI state
  document.getElementById('upload-btn').disabled = true;
  document.getElementById('btn-text').classList.add('hidden');
  document.getElementById('btn-spinner').classList.remove('hidden');
  document.getElementById('upload-progress').classList.remove('hidden');
  setProgress(15, 'Uploading document…');

  const xhr = new XMLHttpRequest();

  xhr.upload.addEventListener('progress', e => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 40) + 10;
      setProgress(pct, 'Uploading…');
    }
  });

  xhr.addEventListener('load', () => {
    setProgress(60, 'Running plagiarism analysis…');

    let data;
    try {
      data = JSON.parse(xhr.responseText);
    } catch {
      finishUpload(false, 'Unexpected server response.');
      return;
    }

    if (xhr.status === 200 && data.success) {
      setProgress(95, 'Generating PDF report…');
      setTimeout(() => {
        setProgress(100, 'Complete!');
        setTimeout(() => {
          showToast(
            `Analysis complete · ${data.plagiarism_percentage}% plagiarism detected`,
            'success'
          );
          finishUpload(true);
          setTimeout(() => location.reload(), 800);
        }, 400);
      }, 600);
    } else if (data.language_error) {
      // Document is not in Sinhala — show amber warning, reset cleanly
      finishUpload(false, null);
      showLanguageWarning(data.error);
    } else {
      finishUpload(false, data.error || 'Processing failed.');
    }
  });

  xhr.addEventListener('error', () => finishUpload(false, 'Network error. Please try again.'));

  xhr.open('POST', '/upload');
  xhr.send(formData);
}


function setProgress(pct, label) {
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('progress-pct').textContent = pct + '%';
  document.getElementById('progress-label').textContent = label;
}


function finishUpload(success, errorMsg) {
  document.getElementById('btn-spinner').classList.add('hidden');
  document.getElementById('btn-text').classList.remove('hidden');
  document.getElementById('upload-btn').disabled = false;

  if (!success) {
    setProgress(0, errorMsg ? 'Upload failed' : 'Ready');
    if (errorMsg) showToast(errorMsg, 'error');
  }
}


// ── Language Warning Modal ────────────────────────────────────────────────
function showLanguageWarning(message) {
  // Remove existing modal if any
  const existing = document.getElementById('lang-warning-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'lang-warning-modal';
  modal.style.cssText = `
    position:fixed;inset:0;z-index:9999;
    display:flex;align-items:center;justify-content:center;
    background:rgba(0,0,0,0.65);backdrop-filter:blur(4px);
  `;

  modal.innerHTML = `
    <div style="
      background:#1e293b;border:1px solid #f59e0b;border-radius:16px;
      max-width:480px;width:90%;padding:32px;box-shadow:0 25px 60px rgba(0,0,0,0.5);
      animation:slideUp .25s ease;
    ">
      <!-- Icon -->
      <div style="text-align:center;margin-bottom:20px;">
        <div style="
          display:inline-flex;align-items:center;justify-content:center;
          width:64px;height:64px;border-radius:50%;
          background:#451a03;border:2px solid #f59e0b;
          font-size:30px;
        ">⚠</div>
      </div>

      <!-- Title -->
      <h3 style="
        text-align:center;color:#fbbf24;font-size:18px;
        font-weight:700;margin:0 0 12px;
      ">Sinhala Document Required</h3>

      <!-- Body -->
      <p style="
        color:#94a3b8;font-size:13px;line-height:1.7;
        text-align:center;margin:0 0 8px;
      ">
        ${message}
      </p>
      <p style="
        color:#64748b;font-size:12px;text-align:center;
        margin:0 0 24px;
      ">
        Similarity.lk is a Sinhala plagiarism detection system.<br>
        Only documents written in <strong style="color:#fbbf24;">සිංහල</strong> are supported.
      </p>

      <!-- Sinhala badge -->
      <div style="
        background:#0f172a;border:1px solid #334155;border-radius:8px;
        padding:10px 16px;margin-bottom:24px;text-align:center;
      ">
        <span style="color:#64748b;font-size:11px;">Accepted languages:</span>
        <span style="
          display:inline-block;margin-left:8px;
          background:#1d4ed8;color:white;padding:2px 12px;
          border-radius:20px;font-size:12px;font-weight:600;
        ">සිංහල (Sinhala)</span>
      </div>

      <!-- Button -->
      <button onclick="document.getElementById('lang-warning-modal').remove();
                       document.getElementById('file-input').value='';"
        style="
          display:block;width:100%;padding:12px;
          background:#f59e0b;color:#0f172a;
          border:none;border-radius:10px;
          font-size:14px;font-weight:700;cursor:pointer;
          transition:background .2s;
        "
        onmouseover="this.style.background='#fbbf24'"
        onmouseout="this.style.background='#f59e0b'"
      >
        Upload a Sinhala Document
      </button>
    </div>
    <style>
      @keyframes slideUp {
        from { opacity:0; transform:translateY(20px); }
        to   { opacity:1; transform:translateY(0); }
      }
    </style>
  `;

  // Close on backdrop click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.remove();
      document.getElementById('file-input').value = '';
    }
  });

  document.body.appendChild(modal);
}


// ── Delete ────────────────────────────────────────────────────────────────
function deleteFile(fileId) {
  if (!confirm('Delete this document and its report permanently?')) return;

  fetch(`/delete/${fileId}`, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        const row = document.getElementById(`row-${fileId}`);
        if (row) {
          row.style.opacity = '0';
          row.style.transition = 'opacity 0.3s';
          setTimeout(() => {
            row.remove();
            showToast('Document deleted.', 'info');
            updateEmptyState();
          }, 300);
        }
      } else {
        showToast(data.error || 'Delete failed.', 'error');
      }
    })
    .catch(() => showToast('Network error.', 'error'));
}


function updateEmptyState() {
  const tbody = document.getElementById('files-tbody');
  if (tbody && tbody.children.length === 0) {
    location.reload();
  }
}


// ── Helpers ───────────────────────────────────────────────────────────────
function formatBytes(bytes) {
  if (bytes < 1024)        return bytes + ' B';
  if (bytes < 1048576)     return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}
