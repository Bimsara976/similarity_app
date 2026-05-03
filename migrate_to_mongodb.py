"""
migrate_to_mongodb.py
=====================
One-time migration script: imports the existing JSON + file-based data into MongoDB.

What it does:
  1. Reads data/database.json → inserts records into MongoDB `files` collection
  2. Reads uploads/* → stores each file in GridFS `uploads` bucket
  3. Reads reports/* → stores each PDF in GridFS `reports` bucket
  4. Creates a default admin user if no users exist yet

Run once from the project root:
    python migrate_to_mongodb.py

After verifying everything looks correct in MongoDB Compass or mongosh,
you can delete the uploads/, reports/, and data/database.json files.
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash

# ── Adjust path so we can import db.py from the project root ──────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_db, get_gridfs

BASE_DIR      = Path(__file__).parent
DB_FILE       = BASE_DIR / 'data' / 'database.json'
UPLOADS_DIR   = BASE_DIR / 'uploads'
REPORTS_DIR   = BASE_DIR / 'reports'


def migrate_users(db):
    print('\n[1/4] Setting up users collection...')
    if db.users.count_documents({}) > 0:
        print('  ⚠  Users already exist — skipping user seed.')
        return

    # Seed the default admin account
    db.users.insert_one({
        'username':      'admin',
        'password_hash': generate_password_hash('admin123'),
        'full_name':     'System Administrator',
        'email':         '',
        'role':          'admin',
        'created_at':    datetime.utcnow(),
        'last_login':    None,
    })
    print('  ✓  Default admin created: username=admin / password=admin123')
    print('     ⚠  Change these credentials immediately after first login!')

    # Migrate the hardcoded researcher account
    db.users.insert_one({
        'username':      'researcher',
        'password_hash': generate_password_hash('research2026'),
        'full_name':     'Researcher',
        'email':         '',
        'role':          'researcher',
        'created_at':    datetime.utcnow(),
        'last_login':    None,
    })
    print('  ✓  Researcher account created: username=researcher / password=research2026')


def migrate_uploads(db):
    print('\n[2/4] Migrating uploaded files to GridFS...')
    uploads_fs = get_gridfs('uploads')

    if not UPLOADS_DIR.exists():
        print('  ⚠  uploads/ directory not found — skipping.')
        return {}

    gridfs_map = {}   # saved_name → gridfs ObjectId
    files = list(UPLOADS_DIR.iterdir())
    if not files:
        print('  ⚠  uploads/ is empty.')
        return {}

    for fpath in files:
        if not fpath.is_file():
            continue
        # Skip if already in GridFS
        if uploads_fs.exists({'filename': fpath.name}):
            existing = uploads_fs.find_one({'filename': fpath.name})
            gridfs_map[fpath.name] = existing._id
            print(f'  →  {fpath.name} already in GridFS, skipping.')
            continue

        with open(fpath, 'rb') as f:
            ext = fpath.suffix.lower().lstrip('.')
            mime = {
                'pdf':  'application/pdf',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'doc':  'application/msword',
            }.get(ext, 'application/octet-stream')

            gid = uploads_fs.put(
                f,
                filename=fpath.name,
                content_type=mime,
                original_name=fpath.name,
                uploaded_by='admin',           # best guess for legacy files
                uploaded_at=datetime.utcfromtimestamp(fpath.stat().st_mtime),
            )
        gridfs_map[fpath.name] = str(gid)   # store as string for JSON safety
        print(f'  ✓  {fpath.name}  →  GridFS {gid}')

    return gridfs_map


def migrate_reports(db):
    print('\n[3/4] Migrating PDF reports to GridFS...')
    reports_fs = get_gridfs('reports')

    if not REPORTS_DIR.exists():
        print('  ⚠  reports/ directory not found — skipping.')
        return {}

    gridfs_map = {}
    files = list(REPORTS_DIR.iterdir())
    if not files:
        print('  ⚠  reports/ is empty.')
        return {}

    for fpath in files:
        if not fpath.is_file() or fpath.suffix.lower() != '.pdf':
            continue
        if reports_fs.exists({'filename': fpath.name}):
            existing = reports_fs.find_one({'filename': fpath.name})
            gridfs_map[fpath.name] = existing._id
            print(f'  →  {fpath.name} already in GridFS, skipping.')
            continue

        with open(fpath, 'rb') as f:
            gid = reports_fs.put(
                f,
                filename=fpath.name,
                content_type='application/pdf',
                generated_at=datetime.utcfromtimestamp(fpath.stat().st_mtime),
            )
        gridfs_map[fpath.name] = str(gid)   # store as string for JSON safety
        print(f'  ✓  {fpath.name}  →  GridFS {gid}')

    return gridfs_map


def migrate_file_records(db, upload_map, report_map):
    print('\n[4/4] Migrating database.json records to MongoDB files collection...')

    if not DB_FILE.exists():
        print('  ⚠  data/database.json not found — skipping.')
        return

    with open(DB_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    records = data.get('files', [])
    if not records:
        print('  ⚠  No records found in database.json.')
        return

    inserted = 0
    skipped  = 0

    for rec in records:
        file_id = rec.get('id')
        if not file_id:
            continue

        if db.files.find_one({'id': file_id}):
            skipped += 1
            continue

        saved_name  = rec.get('saved_name', '')
        report_name = rec.get('report_name', '')

        doc = {
            **rec,
            '_id':              file_id,
            'upload_gridfs_id': upload_map.get(saved_name),
            'report_gridfs_id': report_map.get(report_name),
            'has_semantic':     rec.get('has_semantic', False),
        }
        db.files.insert_one(doc)
        inserted += 1
        print(f'  ✓  [{rec.get("status","?")}] {rec.get("original_name","?")}')

    print(f'\n  Total: {inserted} inserted, {skipped} skipped (already existed).')


def main():
    print('=' * 60)
    print('  Similarity.lk — MongoDB Migration')
    print('=' * 60)

    try:
        db = get_db()
        print(f'\n✓  Connected to MongoDB  →  database: similarity_lk')
    except Exception as e:
        print(f'\n✗  Failed to connect to MongoDB: {e}')
        print('  Make sure MongoDB is running on localhost:27017')
        sys.exit(1)

    migrate_users(db)
    upload_map = migrate_uploads(db)
    report_map = migrate_reports(db)
    migrate_file_records(db, upload_map, report_map)

    print('\n' + '=' * 60)
    print('  Migration complete!')
    print('  You can now run: python app.py')
    print('  Verify in MongoDB Compass: mongodb://localhost:27017/similarity_lk')
    print('=' * 60)


if __name__ == '__main__':
    main()
