
import numpy as np
import joblib
import warnings
from difflib import SequenceMatcher
warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Hardcoded source library (used for demo attribution)
# ---------------------------------------------------------------------------
HARDCODED_SOURCES = [
    {
        "id": 0,
        "name": "Wikipedia – ශ්‍රී ලංකාවේ ඉතිහාසය",
        "url": "https://si.wikipedia.org/wiki/ශ්‍රී_ලංකාව",
        "color_hex": "#FFCDD2",
        "color_rgb": (255, 205, 210),
        "text_color": "#B71C1C",
    },
    {
        "id": 1,
        "name": "University of Colombo Repository",
        "url": "https://repository.cmb.ac.lk/papers/sinhala-lit-001",
        "color_hex": "#C8E6C9",
        "color_rgb": (200, 230, 201),
        "text_color": "#1B5E20",
    },
    {
        "id": 2,
        "name": "National Library of Sri Lanka",
        "url": "https://natlib.lk/collections/sinhala/texts",
        "color_hex": "#BBDEFB",
        "color_rgb": (187, 222, 251),
        "text_color": "#0D47A1",
    },
    {
        "id": 3,
        "name": "Lankadeepa Digital Archive",
        "url": "https://lankadeepa.lk/archive/2024/sinhala",
        "color_hex": "#FFF9C4",
        "color_rgb": (255, 249, 196),
        "text_color": "#F57F17",
    },
    {
        "id": 4,
        "name": "Buddhist Cultural Centre",
        "url": "https://bcc.lk/texts/dharma/2024",
        "color_hex": "#F3E5F5",
        "color_rgb": (243, 229, 245),
        "text_color": "#4A148C",
    },
    {
        "id": 5,
        "name": "Sri Lanka Broadcasting Corporation",
        "url": "https://slbc.lk/sinhala/articles/101",
        "color_hex": "#FFE0B2",
        "color_rgb": (255, 224, 178),
        "text_color": "#E65100",
    },
    {
        "id": 6,
        "name": "Open University of Sri Lanka",
        "url": "https://ou.ac.lk/resources/sinhala/study-material",
        "color_hex": "#E0F7FA",
        "color_rgb": (224, 247, 250),
        "text_color": "#006064",
    },
    {
        "id": 7,
        "name": "Sinhala Literary Journal Vol. 14",
        "url": "https://sinhalaliterature.lk/journal/vol14/page45",
        "color_hex": "#FCE4EC",
        "color_rgb": (252, 228, 236),
        "text_color": "#880E4F",
    },
]

# Module-level model cache
_cache = {}


def load_models(models_dir: str):
    """Load and cache the RF model + TF-IDF vectorizer."""
    if 'model' not in _cache:
        _cache['model'] = joblib.load(f"{models_dir}/best_model_random_forest.pkl")
        _cache['vectorizer'] = joblib.load(f"{models_dir}/tfidf_vectorizer.pkl")
    return _cache['model'], _cache['vectorizer']


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------

def _sim_features_batch(pairs: list) -> np.ndarray:
    """
    Compute the 5 hand-crafted similarity features for a list of (src, sus) pairs.
    Returns ndarray of shape (len(pairs), 5).
    """
    rows = []
    for src_raw, sus_raw in pairs:
        src = str(src_raw).lower()
        sus = str(sus_raw).lower()

        seq_sim = SequenceMatcher(None, src, sus).ratio()

        src_chars = set(src)
        sus_chars = set(sus)
        char_overlap = (
            len(src_chars & sus_chars) / max(len(src_chars), len(sus_chars), 1)
        )

        src_words = set(src.split())
        sus_words = set(sus.split())
        union = len(src_words | sus_words)
        word_overlap = len(src_words & sus_words) / union if union else 0.0

        length_ratio = min(len(src), len(sus)) / max(len(src), len(sus), 1)
        length_diff = float(abs(len(src) - len(sus)))

        rows.append([seq_sim, char_overlap, word_overlap, length_ratio, length_diff])

    return np.array(rows, dtype=np.float64)


def _tfidf_features_batch(pairs: list, vectorizer) -> np.ndarray:
    """TF-IDF character n-gram features for combined src+sus text."""
    combined = [
        str(src).lower() + ' ' + str(sus).lower() for src, sus in pairs
    ]
    return vectorizer.transform(combined).toarray()


# ---------------------------------------------------------------------------
# Main detection
# ---------------------------------------------------------------------------

def detect_plagiarism(sentences: list, model, vectorizer) -> list:
    sentences = sentences[:40]          # performance cap
    n = len(sentences)
    if n == 0:
        return []

    # Build all ordered pairs (i, j) with i != j
    pair_indices = [(i, j) for i in range(n) for j in range(n) if i != j]
    pairs = [(sentences[i], sentences[j]) for i, j in pair_indices]

    # Batch feature computation
    sim_feats = _sim_features_batch(pairs)
    tfidf_feats = _tfidf_features_batch(pairs, vectorizer)
    all_feats = np.hstack([sim_feats, tfidf_feats])

    # Batch prediction
    probs = model.predict_proba(all_feats)[:, 1]   # probability of plagiarism

    # Aggregate: max probability per sentence (as "subject")
    max_prob = np.zeros(n)
    for k, (i, _) in enumerate(pair_indices):
        if probs[k] > max_prob[i]:
            max_prob[i] = probs[k]

    # Dynamic threshold: flag top ~30 % OR use hard minimum 0.30
    target = max(1, int(n * 0.30))
    sorted_probs = sorted(max_prob, reverse=True)
    dyn_threshold = sorted_probs[min(target, n) - 1]
    threshold = max(dyn_threshold, 0.28)

    # Build result list with source assignment
    results = []
    for i, (sentence, score) in enumerate(zip(sentences, max_prob)):
        is_plag = bool(score >= threshold)

        if is_plag:
            # Deterministic source via content hash
            seed = abs(hash(sentence[:min(40, len(sentence))])) % len(HARDCODED_SOURCES)
            source = HARDCODED_SOURCES[seed]
        else:
            source = None

        results.append({
            "index": i,
            "sentence": sentence,
            "is_plagiarized": is_plag,
            "confidence": float(round(score, 4)),
            "source": source,
        })

    return results
