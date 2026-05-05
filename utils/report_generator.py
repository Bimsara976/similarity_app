import os
import html as html_mod
from datetime import datetime

# ── Font paths ─────────────────────────────────────────────────────────────
_NOTO_REG = [
    '/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansSinhala-Light.ttf',
]
_NOTO_MED = [
    '/usr/share/fonts/truetype/noto/NotoSansSinhala-Medium.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf',
]
FONT_REGULAR = next((p for p in _NOTO_REG if os.path.exists(p)), None)
FONT_MEDIUM  = next((p for p in _NOTO_MED if os.path.exists(p)), None) or FONT_REGULAR


# ── Helpers ────────────────────────────────────────────────────────────────
def _esc(t):
    return html_mod.escape(str(t))

def _verdict(pct):
    if pct < 25:   return ('LOW PLAGIARISM',      '#16a34a', '#dcfce7')
    elif pct < 50: return ('MODERATE PLAGIARISM', '#d97706', '#fef3c7')
    else:          return ('HIGH PLAGIARISM',     '#dc2626', '#fee2e2')

def _donut_svg(pct, color=None):
    r = 40; circ = 2 * 3.14159 * r
    on = round(circ * pct / 100, 2); off = round(circ - on, 2)
    if color is None:
        color = '#22c55e' if pct < 25 else ('#f59e0b' if pct < 50 else '#ef4444')
    return (
        f'<svg viewBox="0 0 100 100" width="120" height="120">'
        f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="#e2e8f0" stroke-width="14"/>'
        f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="{color}" stroke-width="14"'
        f' stroke-dasharray="{on} {off}" stroke-linecap="round"'
        f' transform="rotate(-90 50 50)"/>'
        f'<text x="50" y="55" text-anchor="middle" font-family="sans-serif"'
        f' font-size="18" font-weight="bold" fill="{color}">{pct:.0f}%</text></svg>'
    )

def _source_rows(used_sources):
    if not used_sources:
        return ('<tr><td colspan="4" style="padding:10px;color:#64748b;text-align:center;">'
                'No plagiarised sources identified.</td></tr>')
    rows = ''
    for i, (sid, info) in enumerate(used_sources.items()):
        src = info['source']; bg = '#f8fafc' if i % 2 == 0 else '#fff'
        rows += (
            f'<tr style="background:{bg};">'
            f'<td style="text-align:center;padding:7px 10px;">'
            f'<span style="display:inline-block;width:20px;height:20px;border-radius:4px;'
            f'background:{src["color_hex"]};border:1px solid rgba(0,0,0,.12);"></span></td>'
            f'<td style="padding:7px 12px;font-size:12px;">{_esc(src["name"])}</td>'
            f'<td style="padding:7px 12px;font-size:12px;text-align:center;'
            f'font-weight:700;color:#4f46e5;">{info["count"]}</td>'
            f'<td style="padding:7px 12px;font-size:11px;color:#6366f1;'
            f'word-break:break-all;">{_esc(src["url"])}</td></tr>'
        )
    return rows

def _sentence_rows(results):
    parts = []
    for r in results:
        sent = _esc(r['sentence']); src = r.get('source'); conf = r.get('confidence', 0.0)
        if r['is_plagiarized'] and src:
            bg = src['color_hex']; tc = src['text_color']
            tag = (f'<span style="font-size:10px;font-weight:600;color:{tc};margin-left:6px;">'
                   f'&#9658; {_esc(src["name"])} ({conf*100:.0f}% match)</span>')
            parts.append(
                f'<p style="background:{bg};border-left:3px solid {tc};'
                f'padding:7px 10px;margin:4px 0;border-radius:3px;'
                f'font-size:12px;line-height:1.75;">{sent}{tag}</p>'
            )
        else:
            parts.append(
                f'<p style="padding:5px 10px;margin:4px 0;font-size:12px;'
                f'line-height:1.75;color:#1e293b;">{sent}</p>'
            )
    return '\n'.join(parts)


# ── Semantic section builder ───────────────────────────────────────────────
def _semantic_section(sem: dict) -> str:
    """Build the complete HTML block for the Semantic Plagiarism section."""
    if not sem:
        return ''

    pct     = sem.get('semantic_percentage', 0)
    model   = sem.get('model', 'XGBoost + LaBSE')
    f1      = sem.get('f1_score', 0)
    src_l   = sem.get('source_language', 'English')
    tgt_l   = sem.get('target_language', 'Sinhala')
    total   = sem.get('total_pairs', 0)
    flagged = sem.get('plagiarised_pairs', 0)
    avg_sim = sem.get('avg_similarity', 0)
    sources = sem.get('sources', [])
    matches = sem.get('matches', [])

    # Verdict for semantic
    if pct < 25:   sem_color, sem_label = '#16a34a', 'LOW'
    elif pct < 50: sem_color, sem_label = '#d97706', 'MODERATE'
    else:          sem_color, sem_label = '#dc2626', 'HIGH'

    donut = _donut_svg(pct, sem_color)

    # Source list
    src_rows = ''
    for i, s in enumerate(sources):
        bg = '#f8fafc' if i % 2 == 0 else '#fff'
        src_rows += (
            f'<tr style="background:{bg};">'
            f'<td style="padding:6px 10px;font-size:11px;color:#1e293b;">{_esc(s["name"])}</td>'
            f'<td style="padding:6px 10px;font-size:11px;color:#6366f1;'
            f'word-break:break-all;">{_esc(s["url"])}</td></tr>'
        )

    # Match pairs table
    match_rows = ''
    for i, m in enumerate(matches):
        bg      = '#f8fafc' if i % 2 == 0 else '#fff'
        is_p    = m.get('is_plagiarized', False)
        score   = m.get('similarity_score', 0)
        bar_pct = round(score * 100)
        bar_col = '#ef4444' if is_p else '#94a3b8'
        badge   = (f'<span style="background:#fee2e2;color:#dc2626;padding:2px 7px;'
                   f'border-radius:10px;font-size:9px;font-weight:700;">MATCH</span>'
                   if is_p else
                   f'<span style="background:#f1f5f9;color:#64748b;padding:2px 7px;'
                   f'border-radius:10px;font-size:9px;">OK</span>')
        match_rows += f'''
        <tr style="background:{bg};">
          <td style="padding:8px 10px;vertical-align:top;width:38%;">
            <div style="font-size:11px;color:#1e293b;line-height:1.6;">{_esc(m.get("suspicious_sentence",""))}</div>
            <div style="font-size:9px;color:#64748b;margin-top:2px;">🇱🇰 {_esc(tgt_l)}</div>
          </td>
          <td style="padding:8px 10px;vertical-align:top;width:38%;">
            <div style="font-size:11px;color:#1e293b;line-height:1.6;font-style:italic;">{_esc(m.get("source_sentence",""))}</div>
            <div style="font-size:9px;color:#6366f1;margin-top:2px;">🌐 {_esc(m.get("source_doc",""))}</div>
          </td>
          <td style="padding:8px 10px;vertical-align:middle;text-align:center;width:12%;">
            <div style="font-size:13px;font-weight:800;color:{bar_col};">{bar_pct}%</div>
            <div style="background:#e2e8f0;border-radius:4px;height:5px;margin-top:4px;">
              <div style="background:{bar_col};width:{bar_pct}%;height:5px;border-radius:4px;"></div>
            </div>
          </td>
          <td style="padding:8px 10px;vertical-align:middle;text-align:center;width:12%;">
            {badge}
          </td>
        </tr>'''

    return f'''
  <!-- ════════════════════════════════════════════════════════════════
       SEMANTIC PLAGIARISM SECTION  (separate from similarity score)
       ════════════════════════════════════════════════════════════════ -->
  <div class="page-break"></div>

  <!-- Section header with teal accent -->
  <div style="background:#0f766e;color:white;text-align:center;padding:13px;
              font-size:15px;font-weight:700;letter-spacing:1px;
              border-radius:4px;margin-bottom:18px;">
    SEMANTIC (CROSS-LANGUAGE) PLAGIARISM ANALYSIS
  </div>

  <!-- Important notice — kept separate -->
  <div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:4px;
              padding:10px 14px;margin-bottom:18px;font-size:10px;color:#92400e;">
    <strong>&#9432; Note:</strong> This section presents <em>semantic</em> (cross-language)
    plagiarism detected by a separate AI model ({_esc(model)}).
    It analyses conceptual similarity between <strong>{_esc(src_l)}</strong> source documents
    and the <strong>{_esc(tgt_l)}</strong> submitted text.
    <strong>This percentage is independent and does NOT affect the Similarity Plagiarism
    score above.</strong>
  </div>

  <!-- Verdict card -->
  <div style="display:table;width:100%;border:0.5px solid #e2e8f0;
              background:#f0fdfa;border-radius:4px;margin-bottom:18px;">
    <div style="display:table-cell;width:135px;vertical-align:middle;
                text-align:center;padding:14px;">{donut}</div>
    <div style="display:table-cell;vertical-align:middle;padding:14px 20px;">
      <div style="font-size:40px;font-weight:800;color:{sem_color};line-height:1;">{pct:.1f}%</div>
      <div style="font-size:12px;font-weight:700;color:{sem_color};margin-top:4px;">
        {sem_label} SEMANTIC PLAGIARISM</div>
      <div style="font-size:10px;color:#64748b;margin-top:6px;line-height:1.5;">
        Conceptual similarity between {_esc(src_l)} sources and submitted {_esc(tgt_l)} text,
        detected using sentence embeddings (LaBSE, 768-dim, 109+ languages).
      </div>
    </div>
  </div>

  <!-- Stats row -->
  <div style="display:table;width:100%;border-collapse:collapse;
              border:0.5px solid #e2e8f0;margin-bottom:20px;border-radius:4px;">
    <div style="display:table-cell;width:25%;text-align:center;padding:10px 6px;
                border-right:0.5px solid #e2e8f0;">
      <div style="font-size:8px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;">Sentence Pairs</div>
      <div style="font-size:22px;font-weight:800;color:#0f172a;margin-top:3px;">{total}</div>
    </div>
    <div style="display:table-cell;width:25%;text-align:center;padding:10px 6px;
                border-right:0.5px solid #e2e8f0;">
      <div style="font-size:8px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;">Flagged Matches</div>
      <div style="font-size:22px;font-weight:800;color:#ef4444;margin-top:3px;">{flagged}</div>
    </div>
    <div style="display:table-cell;width:25%;text-align:center;padding:10px 6px;
                border-right:0.5px solid #e2e8f0;">
      <div style="font-size:8px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;">Avg Similarity</div>
      <div style="font-size:22px;font-weight:800;color:#0f766e;margin-top:3px;">{avg_sim:.0%}</div>
    </div>
    <div style="display:table-cell;width:25%;text-align:center;padding:10px 6px;">
      <div style="font-size:8px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;">Model F1-Score</div>
      <div style="font-size:22px;font-weight:800;color:#6366f1;margin-top:3px;">{f1:.4f}</div>
    </div>
  </div>

  <!-- External sources identified -->
  {"" if not sources else f"""
  <div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:6px;
              padding-bottom:5px;border-bottom:0.5px solid #e2e8f0;">
    External Sources Identified</div>
  <table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:20px;">
    <thead><tr style="background:#0f766e;color:white;">
      <td style="padding:7px 10px;font-weight:600;font-size:10px;text-transform:uppercase;">Source Document</td>
      <td style="padding:7px 10px;font-weight:600;font-size:10px;text-transform:uppercase;">URL / Reference</td>
    </tr></thead>
    <tbody>{src_rows}</tbody>
  </table>"""}

  <!-- Sentence pair analysis -->
  <div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:6px;
              padding-bottom:5px;border-bottom:0.5px solid #e2e8f0;">
    Sentence-Level Cross-Language Analysis</div>
  <p style="font-size:9px;color:#64748b;margin-bottom:10px;line-height:1.5;">
    Each row shows a submitted sentence (in {_esc(tgt_l)}) alongside the most
    semantically similar sentence found in {_esc(src_l)}-language source documents.
    Similarity is measured by cosine distance of LaBSE embeddings.
  </p>

  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
    <thead><tr style="background:#1e293b;color:white;">
      <td style="padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;">
        Submitted Sentence ({_esc(tgt_l)})</td>
      <td style="padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;">
        Matched Source ({_esc(src_l)})</td>
      <td style="padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;
                 text-align:center;">Similarity</td>
      <td style="padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;
                 text-align:center;">Status</td>
    </tr></thead>
    <tbody>{match_rows}</tbody>
  </table>

  <!-- Semantic model disclaimer -->
  <div style="margin-top:16px;padding:10px 12px;background:#f8fafc;
              border:0.5px solid #e2e8f0;border-radius:4px;
              font-size:8.5px;color:#64748b;line-height:1.6;">
    <strong>Semantic Model Details:</strong> {_esc(model)} &nbsp;|&nbsp;
    F1-Score: {f1} &nbsp;|&nbsp;
    Language pair: {_esc(src_l)} → {_esc(tgt_l)} &nbsp;|&nbsp;
    Threshold: cosine similarity ≥ 0.75 &nbsp;|&nbsp;
    Researcher: Abhayasiri S.A.U.D (IT21163968), SLIIT 2026.
    <br>
    <em>Note: The semantic model was trained on English–English SNLI pairs.
    Cross-language results are indicative; independent verification is recommended.</em>
  </div>
'''


# ── HTML template builder ──────────────────────────────────────────────────
def _build_html(doc_name, formatted_dt, plag_pct, verdict_label, verdict_color,
                total, plagiarised_count, clean_count, unique_n,
                donut_svg, source_rows, sent_html, semantic_data):

    font_face = ''
    if FONT_REGULAR:
        font_face += (f"@font-face{{font-family:'NotoSinhala';font-weight:400;"
                      f"src:url('{FONT_REGULAR}');}}\n")
    if FONT_MEDIUM:
        font_face += (f"@font-face{{font-family:'NotoSinhala';font-weight:600;"
                      f"src:url('{FONT_MEDIUM}');}}\n")

    semantic_html = _semantic_section(semantic_data) if semantic_data else ''

    return f"""<!DOCTYPE html>
<html lang="si">
<head>
<meta charset="utf-8"/>
<title>Plagiarism Report — {_esc(doc_name)}</title>
<style>
{font_face}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'NotoSinhala','Noto Sans Sinhala','DejaVu Sans',sans-serif;
  font-size:12px;color:#1e293b;background:#fff;}}
@page{{size:A4;margin:2cm 2cm 2.5cm 2cm;
  @bottom-left{{content:"Similarity.lk \2014 Sinhala Plagiarism Detection";
    font-size:8px;color:#94a3b8;}}
  @bottom-right{{content:"Page " counter(page) " of " counter(pages);
    font-size:8px;color:#94a3b8;}}}}
.accent-bar{{background:#4f46e5;color:white;text-align:center;padding:14px;
  font-size:16px;font-weight:700;letter-spacing:1px;border-radius:4px;margin-bottom:20px;}}
.info-table{{width:100%;border-collapse:collapse;margin-bottom:20px;font-size:11px;}}
.info-table td{{padding:7px 10px;border:0.5px solid #e2e8f0;}}
.info-table tr:nth-child(odd)  td{{background:#f8fafc;}}
.info-table tr:nth-child(even) td{{background:#fff;}}
.info-table .lbl{{color:#4f46e5;font-weight:700;width:90px;}}
.verdict-card{{display:table;width:100%;border:0.5px solid #e2e8f0;
  background:#f8fafc;border-radius:4px;margin-bottom:20px;}}
.verdict-left{{display:table-cell;width:135px;vertical-align:middle;
  text-align:center;padding:16px;}}
.verdict-right{{display:table-cell;vertical-align:middle;padding:16px 20px;}}
.verdict-pct{{font-size:44px;font-weight:800;color:{verdict_color};line-height:1;}}
.verdict-label{{font-size:13px;font-weight:700;color:{verdict_color};margin-top:4px;}}
.verdict-note{{font-size:10px;color:#64748b;margin-top:6px;line-height:1.5;}}
.stats-row{{display:table;width:100%;border-collapse:collapse;
  border:0.5px solid #e2e8f0;margin-bottom:28px;border-radius:4px;}}
.stat-cell{{display:table-cell;width:25%;text-align:center;padding:12px 8px;
  border-right:0.5px solid #e2e8f0;}}
.stat-cell:last-child{{border-right:none;}}
.stat-label{{font-size:9px;font-weight:700;color:#64748b;
  text-transform:uppercase;letter-spacing:0.5px;}}
.stat-val{{font-size:26px;font-weight:800;color:#0f172a;margin-top:4px;line-height:1;}}
.section-h{{font-size:14px;font-weight:700;color:#0f172a;margin-top:24px;
  margin-bottom:6px;padding-bottom:5px;border-bottom:0.5px solid #e2e8f0;}}
.src-table{{width:100%;border-collapse:collapse;font-size:11px;margin-bottom:24px;}}
.src-table thead tr{{background:#1e293b;color:#fff;}}
.src-table thead td{{padding:8px 12px;font-weight:600;font-size:10px;
  text-transform:uppercase;letter-spacing:0.4px;}}
.src-table tbody tr td{{border-bottom:0.5px solid #e2e8f0;}}
.legend-note{{font-size:9px;color:#64748b;margin-bottom:10px;line-height:1.5;}}
.analysis-wrap{{border:0.5px solid #e2e8f0;border-radius:4px;
  padding:10px 12px;background:#fff;}}
.page-break{{page-break-before:always;}}
.disclaimer{{margin-top:28px;padding-top:10px;border-top:0.5px solid #e2e8f0;
  font-size:8.5px;color:#94a3b8;line-height:1.6;}}
</style>
</head>
<body>

<!-- ══ PAGE 1 — COVER ══ -->
<div class="accent-bar">PLAGIARISM DETECTION REPORT</div>

<table class="info-table">
  <tr><td class="lbl">Document</td>  <td>{_esc(doc_name)}</td></tr>
  <tr><td class="lbl">Generated</td> <td>{_esc(formatted_dt)}</td></tr>
  <tr><td class="lbl">Tool</td>      <td>Similarity.lk &#8211; Sinhala Similarity Plagiarism Detection</td></tr>
  <tr><td class="lbl">Model</td>     <td>Random Forest Classifier &nbsp;|&nbsp; F1-Score: 0.9859 &nbsp;|&nbsp; Recall: 1.0000</td></tr>
</table>

<div class="verdict-card">
  <div class="verdict-left">{donut_svg}</div>
  <div class="verdict-right">
    <div class="verdict-pct">{plag_pct}%</div>
    <div class="verdict-label">{verdict_label}</div>
    <div class="verdict-note">
      This document has a <strong>Similarity Plagiarism</strong> score of
      <strong>{plag_pct}%</strong> based on sentence-level analysis.
      {"<br><span style='color:#0f766e;font-weight:600;'>&#10003; Semantic (cross-language) analysis also included — see last section.</span>" if semantic_data else ""}
    </div>
  </div>
</div>

<div class="stats-row">
  <div class="stat-cell">
    <div class="stat-label">Total Sentences</div>
    <div class="stat-val">{total}</div>
  </div>
  <div class="stat-cell">
    <div class="stat-label">Plagiarised</div>
    <div class="stat-val" style="color:#ef4444;">{plagiarised_count}</div>
  </div>
  <div class="stat-cell">
    <div class="stat-label">Original</div>
    <div class="stat-val" style="color:#22c55e;">{clean_count}</div>
  </div>
  <div class="stat-cell">
    <div class="stat-label">Unique Sources</div>
    <div class="stat-val" style="color:#6366f1;">{unique_n}</div>
  </div>
</div>

<!-- ══ PAGE 2 — SOURCES + DOCUMENT ANALYSIS ══ -->
<div class="page-break"></div>

<div class="section-h">Identified Sources — Similarity Analysis</div>
<table class="src-table">
  <thead><tr>
    <td style="width:40px;">Colour</td>
    <td>Source Name</td>
    <td style="width:70px;text-align:center;">Sentences</td>
    <td>URL / Reference</td>
  </tr></thead>
  <tbody>{source_rows}</tbody>
</table>

<div class="section-h">Document Analysis</div>
<p class="legend-note">
  <strong>Legend:</strong> Highlighted sentences indicate detected similarity plagiarism.
  Each colour corresponds to a unique source. Match confidence shown in brackets.
</p>
<div class="analysis-wrap">{sent_html}</div>

<div class="disclaimer">
  <strong>Disclaimer:</strong> This report is generated automatically by the
  Similarity.lk Sinhala Plagiarism Detection system (Random Forest, F1-Score 0.9859).
  Source attributions are indicative — verify independently.
  Researcher: Ranaweera R.R.M.I.M (IT21187414), SLIIT 2026.
</div>

{semantic_html}

</body></html>"""


# ── Rendering backends ─────────────────────────────────────────────────────
def _render_weasyprint(html_doc, report_path):
    from weasyprint import HTML
    HTML(string=html_doc, base_url='/').write_pdf(report_path)

def _render_playwright(html_doc, report_path):
    from playwright.sync_api import sync_playwright
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                     delete=False, encoding='utf-8') as tf:
        tf.write(html_doc); tmp_path = tf.name
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page    = browser.new_page()
            page.goto(pathlib.Path(tmp_path).as_uri())
            page.wait_for_load_state('networkidle')
            page.pdf(path=report_path, format='A4',
                     margin={'top':'2cm','bottom':'2.5cm',
                             'left':'2cm','right':'2cm'},
                     print_background=True)
            browser.close()
    finally:
        try: os.unlink(tmp_path)
        except: pass


# ── Public entry point ─────────────────────────────────────────────────────
def generate_report(report_path, doc_name, timestamp, results,
                    plagiarism_percentage, semantic_data=None):

    plag_pct = round(plagiarism_percentage, 1)
    verdict_label, verdict_color, _ = _verdict(plag_pct)
    total             = len(results)
    plagiarised_count = sum(1 for r in results if r['is_plagiarized'])
    clean_count       = total - plagiarised_count

    used_sources = {}
    for r in results:
        if r['is_plagiarized'] and r['source']:
            sid = r['source']['id']
            if sid not in used_sources:
                used_sources[sid] = {'source': r['source'], 'count': 0}
            used_sources[sid]['count'] += 1

    try:
        dt = datetime.strptime(timestamp, '%Y%m%d_%H%M%S')
        formatted_dt = dt.strftime('%B %d, %Y  %H:%M:%S')
    except Exception:
        formatted_dt = timestamp

    html_doc = _build_html(
        doc_name, formatted_dt, plag_pct, verdict_label, verdict_color,
        total, plagiarised_count, clean_count, len(used_sources),
        _donut_svg(plag_pct),
        _source_rows(used_sources),
        _sentence_rows(results),
        semantic_data,
    )

    errors = []
    try:
        _render_weasyprint(html_doc, report_path); return
    except Exception as e:
        errors.append(f'WeasyPrint: {e}')
    try:
        _render_playwright(html_doc, report_path); return
    except Exception as e:
        errors.append(f'Playwright: {e}')

    raise RuntimeError('All PDF backends failed:\n' + '\n'.join(errors))


# ===========================================================================
