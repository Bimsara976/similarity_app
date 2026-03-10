"""
Similarity.lk — Sinhala Plagiarism Detection Web App
Flask entry point: login, dashboard, upload, process, download.
"""
import os
import json
import uuid
import warnings
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_from_directory, flash, jsonify,
)
from werkzeug.utils import secure_filename

warnings.filterwarnings('ignore')

# ── App setup ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'similarity_lk_ultra_secret_2026_xKj9'

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER   = os.path.join(BASE_DIR, 'uploads')
REPORTS_FOLDER  = os.path.join(BASE_DIR, 'reports')
MODELS_FOLDER   = os.path.join(BASE_DIR, 'models')
DATA_FOLDER     = os.path.join(BASE_DIR, 'data')
DB_FILE         = os.path.join(DATA_FOLDER, 'database.json')

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024   # 20 MB

# Hardcoded credentials  {username: password}
CREDENTIALS = {
    'admin': 'admin123',
    'researcher': 'research2026',
}

# Ensure directories exist
for d in [UPLOAD_FOLDER, REPORTS_FOLDER, MODELS_FOLDER, DATA_FOLDER]:
    os.makedirs(d, exist_ok=True)


# ── Tiny JSON database ────────────────────────────────────────────────────
def _init_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, 'w') as f:
            json.dump({'files': []}, f)


def load_db() -> dict:
    _init_db()
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_db(data: dict):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Helpers ───────────────────────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


# ── Auth routes ───────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if CREDENTIALS.get(username) == password:
            session['user'] = username
            return redirect(url_for('dashboard'))
        error = 'Invalid username or password. Please try again.'

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


# ── Dashboard ─────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    db = load_db()
    files = sorted(db['files'], key=lambda x: x.get('upload_time', ''), reverse=True)

    # Summary stats
    total_files   = len(files)
    completed     = [f for f in files if f.get('status') == 'completed']
    avg_plag      = (
        round(sum(f.get('plagiarism_percentage', 0) for f in completed) / len(completed), 1)
        if completed else 0
    )
    high_plag     = sum(1 for f in completed if f.get('plagiarism_percentage', 0) >= 50)

    stats = {
        'total_files':   total_files,
        'completed':     len(completed),
        'avg_plagiarism': avg_plag,
        'high_risk':     high_plag,
    }

    return render_template('dashboard.html',
                           files=files,
                           stats=stats,
                           user=session['user'])


# ── Upload & Process ──────────────────────────────────────────────────────
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided.'}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'No file selected.'}), 400

    if not allowed_file(f.filename):
        return jsonify({'error': 'Only PDF and DOCX files are supported.'}), 400

    # Build timestamped filename
    timestamp    = datetime.now().strftime('%Y%m%d_%H%M%S')
    original     = secure_filename(f.filename)
    base, ext    = original.rsplit('.', 1)
    saved_name   = f'{base}_{timestamp}.{ext}'
    file_path    = os.path.join(UPLOAD_FOLDER, saved_name)
    f.save(file_path)

    file_id = str(uuid.uuid4())
    entry = {
        'id':                   file_id,
        'original_name':        original,
        'saved_name':           saved_name,
        'upload_time':          datetime.now().isoformat(),
        'status':               'processing',
        'plagiarism_percentage': 0,
        'total_sentences':      0,
        'plagiarized_sentences': 0,
        'report_name':          None,
        'uploaded_by':          session['user'],
        'error':                None,
    }

    db = load_db()
    db['files'].append(entry)
    save_db(db)

    # ── Process synchronously ─────────────────────────────────────────────
    try:
        result = _process_file(file_path, base, timestamp, original_name=original)

        db = load_db()
        for rec in db['files']:
            if rec['id'] == file_id:
                rec.update(result)
                rec['status'] = 'completed'
                break
        save_db(db)

        return jsonify({'success': True, 'file_id': file_id, **result})

    except LanguageError as lang_exc:
        # Remove the DB entry — document was rejected, file already deleted
        db = load_db()
        db['files'] = [f for f in db['files'] if f['id'] != file_id]
        save_db(db)
        return jsonify({
            'error':          str(lang_exc),
            'language_error': True,
        }), 422

    except Exception as exc:
        db = load_db()
        for rec in db['files']:
            if rec['id'] == file_id:
                rec['status'] = 'failed'
                rec['error']  = str(exc)
                break
        save_db(db)
        app.logger.exception('Processing failed')
        return jsonify({'error': str(exc)}), 500


class LanguageError(ValueError):
    """Raised when the uploaded document does not contain Sinhala text."""
    pass


def _process_file(file_path: str, base_name: str, timestamp: str,
                  original_name: str = '') -> dict:
    from utils.text_extractor    import extract_text, split_sentences, check_language
    from utils.plagiarism_engine import load_models, detect_plagiarism
    from utils.report_generator  import generate_report
    from utils.semantic_loader   import load_semantic_data, summarise_semantic

    text = extract_text(file_path)

    # ── Language check — reject non-Sinhala documents immediately ─────────
    lang = check_language(text)
    if not lang['is_sinhala']:
        # Delete the uploaded file — no need to store rejected docs
        try:
            os.remove(file_path)
        except Exception:
            pass
        raise LanguageError(lang['warning'])

    sentences = split_sentences(text)

    if not sentences:
        raise ValueError('No readable text found in the document.')

    model, vectorizer = load_models(MODELS_FOLDER)
    results           = detect_plagiarism(sentences, model, vectorizer)

    total_s  = len(results)
    plag_s   = sum(1 for r in results if r['is_plagiarized'])
    plag_pct = round((plag_s / total_s * 100) if total_s else 0, 2)

    # ── Semantic plagiarism lookup (optional, separate section) ───────────
    raw_semantic  = load_semantic_data(original_name or base_name, DATA_FOLDER)
    semantic_data = summarise_semantic(raw_semantic) if raw_semantic else None

    report_name = f'Similarity_{base_name}_{timestamp}.pdf'
    report_path = os.path.join(REPORTS_FOLDER, report_name)

    generate_report(
        report_path=report_path,
        doc_name=base_name,
        timestamp=timestamp,
        results=results,
        plagiarism_percentage=plag_pct,
        semantic_data=semantic_data,
    )

    return {
        'plagiarism_percentage':  plag_pct,
        'total_sentences':        total_s,
        'plagiarized_sentences':  plag_s,
        'report_name':            report_name,
        'has_semantic':           semantic_data is not None,
    }


# ── Downloads ─────────────────────────────────────────────────────────────
@app.route('/download/report/<path:filename>')
@login_required
def download_report(filename):
    return send_from_directory(REPORTS_FOLDER, filename, as_attachment=True)


@app.route('/download/upload/<path:filename>')
@login_required
def download_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


# ── Delete ────────────────────────────────────────────────────────────────
@app.route('/delete/<file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    db    = load_db()
    entry = next((f for f in db['files'] if f['id'] == file_id), None)
    if not entry:
        return jsonify({'error': 'File not found.'}), 404

    for path in [
        os.path.join(UPLOAD_FOLDER, entry['saved_name']),
        os.path.join(REPORTS_FOLDER, entry['report_name'] or ''),
    ]:
        if path and os.path.exists(path):
            os.remove(path)

    db['files'] = [f for f in db['files'] if f['id'] != file_id]
    save_db(db)
    return jsonify({'success': True})


# ── Status API (polling) ───────────────────────────────────────────────────
@app.route('/status/<file_id>')
@login_required
def file_status(file_id):
    db    = load_db()
    entry = next((f for f in db['files'] if f['id'] == file_id), None)
    if not entry:
        return jsonify({'error': 'Not found.'}), 404
    return jsonify(entry)


# ── Run ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    _init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
