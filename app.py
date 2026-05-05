import os
import io
import uuid
import warnings
import tempfile
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_file,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from bson import ObjectId
from db import get_db, get_gridfs

warnings.filterwarnings('ignore')


# ── MongoDB ObjectId → JSON fix ───────────────────────────────────────────
class MongoJSONProvider(app.json_provider_class if False else object):
    pass

import json as _json

class _MongoEncoder(_json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if hasattr(o, 'isoformat'):   # datetime
            return o.isoformat()
        return super().default(o)

def _safe_jsonify(data, status=200):
    """jsonify that handles MongoDB ObjectId and datetime."""
    text = _json.dumps(data, cls=_MongoEncoder)
    from flask import Response
    return Response(text, status=status, mimetype='application/json')

# ── App setup ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'similarity_lk_ultra_secret_2026_xKj9')

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
MODELS_FOLDER = os.path.join(BASE_DIR, 'models')
DATA_FOLDER   = os.path.join(BASE_DIR, 'data')

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024   # 20 MB

# Ensure static folders still exist (models & semantic data stay on disk)
os.makedirs(MODELS_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER,   exist_ok=True)


# ── Custom exception ──────────────────────────────────────────────────────
class LanguageError(ValueError):
    """Raised when the uploaded document does not contain Sinhala text."""
    pass


# ── Helpers ───────────────────────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        db   = get_db()
        user = db.users.find_one({'username': session['user']})
        if not user or user.get('role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper


def _current_user():
    """Return the full user document for the logged-in user."""
    if 'user' not in session:
        return None
    return get_db().users.find_one({'username': session['user']}, {'password_hash': 0})


# ── Auth routes ───────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db   = get_db()
        user = db.users.find_one({'username': username})

        if user and check_password_hash(user['password_hash'], password):
            session['user']      = username
            session['user_role'] = user.get('role', 'researcher')
            session['full_name'] = user.get('full_name', username)
            # Update last_login
            db.users.update_one(
                {'username': username},
                {'$set': {'last_login': datetime.utcnow()}}
            )
            return redirect(url_for('dashboard'))

        error = 'Invalid username or password. Please try again.'

    return render_template('login.html', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Self-registration page. First user gets admin role automatically."""
    if 'user' in session:
        return redirect(url_for('dashboard'))

    error   = None
    success = None

    if request.method == 'POST':
        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        confirm    = request.form.get('confirm_password', '')
        full_name  = request.form.get('full_name', '').strip()
        email      = request.form.get('email', '').strip()

        # ── Validation ────────────────────────────────────────────────────
        if not username or not password or not full_name:
            error = 'Username, full name and password are required.'
        elif len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        else:
            db = get_db()
            if db.users.find_one({'username': username}):
                error = f'Username "{username}" is already taken.'
            else:
                # First-ever user becomes admin
                is_first = db.users.count_documents({}) == 0
                role     = 'admin' if is_first else 'researcher'

                db.users.insert_one({
                    'username':      username,
                    'password_hash': generate_password_hash(password),
                    'full_name':     full_name,
                    'email':         email,
                    'role':          role,
                    'created_at':    datetime.utcnow(),
                    'last_login':    None,
                })
                success = (
                    f'Account created successfully! '
                    f'{"You have been granted admin access." if is_first else ""} '
                    f'Please sign in.'
                )

    return render_template('register.html', error=error, success=success)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Dashboard ─────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    db    = get_db()
    user  = _current_user()
    role  = user.get('role', 'researcher') if user else 'researcher'

    # Admins see all files; researchers see only their own
    query = {} if role == 'admin' else {'uploaded_by': session['user']}
    files = list(
        db.files.find(query, {'_id': 0})
                .sort('upload_time', -1)
    )

    completed  = [f for f in files if f.get('status') == 'completed']
    avg_plag   = (
        round(sum(f.get('plagiarism_percentage', 0) for f in completed) / len(completed), 1)
        if completed else 0
    )

    stats = {
        'total_files':    len(files),
        'completed':      len(completed),
        'avg_plagiarism': avg_plag,
        'high_risk':      sum(1 for f in completed if f.get('plagiarism_percentage', 0) >= 50),
    }

    return render_template(
        'dashboard.html',
        files=files,
        stats=stats,
        user=session['user'],
        full_name=user.get('full_name', session['user']) if user else session['user'],
        role=role,
    )


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

    timestamp    = datetime.now().strftime('%Y%m%d_%H%M%S')
    original     = secure_filename(f.filename)
    base, ext    = original.rsplit('.', 1)
    saved_name   = f'{base}_{timestamp}.{ext}'

    # ── Store uploaded file in GridFS ─────────────────────────────────────
    file_bytes      = f.read()
    uploads_fs      = get_gridfs('uploads')
    upload_gridfs_id = uploads_fs.put(
        file_bytes,
        filename=saved_name,
        content_type=f.content_type or 'application/octet-stream',
        original_name=original,
        uploaded_by=session['user'],
        uploaded_at=datetime.utcnow(),
    )

    file_id = str(uuid.uuid4())
    entry   = {
        'id':                    file_id,
        'original_name':         original,
        'saved_name':            saved_name,
        'upload_time':           datetime.now().isoformat(),
        'status':                'processing',
        'plagiarism_percentage': 0,
        'total_sentences':       0,
        'plagiarized_sentences': 0,
        'report_name':           None,
        'uploaded_by':           session['user'],
        'error':                 None,
        'has_semantic':          False,
        'upload_gridfs_id':      str(upload_gridfs_id),   # ObjectId → str
        'report_gridfs_id':      None,
    }

    db = get_db()
    db.files.insert_one({**entry, '_id': file_id})

    # ── Process synchronously ─────────────────────────────────────────────
    try:
        result = _process_file(
            file_bytes=file_bytes,
            saved_name=saved_name,
            base_name=base,
            timestamp=timestamp,
            original_name=original,
            file_id=file_id,
        )

        db.files.update_one(
            {'id': file_id},
            {'$set': {**result, 'status': 'completed'}}
        )
        return jsonify({'success': True, 'file_id': file_id, **result})

    except LanguageError as lang_exc:
        # Clean up GridFS upload — document was rejected
        try:
            uploads_fs.delete(upload_gridfs_id)
        except Exception:
            pass
        db.files.delete_one({'id': file_id})
        return jsonify({'error': str(lang_exc), 'language_error': True}), 422

    except Exception as exc:
        db.files.update_one(
            {'id': file_id},
            {'$set': {'status': 'failed', 'error': str(exc)}}
        )
        app.logger.exception('Processing failed')
        return jsonify({'error': str(exc)}), 500


def _process_file(file_bytes: bytes, saved_name: str, base_name: str,
                  timestamp: str, original_name: str, file_id: str) -> dict:
    """
    Core processing:
    1. Write bytes to a temp file (extractors need a path)
    2. Extract text → language check → sentence split
    3. Plagiarism detection
    4. Semantic lookup
    5. Generate PDF report → store in GridFS
    """
    from utils.text_extractor    import extract_text, split_sentences, check_language
    from utils.plagiarism_engine import load_models, detect_plagiarism
    from utils.report_generator  import generate_report
    from utils.semantic_loader   import load_semantic_data, summarise_semantic

    # Write uploaded bytes to a temp file so extractors can open it
    suffix = '.' + saved_name.rsplit('.', 1)[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        text = extract_text(tmp_path)

        lang = check_language(text)
        if not lang['is_sinhala']:
            raise LanguageError(lang['warning'])

        sentences = split_sentences(text)
        if not sentences:
            raise ValueError('No readable text found in the document.')

        model, vectorizer = load_models(MODELS_FOLDER)
        results           = detect_plagiarism(sentences, model, vectorizer)

        total_s  = len(results)
        plag_s   = sum(1 for r in results if r['is_plagiarized'])
        plag_pct = round((plag_s / total_s * 100) if total_s else 0, 2)

        raw_semantic  = load_semantic_data(original_name or base_name, DATA_FOLDER)
        semantic_data = summarise_semantic(raw_semantic) if raw_semantic else None

        # Generate PDF report into a temp file, then stream into GridFS
        report_name = f'Similarity_{base_name}_{timestamp}.pdf'
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as rpt_tmp:
            rpt_path = rpt_tmp.name

        generate_report(
            report_path=rpt_path,
            doc_name=base_name,
            timestamp=timestamp,
            results=results,
            plagiarism_percentage=plag_pct,
            semantic_data=semantic_data,
        )

        # Store report PDF in GridFS
        reports_fs = get_gridfs('reports')
        with open(rpt_path, 'rb') as rpt_f:
            report_gridfs_id = reports_fs.put(
                rpt_f,
                filename=report_name,
                content_type='application/pdf',
                file_id=file_id,
                generated_at=datetime.utcnow(),
            )
        os.unlink(rpt_path)

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return {
        'plagiarism_percentage': plag_pct,
        'total_sentences':       total_s,
        'plagiarized_sentences': plag_s,
        'report_name':           report_name,
        'report_gridfs_id':      str(report_gridfs_id),   # ObjectId → str for JSON safety
        'has_semantic':          semantic_data is not None,
    }


# ── Downloads (served from GridFS) ────────────────────────────────────────
@app.route('/download/report/<file_id>')
@login_required
def download_report(file_id):
    db    = get_db()
    entry = db.files.find_one({'id': file_id})

    if not entry:
        return jsonify({'error': 'File record not found.'}), 404

    gid_raw = entry.get('report_gridfs_id')
    if not gid_raw or gid_raw == 'None':
        return jsonify({'error': 'Report not yet generated for this file.'}), 404

    # Researchers can only download their own reports
    user = _current_user()
    if user.get('role') != 'admin' and entry['uploaded_by'] != session['user']:
        return jsonify({'error': 'Access denied.'}), 403

    try:
        reports_fs = get_gridfs('reports')
        grid_out   = reports_fs.get(ObjectId(str(gid_raw)))
        report_name = entry.get('report_name', 'report.pdf')
        return send_file(
            io.BytesIO(grid_out.read()),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=report_name,
        )
    except Exception as e:
        app.logger.exception('Report download failed')
        return jsonify({'error': f'Could not retrieve report: {e}'}), 500


@app.route('/download/upload/<file_id>')
@login_required
def download_upload(file_id):
    db    = get_db()
    entry = db.files.find_one({'id': file_id})

    if not entry:
        return jsonify({'error': 'File record not found.'}), 404

    gid_raw = entry.get('upload_gridfs_id')
    if not gid_raw or gid_raw == 'None':
        return jsonify({'error': 'Original document not found in storage.'}), 404

    user = _current_user()
    if user.get('role') != 'admin' and entry['uploaded_by'] != session['user']:
        return jsonify({'error': 'Access denied.'}), 403

    try:
        uploads_fs = get_gridfs('uploads')
        grid_out   = uploads_fs.get(ObjectId(str(gid_raw)))
        saved_name = entry.get('saved_name', 'document')
        return send_file(
            io.BytesIO(grid_out.read()),
            mimetype=grid_out.content_type or 'application/octet-stream',
            as_attachment=True,
            download_name=saved_name,
        )
    except Exception as e:
        app.logger.exception('Upload download failed')
        return jsonify({'error': f'Could not retrieve document: {e}'}), 500


# ── Delete ────────────────────────────────────────────────────────────────
@app.route('/delete/<file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    db    = get_db()
    entry = db.files.find_one({'id': file_id})
    if not entry:
        return jsonify({'error': 'File not found.'}), 404

    user = _current_user()
    if user.get('role') != 'admin' and entry['uploaded_by'] != session['user']:
        return jsonify({'error': 'Access denied.'}), 403

    # Remove GridFS files
    uploads_fs = get_gridfs('uploads')
    reports_fs = get_gridfs('reports')

    for gfs, key in [(uploads_fs, 'upload_gridfs_id'), (reports_fs, 'report_gridfs_id')]:
        gid = entry.get(key)
        if gid:
            try:
                gfs.delete(ObjectId(gid) if isinstance(gid, str) else gid)
            except Exception:
                pass

    db.files.delete_one({'id': file_id})
    return jsonify({'success': True})


# ── Status API (polling) ──────────────────────────────────────────────────
@app.route('/status/<file_id>')
@login_required
def file_status(file_id):
    db    = get_db()
    entry = db.files.find_one({'id': file_id}, {'_id': 0, 'upload_gridfs_id': 0, 'report_gridfs_id': 0})
    if not entry:
        return jsonify({'error': 'Not found.'}), 404
    return jsonify(entry)


# ── Admin: User management ────────────────────────────────────────────────
@app.route('/admin/users')
@admin_required
def admin_users():
    db    = get_db()
    users = list(db.users.find({}, {'password_hash': 0, '_id': 0}).sort('created_at', -1))
    return render_template('admin_users.html', users=users, user=session['user'])


@app.route('/admin/users/delete/<username>', methods=['POST'])
@admin_required
def admin_delete_user(username):
    if username == session['user']:
        return jsonify({'error': 'Cannot delete your own account.'}), 400
    db = get_db()
    db.users.delete_one({'username': username})
    return jsonify({'success': True})


@app.route('/admin/users/role/<username>', methods=['POST'])
@admin_required
def admin_change_role(username):
    new_role = request.json.get('role')
    if new_role not in ('admin', 'researcher'):
        return jsonify({'error': 'Invalid role.'}), 400
    db = get_db()
    db.users.update_one({'username': username}, {'$set': {'role': new_role}})
    return jsonify({'success': True})


# ── Seed admin (first-run helper) ─────────────────────────────────────────
def seed_admin_if_empty():
    """
    If no users exist yet, create a default admin account.
    Remove or change credentials after first login.
    """
    db = get_db()
    if db.users.count_documents({}) == 0:
        db.users.insert_one({
            'username':      'admin',
            'password_hash': generate_password_hash('admin123'),
            'full_name':     'System Administrator',
            'email':         '',
            'role':          'admin',
            'created_at':    datetime.utcnow(),
            'last_login':    None,
        })
        print('[Similarity.lk] Default admin created — username: admin / password: admin123')
        print('[Similarity.lk] Please change these credentials immediately after first login.')


# ── Run ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    seed_admin_if_empty()
    app.run(debug=True, host='0.0.0.0', port=5000)
