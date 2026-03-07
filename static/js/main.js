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
    setProgress(0, 'Upload failed');
    showToast(errorMsg || 'Upload failed.', 'error');
  }
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
