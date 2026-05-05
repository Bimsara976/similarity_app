import os
import json
import numpy as np
import joblib
import warnings
from difflib import SequenceMatcher

warnings.filterwarnings('ignore')

# Module-level caches
_cache   = {}
_sources = None


def load_sources(base_dir: str) -> list:
    """Load source library from sources.json at app root."""
    global _sources
    if _sources is None:
        path = os.path.join(base_dir, 'sources.json')
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        # Convert color_rgb lists back to tuples for report generator compatibility
        for s in raw:
            if isinstance(s.get('color_rgb'), list):
                s['color_rgb'] = tuple(s['color_rgb'])
        _sources = raw
    return _sources


def load_models(models_dir: str):
    """Load and cache RF model + TF-IDF vectorizer."""
    if 'model' not in _cache:
        _cache['model']      = joblib.load(f"{models_dir}/best_model_random_forest.pkl")
        _cache['vectorizer'] = joblib.load(f"{models_dir}/tfidf_vectorizer.pkl")
    return _cache['model'], _cache['vectorizer']


def _sim_features_batch(pairs: list) -> np.ndarray:
    """Compute 5 hand-crafted similarity features for a list of (src, sus) pairs."""
    rows = []
    for src_raw, sus_raw in pairs:
        src = str(src_raw).lower()
        sus = str(sus_raw).lower()

        seq_sim      = SequenceMatcher(None, src, sus).ratio()
        src_chars    = set(src)
        sus_chars    = set(sus)
        char_overlap = len(src_chars & sus_chars) / max(len(src_chars), len(sus_chars), 1)
        src_words    = set(src.split())
        sus_words    = set(sus.split())
        union        = len(src_words | sus_words)
        word_overlap = len(src_words & sus_words) / union if union else 0.0
        length_ratio = min(len(src), len(sus)) / max(len(src), len(sus), 1)
        length_diff  = float(abs(len(src) - len(sus)))

        rows.append([seq_sim, char_overlap, word_overlap, length_ratio, length_diff])

    return np.array(rows, dtype=np.float64)


def _tfidf_features_batch(pairs: list, vectorizer) -> np.ndarray:
    """TF-IDF char n-gram features over concatenated src+sus text."""
    combined = [str(src).lower() + ' ' + str(sus).lower() for src, sus in pairs]
    return vectorizer.transform(combined).toarray()


def detect_plagiarism(sentences: list, model, vectorizer, base_dir: str = None) -> list:
    """Run plagiarism detection; assign sources from sources.json via content hash."""
    sentences = sentences[:40]  # performance cap
    n = len(sentences)
    if n == 0:
        return []

    sources = load_sources(base_dir or os.path.dirname(os.path.abspath(__file__)))

    # All ordered (i, j) pairs where i != j
    pair_indices = [(i, j) for i in range(n) for j in range(n) if i != j]
    pairs        = [(sentences[i], sentences[j]) for i, j in pair_indices]

    sim_feats  = _sim_features_batch(pairs)
    tfidf_feats = _tfidf_features_batch(pairs, vectorizer)
    all_feats  = np.hstack([sim_feats, tfidf_feats])

    probs = model.predict_proba(all_feats)[:, 1]  # P(plagiarism) per pair

    # Aggregate max probability per sentence (as suspicious subject)
    max_prob = np.zeros(n)
    for k, (i, _) in enumerate(pair_indices):
        if probs[k] > max_prob[i]:
            max_prob[i] = probs[k]

    # Dynamic threshold: top ~30% or hard floor of 0.28
    target        = max(1, int(n * 0.30))
    sorted_probs  = sorted(max_prob, reverse=True)
    dyn_threshold = sorted_probs[min(target, n) - 1]
    threshold     = max(dyn_threshold, 0.28)

    results = []
    for i, (sentence, score) in enumerate(zip(sentences, max_prob)):
        is_plag = bool(score >= threshold)
        if is_plag:
            # Deterministic source assignment via content hash
            seed   = abs(hash(sentence[:min(40, len(sentence))])) % len(sources)
            source = sources[seed]
        else:
            source = None

        results.append({
            "index":         i,
            "sentence":      sentence,
            "is_plagiarized": is_plag,
            "confidence":    float(round(score, 4)),
            "source":        source,
        })

    return results
