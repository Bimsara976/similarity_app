import os
import json
import re

_SEMANTIC_FILE = 'semantic_plagiarism.json'
_TIMESTAMP_RE  = re.compile(r'_\d{8}_\d{6}')


def _normalise(filename: str) -> str:
    name = os.path.basename(filename)
    name = _TIMESTAMP_RE.sub('', name)
    name = re.sub(r'_+\.', '.', name)
    return name.lower().strip()


def load_semantic_data(filename: str, data_folder: str) -> dict | None:
    json_path = os.path.join(data_folder, _SEMANTIC_FILE)
    if not os.path.exists(json_path):
        return None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None

    needle = _normalise(filename)

    # 1. Exact normalised match
    for key, value in data.items():
        if _normalise(key) == needle:
            return value

    # 2. Stem-only match (ignore extension)
    needle_stem = os.path.splitext(needle)[0]
    for key, value in data.items():
        if os.path.splitext(_normalise(key))[0] == needle_stem:
            return value

    return None


def summarise_semantic(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return None

    pairs = raw.get('pairs', [])

    # Sort by similarity desc, flag entries above threshold (0.75)
    threshold = 0.75
    processed = []
    for p in sorted(pairs, key=lambda x: x.get('similarity_score', 0), reverse=True)[:20]:
        score = float(p.get('similarity_score', 0))
        processed.append({
            'suspicious_sentence': p.get('suspicious_sentence', ''),
            'source_sentence':     p.get('source_sentence', ''),
            'source_doc':          p.get('source_doc', p.get('source_name', '')),
            'source_language':     p.get('source_language', 'English'),
            'similarity_score':    score,
            'is_plagiarized':      p.get('is_plagiarized', score >= threshold),
        })

    # Build unique sources list from pairs
    seen_sources = {}
    for p in processed:
        name = p.get('source_doc', '')
        url  = ''
        # Try to get url from original data
        for orig in pairs:
            if orig.get('source_name', orig.get('source_doc', '')) == name:
                url = orig.get('source_url', '')
                break
        if name and name not in seen_sources:
            seen_sources[name] = url

    sources = [{'name': n, 'url': u} for n, u in seen_sources.items()]

    flagged     = sum(1 for p in processed if p['is_plagiarized'])
    total_pairs = int(raw.get('total_pairs_checked', len(processed)))
    avg_sim     = (sum(p['similarity_score'] for p in processed) / len(processed)
                   if processed else 0.0)

    return {
        'semantic_percentage': float(raw.get('percentage', 0)),
        'model':               raw.get('model',           'LaBSE + XGBoost'),
        'f1_score':            float(raw.get('f1_score',  0.6950)),
        'source_language':     raw.get('source_language', 'English'),
        'target_language':     raw.get('target_language', 'Sinhala'),
        'total_pairs':         total_pairs,
        'plagiarised_pairs':   int(raw.get('flagged_pairs', flagged)),
        'avg_similarity':      avg_sim,
        'sources':             sources,
        'matches':             processed,
    }
