import os
import gridfs
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure

# ── Config from environment ───────────────────────────────────────────────
_HOST = os.environ.get('MONGO_HOST', 'localhost')
_PORT = int(os.environ.get('MONGO_PORT', 27017))
_USER = os.environ.get('MONGO_USER', '')
_PASS = os.environ.get('MONGO_PASS', '')
_DB   = os.environ.get('MONGO_DB',   'similarity_lk')

# Build URI — include credentials only if both are set
if _USER and _PASS:
    MONGO_URI = f"mongodb://{_USER}:{_PASS}@{_HOST}:{_PORT}/{_DB}?authSource={_DB}"
else:
    MONGO_URI = f"mongodb://{_HOST}:{_PORT}"

DB_NAME = _DB

_client = None
_db     = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        try:
            _client.admin.command('ping')
        except ConnectionFailure as e:
            raise RuntimeError(
                f"Cannot connect to MongoDB at {_HOST}:{_PORT}. "
                f"Make sure MongoDB is running.\nURI: {MONGO_URI}\n{e}"
            )
    return _client


def get_db():
    global _db
    if _db is None:
        _db = get_client()[DB_NAME]
        _ensure_indexes(_db)
    return _db


def get_gridfs(collection_name: str) -> gridfs.GridFS:
    """Return a GridFS instance for the given collection prefix."""
    db = get_db()
    return gridfs.GridFS(db, collection=collection_name)


# ── Index setup ───────────────────────────────────────────────────────────
def _ensure_indexes(db):
    # Users: unique on username
    db.users.create_index([('username', ASCENDING)], unique=True)

    # Files: fast lookup by id, uploader, time
    db.files.create_index([('id', ASCENDING)],          unique=True)
    db.files.create_index([('uploaded_by', ASCENDING)])
    db.files.create_index([('upload_time', DESCENDING)])
