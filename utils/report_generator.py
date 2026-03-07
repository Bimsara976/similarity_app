"""
PDF Report Generator — Multi-backend edition
============================================
Rendering strategy (tries in order):

  1. WeasyPrint  — Linux / macOS (uses Cairo + Pango + HarfBuzz via GTK)
  2. Playwright  — Windows + all platforms (headless Chromium, bundled HarfBuzz)
  3. ReportLab   — Universal fallback (Sinhala may not shape perfectly, but
                   generates a valid PDF rather than crashing)

Why multiple backends?
  WeasyPrint requires GTK3 DLLs (libgobject, libcairo, libpango).
  On Windows these are NOT bundled; users see:
      "cannot load library libgobject-2.0-0.dll: error0x7e"
  Playwright bundles its own Chromium + Skia + HarfBuzz — no OS dependencies.
"""

import os
import html as html_mod
from datetime import datetime

# ---------------------------------------------------------------------------
# Sinhala font paths (Noto Sans Sinhala — proper OpenType with GSUB/GPOS)
# ---------------------------------------------------------------------------
_NOTO_PATHS = [
    '/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansSinhala-Light.ttf',
    'C:/Windows/Fonts/NotoSansSinhala-Regular.ttf',
]
_NOTO_MED_PATHS = [
    '/usr/share/fonts/truetype/noto/NotoSansSinhala-Medium.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf',
    'C:/Windows/Fonts/NotoSansSinhala-Medium.ttf',
]

FONT_REGULAR = next((p for p in _NOTO_PATHS if os.path.exists(p)), None)
FONT_MEDIUM  = next((p for p in _NOTO_MED_PATHS if os.path.exists(p)), None) or FONT_REGULAR


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------
def _esc(text):
    return html_mod.escape(str(text))


def _verdict(pct):
    if pct < 25:   return ('LOW PLAGIARISM',      '#16a34a', '#dcfce7')
    elif pct < 50: return ('MODERATE PLAGIARISM', '#d97706', '#fef3c7')
    else:          return ('HIGH PLAGIARISM',     '#dc2626', '#fee2e2')


def _donut_svg(pct):
    r = 40
    circ = 2 * 3.14159 * r
    on   = round(circ * pct / 100, 2)
    off  = round(circ - on, 2)
    col  = '#22c55e' if pct < 25 else ('#f59e0b' if pct < 50 else '#ef4444')
    return (
        f'<svg viewBox="0 0 100 100" width="130" height="130">'
        f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="#e2e8f0" stroke-width="14"/>'
        f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="{col}" stroke-width="14"'
        f' stroke-dasharray="{on} {off}" stroke-linecap="round"'
        f' transform="rotate(-90 50 50)"/>'
        f'<text x="50" y="55" text-anchor="middle"'
        f' font-family="sans-serif" font-size="18" font-weight="bold"'
        f' fill="{col}">{pct:.0f}%</text></svg>'
    )


def _source_rows(used_sources):
    if not used_sources:
        return ('<tr><td colspan="4" style="padding:10px;color:#64748b;text-align:center;">'
                'No plagiarised sources identified.</td></tr>')
    rows = ''
    for i, (sid, info) in enumerate(used_sources.items()):
        src = info['source']
        bg  = '#f8fafc' if i % 2 == 0 else '#ffffff'
        rows += (
            f'<tr style="background:{bg};">'
            f'<td style="text-align:center;padding:7px 10px;">'
            f'<span style="display:inline-block;width:22px;height:22px;border-radius:4px;'
            f'background:{src["color_hex"]};border:1px solid rgba(0,0,0,.12);"></span></td>'
            f'<td style="padding:7px 12px;font-size:12px;color:#1e293b;">{_esc(src["name"])}</td>'
            f'<td style="padding:7px 12px;font-size:12px;text-align:center;'
            f'font-weight:700;color:#4f46e5;">{info["count"]}</td>'
            f'<td style="padding:7px 12px;font-size:11px;color:#6366f1;'
            f'word-break:break-all;">{_esc(src["url"])}</td>'
            f'</tr>'
        )
    return rows


def _sentence_rows(results):
    parts = []
    for r in results:
        sent   = _esc(r['sentence'])
        src    = r.get('source')
        conf   = r.get('confidence', 0.0)
        if r['is_plagiarized'] and src:
            bg  = src['color_hex']
            tc  = src['text_color']
            tag = (f'<span style="font-size:10px;font-weight:600;color:{tc};margin-left:6px;">'
                   f'&#9658; {_esc(src["name"])} ({conf*100:.0f}% match)</span>')
            parts.append(
                f'<p style="background:{bg};border-left:3px solid {tc};'
                f'padding:7px 10px;margin:4px 0;border-radius:3px;'
                f'font-size:12px;line-height:1.75;">{sent}{tag}</p>'
            )
        else:
            parts.append(
                f'<p style="padding:5px 10px;margin:4px 0;'
                f'font-size:12px;line-height:1.75;color:#1e293b;">{sent}</p>'
            )
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# HTML template builder
# ---------------------------------------------------------------------------
def _build_html(doc_name, formatted_dt, plag_pct, verdict_label, verdict_color,
                total, plagiarised_count, clean_count, unique_n,
                donut_svg, source_rows, sent_html):

    # Build @font-face only if we have the font file
    font_face = ''
    if FONT_REGULAR:
        font_face += (
            f"@font-face {{ font-family:'NotoSinhala'; font-weight:400; "
            f"src:url('{FONT_REGULAR}'); }}\n"
        )
    if FONT_MEDIUM:
        font_face += (
            f"@font-face {{ font-family:'NotoSinhala'; font-weight:600; "
            f"src:url('{FONT_MEDIUM}'); }}\n"
        )

    return f"""<!DOCTYPE html>
<html lang="si">
<head>
<meta charset="utf-8"/>
<title>Plagiarism Report</title>
<style>
{font_face}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  font-family:'NotoSinhala','Noto Sans Sinhala','Noto Sans','DejaVu Sans',sans-serif;
  font-size:12px;color:#1e293b;background:#fff;
}}
@page{{
  size:A4; margin:2cm 2cm 2.5cm 2cm;
  @bottom-left{{content:"Similarity.lk \2014 Sinhala Plagiarism Detection";font-size:8px;color:#94a3b8;}}
  @bottom-right{{content:"Page " counter(page) " of " counter(pages);font-size:8px;color:#94a3b8;}}
}}
.accent-bar{{background:#4f46e5;color:white;text-align:center;padding:14px;
  font-size:16px;font-weight:700;letter-spacing:1px;border-radius:4px;margin-bottom:20px;}}
.info-table{{width:100%;border-collapse:collapse;margin-bottom:20px;font-size:11px;}}
.info-table td{{padding:7px 10px;border:0.5px solid #e2e8f0;}}
.info-table tr:nth-child(odd)  td{{background:#f8fafc;}}
.info-table tr:nth-child(even) td{{background:#ffffff;}}
.info-table .lbl{{color:#4f46e5;font-weight:700;width:90px;}}
.verdict-card{{display:table;width:100%;border:0.5px solid #e2e8f0;
  background:#f8fafc;border-radius:4px;margin-bottom:20px;}}
.verdict-left{{display:table-cell;width:145px;vertical-align:middle;text-align:center;padding:16px;}}
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
.section-h{{font-size:14px;font-weight:700;color:#0f172a;
  margin-top:24px;margin-bottom:6px;padding-bottom:5px;
  border-bottom:0.5px solid #e2e8f0;}}
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
      This document has a plagiarism score of <strong>{plag_pct}%</strong>
      based on sentence-level similarity analysis.
    </div>
  </div>
</div>
<div class="stats-row">
  <div class="stat-cell"><div class="stat-label">Total Sentences</div>
    <div class="stat-val">{total}</div></div>
  <div class="stat-cell"><div class="stat-label">Plagiarised</div>
    <div class="stat-val" style="color:#ef4444;">{plagiarised_count}</div></div>
  <div class="stat-cell"><div class="stat-label">Original</div>
    <div class="stat-val" style="color:#22c55e;">{clean_count}</div></div>
  <div class="stat-cell"><div class="stat-label">Unique Sources</div>
    <div class="stat-val" style="color:#6366f1;">{unique_n}</div></div>
</div>
<div class="page-break"></div>
<div class="section-h">Identified Sources</div>
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
  <strong>Legend:</strong> Highlighted sentences indicate detected plagiarism.
  Each colour corresponds to a unique identified source (see legend above).
  Match confidence is shown in brackets.
</p>
<div class="analysis-wrap">{sent_html}</div>
<div class="disclaimer">
  <strong>Disclaimer:</strong> This report is generated automatically by the
  Similarity.lk Sinhala Plagiarism Detection system. Source attributions are
  indicative and should be verified independently.
  The system uses a Random Forest classifier trained on Sinhala sentence pairs
  (F1-Score 0.9859, Recall 1.0).
</div>
</body></html>"""


# ---------------------------------------------------------------------------
# Backend 1 — WeasyPrint (Linux / macOS, needs GTK3)
# ---------------------------------------------------------------------------
def _render_weasyprint(html_doc, report_path):
    from weasyprint import HTML
    HTML(string=html_doc, base_url='/').write_pdf(report_path)


# ---------------------------------------------------------------------------
# Backend 2 — Playwright / headless Chromium (cross-platform, no OS deps)
# ---------------------------------------------------------------------------
def _render_playwright(html_doc, report_path):
    from playwright.sync_api import sync_playwright

    # Convert local font file:// URIs to absolute paths for Chromium
    # (Chromium blocks file:// font loading in data URIs — write temp HTML file)
    import tempfile, pathlib

    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False, encoding='utf-8'
    ) as tf:
        tf.write(html_doc)
        tmp_path = tf.name

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page    = browser.new_page()
            page.goto(pathlib.Path(tmp_path).as_uri())
            page.wait_for_load_state('networkidle')
            page.pdf(
                path=report_path,
                format='A4',
                margin={'top': '2cm', 'bottom': '2.5cm',
                        'left': '2cm', 'right': '2cm'},
                print_background=True,
            )
            browser.close()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Backend 3 — ReportLab (universal fallback, Sinhala may not shape perfectly)
# ---------------------------------------------------------------------------
def _render_reportlab(doc_name, formatted_dt, plag_pct, verdict_label, verdict_color,
                      total, plagiarised_count, clean_count, unique_n,
                      used_sources, results, report_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, Color
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Register Sinhala font if available
    sinhala_font = 'Helvetica'
    if FONT_REGULAR and os.path.exists(FONT_REGULAR):
        try:
            pdfmetrics.registerFont(TTFont('NotoSinhala', FONT_REGULAR))
            sinhala_font = 'NotoSinhala'
        except Exception:
            pass

    INDIGO = HexColor('#4f46e5')
    NAVY   = HexColor('#0f172a')
    BORDER = HexColor('#e2e8f0')
    MUTED  = HexColor('#64748b')
    LIGHT  = HexColor('#f8fafc')
    V_COL  = HexColor(verdict_color)

    W = A4[0] - 4 * cm

    doc = SimpleDocTemplate(
        report_path, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm,
    )

    styles = getSampleStyleSheet()

    def ps(name, **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    story = []

    # Header bar
    hdr = Table([['PLAGIARISM DETECTION REPORT']], colWidths=[W])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,-1), INDIGO),
        ('TEXTCOLOR',     (0,0),(-1,-1), HexColor('#ffffff')),
        ('FONTNAME',      (0,0),(-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0),(-1,-1), 15),
        ('ALIGN',         (0,0),(-1,-1), 'CENTER'),
        ('TOPPADDING',    (0,0),(-1,-1), 13),
        ('BOTTOMPADDING', (0,0),(-1,-1), 13),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.4*cm))

    # Info
    info_rows = [
        ['Document',  doc_name],
        ['Generated', formatted_dt],
        ['Tool',      'Similarity.lk – Sinhala Similarity Plagiarism Detection'],
        ['Model',     'Random Forest | F1-Score: 0.9859 | Recall: 1.0000'],
    ]
    info_tbl = Table(info_rows, colWidths=[3*cm, W-3*cm])
    info_tbl.setStyle(TableStyle([
        ('FONTNAME',    (0,0),(0,-1), 'Helvetica-Bold'),
        ('FONTSIZE',    (0,0),(-1,-1), 9),
        ('TEXTCOLOR',   (0,0),(0,-1), INDIGO),
        ('TOPPADDING',  (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('LEFTPADDING', (0,0),(-1,-1), 8),
        ('ROWBACKGROUNDS',(0,0),(-1,-1), [LIGHT, HexColor('#ffffff')]),
        ('BOX',       (0,0),(-1,-1), 0.5, BORDER),
        ('INNERGRID', (0,0),(-1,-1), 0.5, BORDER),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.4*cm))

    # Verdict
    story.append(Paragraph(
        f'<font size="36" color="{verdict_color}"><b>{plag_pct}%</b></font>',
        ps('VP', alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        f'<font size="12" color="{verdict_color}"><b>{verdict_label}</b></font>',
        ps('VL', alignment=TA_CENTER, spaceAfter=6)
    ))

    # Stats
    stats_data = [
        ['Total Sentences', 'Plagiarised', 'Original', 'Unique Sources'],
        [str(total), str(plagiarised_count), str(clean_count), str(unique_n)],
    ]
    stats_tbl = Table(stats_data, colWidths=[W/4]*4)
    stats_tbl.setStyle(TableStyle([
        ('FONTNAME',  (0,0),(-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',  (0,0),(-1,0), 8),
        ('TEXTCOLOR', (0,0),(-1,0), MUTED),
        ('FONTNAME',  (0,1),(-1,1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0,1),(-1,1), 18),
        ('TEXTCOLOR', (0,1),(-1,1), NAVY),
        ('ALIGN',     (0,0),(-1,-1), 'CENTER'),
        ('TOPPADDING',(0,0),(-1,-1), 8),
        ('BOTTOMPADDING',(0,0),(-1,-1), 8),
        ('BOX',       (0,0),(-1,-1), 0.5, BORDER),
        ('INNERGRID', (0,0),(-1,-1), 0.5, BORDER),
    ]))
    story.append(Spacer(1, 0.3*cm))
    story.append(stats_tbl)
    story.append(PageBreak())

    # Sources
    story.append(Paragraph('Identified Sources',
        ps('H2', fontSize=13, fontName='Helvetica-Bold', textColor=NAVY,
           spaceBefore=10, spaceAfter=6)))
    story.append(HRFlowable(width='100%', thickness=0.5, color=BORDER))
    story.append(Spacer(1, 0.2*cm))

    if used_sources:
        src_hdr = [['Colour', 'Source Name', 'Count', 'URL']]
        src_data = src_hdr + [
            ['', info['source']['name'], str(info['count']), info['source']['url']]
            for info in used_sources.values()
        ]
        src_tbl = Table(src_data, colWidths=[1.2*cm, 5.5*cm, 1.5*cm, W-8.2*cm])
        src_style = [
            ('BACKGROUND',    (0,0),(-1,0), HexColor('#1e293b')),
            ('TEXTCOLOR',     (0,0),(-1,0), HexColor('#ffffff')),
            ('FONTNAME',      (0,0),(-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0),(-1,-1), 8),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING',    (0,0),(-1,-1), 6),
            ('BOTTOMPADDING', (0,0),(-1,-1), 6),
            ('LEFTPADDING',   (0,0),(-1,-1), 6),
            ('ROWBACKGROUNDS',(0,1),(-1,-1), [HexColor('#f8fafc'), HexColor('#ffffff')]),
            ('BOX',       (0,0),(-1,-1), 0.5, BORDER),
            ('INNERGRID', (0,0),(-1,-1), 0.5, BORDER),
        ]
        for i, info in enumerate(used_sources.values()):
            r, g, b = info['source']['color_rgb']
            src_style.append(('BACKGROUND', (0, i+1), (0, i+1),
                               Color(r/255, g/255, b/255)))
        src_tbl.setStyle(TableStyle(src_style))
        story.append(src_tbl)

    story.append(Spacer(1, 0.4*cm))

    # Sentences
    story.append(Paragraph('Document Analysis',
        ps('H2b', fontSize=13, fontName='Helvetica-Bold', textColor=NAVY,
           spaceBefore=10, spaceAfter=6)))
    story.append(HRFlowable(width='100%', thickness=0.5, color=BORDER))
    story.append(Spacer(1, 0.2*cm))

    body_st = ps('Body', fontSize=9, fontName=sinhala_font, leading=14, spaceAfter=3)

    for r in results:
        safe = (r['sentence']
                .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        src  = r.get('source')
        conf = r.get('confidence', 0.0)
        if r['is_plagiarized'] and src:
            col_r, col_g, col_b = src['color_rgb']
            bg  = Color(col_r/255, col_g/255, col_b/255)
            tag = (f'<font size="7" color="{src["text_color"]}">'
                   f' > {src["name"]} ({conf*100:.0f}% match)</font>')
            st = ps(f'P_{r["index"]}', fontSize=9, fontName=sinhala_font,
                    leading=14, spaceAfter=3, backColor=bg,
                    borderPadding=(3, 5, 3, 5))
            story.append(Paragraph(safe + tag, st))
        else:
            story.append(Paragraph(safe, body_st))

    doc.build(story)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def generate_report(report_path, doc_name, timestamp, results, plagiarism_percentage):
    plag_pct          = round(plagiarism_percentage, 1)
    verdict_label, verdict_color, _verdict_bg = _verdict(plag_pct)
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
        _donut_svg(plag_pct), _source_rows(used_sources), _sentence_rows(results)
    )

    # ── Try backends in order ──────────────────────────────────────────────
    errors = []

    # 1. WeasyPrint (works on Linux/macOS with GTK3)
    try:
        _render_weasyprint(html_doc, report_path)
        return
    except Exception as e:
        errors.append(f'WeasyPrint: {e}')

    # 2. Playwright / headless Chromium (cross-platform, no OS GTK dependency)
    try:
        _render_playwright(html_doc, report_path)
        return
    except Exception as e:
        errors.append(f'Playwright: {e}')

    # 3. ReportLab fallback (always available, Sinhala shaping may be imperfect)
    try:
        _render_reportlab(
            doc_name, formatted_dt, plag_pct, verdict_label, verdict_color,
            total, plagiarised_count, clean_count, len(used_sources),
            used_sources, results, report_path
        )
        return
    except Exception as e:
        errors.append(f'ReportLab: {e}')

    raise RuntimeError(
        'All PDF backends failed. Details:\n' + '\n'.join(errors)
    )
