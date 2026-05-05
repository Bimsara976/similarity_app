import re
import os
import io

# Sinhala Unicode block U+0D80–U+0DFF
_SINHALA_RE  = re.compile(r'[\u0D80-\u0DFF]')
CID_PATTERN  = re.compile(r'\(cid:\d+\)')
_MIN_TEXT_LEN = 80


def _cid_ratio(text: str) -> float:
    """Fraction of text occupied by CID placeholder tokens."""
    if not text:
        return 0.0
    cid_chars = sum(len(m.group()) for m in CID_PATTERN.finditer(text))
    return cid_chars / max(len(text), 1)


def _sinhala_ratio(text: str) -> float:
    """Fraction of non-space printable chars that are Sinhala Unicode."""
    if not text:
        return 0.0
    sinhala   = len(_SINHALA_RE.findall(text))
    printable = sum(1 for c in text if not c.isspace())
    return sinhala / max(printable, 1)


def _is_good_extraction(text: str) -> bool:
    """
    True if extraction looks like genuine readable Unicode text.
    Only rejects: too-short text or heavy CID encoding (legacy Type-A font).
    NOTE: Language filtering is intentionally left to check_language() — this
    function must NOT reject English text, otherwise English docs bypass the
    language gate and surface as generic 500 errors instead of 422 warnings.
    """
    if not text or len(text.strip()) < _MIN_TEXT_LEN:
        return False
    if _cid_ratio(text) > 0.25:  # Type-A legacy CID font
        return False
    return True


def _needs_ocr_for_wijesekara(text: str) -> bool:
    """True if text looks like a Wijesekara/FM-font encoded doc (Type-B legacy)."""
    return _sinhala_ratio(text) < 0.02 and len(text.strip()) >= _MIN_TEXT_LEN


def _strip_cid(text: str) -> str:
    return CID_PATTERN.sub('', text).strip()


# ---------------------------------------------------------------------------
# OCR fallback — PyMuPDF render + Tesseract (no Poppler needed)
# ---------------------------------------------------------------------------
def _extract_via_ocr(file_path: str) -> str:
    """Render PDF pages via PyMuPDF at 300 DPI, then OCR with Tesseract sin+eng."""
    import fitz
    import pytesseract
    from PIL import Image

    try:
        langs    = pytesseract.get_languages()
        ocr_lang = 'sin+eng' if 'sin' in langs else 'eng'
    except Exception:
        ocr_lang = 'sin+eng'

    SCALE  = 300 / 72.0
    matrix = fitz.Matrix(SCALE, SCALE)
    parts  = []

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise RuntimeError(f'PyMuPDF could not open file: {e}')

    try:
        for page_num in range(len(doc)):
            page      = doc[page_num]
            pix       = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
            img       = Image.open(io.BytesIO(pix.tobytes('png')))
            page_text = pytesseract.image_to_string(img, lang=ocr_lang, config='--psm 3 --oem 1')
            parts.append(page_text)
    finally:
        doc.close()

    return '\n\n'.join(parts)


# ---------------------------------------------------------------------------
# PDF extractor — pdfplumber → pypdf → OCR
# ---------------------------------------------------------------------------
def _extract_pdf(file_path: str) -> str:
    # Attempt 1: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            raw = '\n\n'.join(p.extract_text() or '' for p in pdf.pages)
        if _is_good_extraction(raw):
            # Wijesekara font: text extracted but no Sinhala Unicode → OCR
            if _needs_ocr_for_wijesekara(raw):
                return _extract_via_ocr(file_path)
            return _strip_cid(raw)
    except Exception:
        pass

    # Attempt 2: pypdf
    try:
        from pypdf import PdfReader
        raw = '\n\n'.join(p.extract_text() or '' for p in PdfReader(file_path).pages)
        if _is_good_extraction(raw):
            if _needs_ocr_for_wijesekara(raw):
                return _extract_via_ocr(file_path)
            return _strip_cid(raw)
    except Exception:
        pass

    # Attempt 3: PyMuPDF + Tesseract OCR (handles CID and legacy fonts)
    try:
        return _extract_via_ocr(file_path)
    except Exception as e:
        raise RuntimeError(
            f'All extraction methods failed for "{os.path.basename(file_path)}". '
            f'OCR error: {e}\n'
            f'Install: pip install pymupdf pytesseract\n'
            f'Windows: https://github.com/UB-Mannheim/tesseract/wiki'
        )


# ---------------------------------------------------------------------------
# DOCX extractor
# ---------------------------------------------------------------------------
def _extract_docx(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_text(file_path: str) -> str:
    """Extract plain text from PDF or DOCX; falls back to OCR for legacy Sinhala fonts."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return _extract_pdf(file_path)
    elif ext in ('.docx', '.doc'):
        return _extract_docx(file_path)
    else:
        raise ValueError(f'Unsupported file type: {ext}')


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------
_WHITESPACE = re.compile(r'\s+')
_MIN_LEN    = 15
_MAX_SENTS  = 40


def split_sentences(text: str) -> list:
    """Split text on sentence-ending punctuation; keep ≥15 chars, cap at 40."""
    text = _WHITESPACE.sub(' ', text).strip()
    raw  = re.split(r'(?<=[.!?।෴])\s+|\n{2,}', text)

    sentences = []
    for seg in raw:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) > 300:
            sub = re.split(r'[,\n]+', seg)
            sentences.extend(s.strip() for s in sub if len(s.strip()) >= _MIN_LEN)
        elif len(seg) >= _MIN_LEN:
            sentences.append(seg)

    # Deduplicate while preserving order
    seen, unique = set(), []
    for s in sentences:
        key = s[:80]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    # If over cap, keep the longest (most content-rich) sentences
    if len(unique) > _MAX_SENTS:
        unique = sorted(unique, key=len, reverse=True)[:_MAX_SENTS]

    return unique


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------
_SINHALA_BLOCK     = re.compile(r'[\u0D80-\u0DFF]')
_MIN_SINHALA_RATIO = 0.02  # 2% floor — even short Sinhala titles pass


def check_language(text: str) -> dict:
    """Return is_sinhala=True only if ≥2% of printable chars are Sinhala Unicode."""
    printable = [c for c in text if not c.isspace()]
    total     = len(printable)

    if total == 0:
        return {
            'is_sinhala':    False,
            'sinhala_ratio': 0.0,
            'sinhala_chars': 0,
            'total_chars':   0,
            'warning': 'Document appears empty or contains no readable text. Please upload a Sinhala document.',
        }

    sinhala_count = len(_SINHALA_BLOCK.findall(text))
    ratio         = sinhala_count / total

    if ratio < _MIN_SINHALA_RATIO:
        pct = round(ratio * 100, 2)
        return {
            'is_sinhala':    False,
            'sinhala_ratio': ratio,
            'sinhala_chars': sinhala_count,
            'total_chars':   total,
            'warning': (
                f'This document does not appear to contain Sinhala text '
                f'(only {pct}% Sinhala characters detected). '
                f'Similarity.lk only supports Sinhala (සිංහල) documents.'
            ),
        }

    return {
        'is_sinhala':    True,
        'sinhala_ratio': ratio,
        'sinhala_chars': sinhala_count,
        'total_chars':   total,
        'warning':       '',
    }
