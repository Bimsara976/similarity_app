import re
import os
import io

# Sinhala Unicode block: U+0D80 – U+0DFF
_SINHALA_RE = re.compile(r'[\u0D80-\u0DFF]')
CID_PATTERN  = re.compile(r'\(cid:\d+\)')

_MIN_TEXT_LEN = 80


def _cid_ratio(text: str) -> float:
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
    Return True only if extraction looks like genuine Unicode content.
    Rejects:
      - Text too short (< 80 chars)
      - > 25% CID placeholder tokens     → Type A legacy font
      - < 2% Sinhala Unicode characters  → Type B Wijesekara font
    """
    if not text or len(text.strip()) < _MIN_TEXT_LEN:
        return False
    if _cid_ratio(text) > 0.25:
        return False
    if _sinhala_ratio(text) < 0.02:
        return False
    return True


def _strip_cid(text: str) -> str:
    return CID_PATTERN.sub('', text).strip()


# ---------------------------------------------------------------------------
# OCR extractor — uses PyMuPDF (no Poppler needed, cross-platform)
# ---------------------------------------------------------------------------
def _extract_via_ocr(file_path: str) -> str:
    """
    Render each PDF page to a 300-DPI RGB image using PyMuPDF (fitz),
    then run Tesseract OCR with Sinhala + English language support.

    PyMuPDF bundles its own MuPDF renderer — no Poppler or GTK required.
    Works on Windows, Linux, and macOS out of the box.
    """
    import fitz          # PyMuPDF — pip install pymupdf
    import pytesseract
    from PIL import Image

    # Determine available OCR languages
    try:
        langs = pytesseract.get_languages()
        ocr_lang = 'sin+eng' if 'sin' in langs else 'eng'
    except Exception:
        ocr_lang = 'sin+eng'

    DPI    = 300
    SCALE  = DPI / 72.0   # MuPDF native unit is 72 dpi
    matrix = fitz.Matrix(SCALE, SCALE)

    parts = []
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise RuntimeError(f'PyMuPDF could not open file: {e}')

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix  = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
            img  = Image.open(io.BytesIO(pix.tobytes('png')))
            page_text = pytesseract.image_to_string(
                img,
                lang=ocr_lang,
                config='--psm 3 --oem 1',
            )
            parts.append(page_text)
    finally:
        doc.close()

    return '\n\n'.join(parts)


# ---------------------------------------------------------------------------
# PDF extractor
# ---------------------------------------------------------------------------
def _extract_pdf(file_path: str) -> str:
    # --- Attempt 1: pdfplumber ---
    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                pages_text.append(page.extract_text() or '')
        raw = '\n\n'.join(pages_text)
        if _is_good_extraction(raw):
            return _strip_cid(raw)
    except Exception:
        pass

    # --- Attempt 2: pypdf ---
    try:
        from pypdf import PdfReader
        pages_text = [p.extract_text() or '' for p in PdfReader(file_path).pages]
        raw = '\n\n'.join(pages_text)
        if _is_good_extraction(raw):
            return _strip_cid(raw)
    except Exception:
        pass

    # --- Attempt 3: PyMuPDF + Tesseract OCR ---
    # Handles CID-encoded and Wijesekara/legacy fonts without Poppler
    try:
        return _extract_via_ocr(file_path)
    except Exception as e:
        raise RuntimeError(
            f'All extraction methods failed for "{os.path.basename(file_path)}". '
            f'OCR error: {e}\n\n'
            f'To enable OCR support, install:\n'
            f'  pip install pymupdf pytesseract\n'
            f'  # Windows: https://github.com/UB-Mannheim/tesseract/wiki\n'
            f'  # Linux:   sudo apt install tesseract-ocr tesseract-ocr-sin\n'
            f'  # macOS:   brew install tesseract'
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
    """
    Extract plain text from a PDF or DOCX file.

    Automatically falls back to Tesseract OCR (via PyMuPDF page rendering)
    for PDFs that use legacy Sinhala font encodings (CID or Wijesekara).
    No Poppler installation required — PyMuPDF is self-contained.
    """
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
    """
    Split text into sentences suitable for plagiarism analysis.
    Splits on sentence-ending punctuation and blank lines.
    Keeps sentences >= 15 chars, caps at 40 sentences.
    """
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
_SINHALA_BLOCK = re.compile(r'[\u0D80-\u0DFF]')

# Minimum fraction of printable chars that must be Sinhala Unicode
_MIN_SINHALA_RATIO = 0.02   # 2% — even short Sinhala titles pass this


def check_language(text: str) -> dict:
    """
    Analyse extracted text and decide whether it contains enough Sinhala
    to be eligible for plagiarism detection.

    Returns
    -------
    {
        'is_sinhala'     : bool   — True if document is acceptable
        'sinhala_ratio'  : float  — fraction of printable chars that are Sinhala
        'sinhala_chars'  : int    — raw count of Sinhala Unicode characters
        'total_chars'    : int    — total printable character count
        'warning'        : str    — human-readable warning (empty if is_sinhala=True)
    }
    """
    printable = [c for c in text if not c.isspace()]
    total     = len(printable)

    if total == 0:
        return {
            'is_sinhala':    False,
            'sinhala_ratio': 0.0,
            'sinhala_chars': 0,
            'total_chars':   0,
            'warning': (
                'The document appears to be empty or contains no readable text. '
                'Please upload a Sinhala-language document.'
            ),
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
                f'Similarity.lk is designed for Sinhala-language documents only. '
                f'Please upload a document written in Sinhala (සිංහල).'
            ),
        }

    return {
        'is_sinhala':    True,
        'sinhala_ratio': ratio,
        'sinhala_chars': sinhala_count,
        'total_chars':   total,
        'warning':       '',
    }
