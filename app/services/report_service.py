"""
Report service — compiles a completed Inspection into a clean, self-contained
HTML report (Jinja2 templated inline, no external file dependency) suitable
for browser rendering, printing to PDF, or saving to disk for the demo
pipeline.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, select_autoescape

from app.config import settings
from app.models.inspection import Inspection

_SEVERITY_COLORS = {
    "Low": "#2563eb",
    "Medium": "#d97706",
    "High": "#ea580c",
    "Critical": "#dc2626",
}

_CONDITION_STYLES = {
    "GOOD": ("#166534", "#dcfce7", "PASS"),
    "ACCEPTABLE": ("#854d0e", "#fef9c3", "PASS"),
    "POOR": ("#9a3412", "#ffedd5", "FAIL"),
    "CRITICAL": ("#991b1b", "#fee2e2", "FAIL"),
}

_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Inspection Report — {{ inspection.id }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    background: #f3f4f6; margin: 0; padding: 32px; color: #111827;
  }
  .sheet { max-width: 860px; margin: 0 auto; background: #fff; border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
  .header { padding: 28px 32px; border-bottom: 1px solid #e5e7eb; display: flex;
    justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; }
  .header h1 { margin: 0 0 4px; font-size: 20px; }
  .header .company { color: #6b7280; font-size: 13px; }
  .badge { display: inline-block; padding: 8px 18px; border-radius: 999px; font-weight: 700;
    font-size: 14px; letter-spacing: 0.02em; }
  .meta { padding: 20px 32px; display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px; background: #fafafa; border-bottom: 1px solid #e5e7eb; font-size: 13px; }
  .meta div span.label { display:block; color:#6b7280; font-size:11px; text-transform:uppercase;
    letter-spacing:0.05em; margin-bottom: 2px; }
  section { padding: 24px 32px; border-bottom: 1px solid #e5e7eb; }
  section:last-child { border-bottom: none; }
  h2 { font-size: 15px; text-transform: uppercase; letter-spacing: 0.04em; color: #374151;
    margin: 0 0 14px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #f0f0f0; }
  th { color: #6b7280; font-weight: 600; font-size: 12px; text-transform: uppercase; }
  .defect-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px 16px; margin-bottom: 10px; }
  .defect-card .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;}
  .sev-pill { color:#fff; font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px; }
  .rec { color:#374151; font-size:13px; margin-top:6px; }
  .rec strong { color:#111827; }
  .hazard-list { margin: 0; padding-left: 18px; }
  .hazard-list li { color: #991b1b; margin-bottom: 4px; }
  .summary-box { background:#f9fafb; border-left:4px solid #2563eb; padding:14px 16px; border-radius:6px;
    font-size:14px; line-height:1.5; }
  .no-defects { color:#166534; font-size:14px; }
  .footer { padding: 16px 32px; font-size: 11px; color: #9ca3af; text-align: center; }
  @media print { body { background:#fff; padding:0; } .sheet { box-shadow:none; border-radius:0; } }
</style>
</head>
<body>
  <div class="sheet">
    <div class="header">
      <div>
        <h1>Field Inspection Report</h1>
        <div class="company">{{ company_name }} &middot; Inspection ID: {{ inspection.id }}</div>
        {% if inspection.inspector_name or inspection.inspector_email %}
        <div class="company" style="margin-top:2px;">
          Submitted by
          <strong>{{ inspection.inspector_name or 'Unknown inspector' }}</strong>{% if inspection.inspector_email %} ({{ inspection.inspector_email }}){% endif %}
        </div>
        {% endif %}
      </div>
      <span class="badge" style="color:{{ cond_fg }}; background:{{ cond_bg }};">
        {{ cond_label }} &mdash; {{ inspection.overall_condition.value if inspection.overall_condition else 'N/A' }}
      </span>
    </div>

    <div class="meta">
      <div><span class="label">Inspector</span>{{ inspection.inspector_name or '—' }}</div>
      <div><span class="label">Inspector Email</span>{{ inspection.inspector_email or '—' }}</div>
      <div><span class="label">Site / Location</span>{{ inspection.site_location or '—' }}</div>
      <div><span class="label">Date</span>{{ inspection.created_at.strftime('%Y-%m-%d %H:%M UTC') }}</div>
      <div><span class="label">Status</span>{{ inspection.status.value }}</div>
    </div>

    <section>
      <h2>Asset Metadata (OCR / Visual ID)</h2>
      <table>
        <tr><th>Asset Type</th><th>Manufacturer</th><th>Model No.</th><th>Serial / Tag No.</th><th>Confidence</th></tr>
        <tr>
          <td>{{ asset.asset_type if asset else '—' }}</td>
          <td>{{ asset.manufacturer if asset and asset.manufacturer else '—' }}</td>
          <td>{{ asset.model_number if asset and asset.model_number else '—' }}</td>
          <td>{{ asset.serial_or_tag_number if asset and asset.serial_or_tag_number else '—' }}</td>
          <td>{{ '%.0f'|format((asset.confidence_score or 0) * 100) }}%</td>
        </tr>
      </table>
    </section>

    <section>
      <h2>Summary</h2>
      <div class="summary-box">{{ inspection.overall_summary or 'No summary available.' }}</div>
    </section>

    <section>
      <h2>Detected Defects ({{ defects|length }})</h2>
      {% if defects %}
        {% for d in defects %}
        <div class="defect-card">
          <div class="top">
            <strong>{{ d.defect_type }}</strong>
            <span class="sev-pill" style="background:{{ severity_colors.get(d.severity.value, '#6b7280') }};">
              {{ d.severity.value }}
            </span>
          </div>
          <div style="font-size:13px; color:#6b7280;">Location: {{ d.location_description or '—' }}</div>
          <div class="rec"><strong>Recommendation:</strong> {{ d.recommendation or '—' }}</div>
        </div>
        {% endfor %}
      {% else %}
        <p class="no-defects">No visual defects detected.</p>
      {% endif %}
    </section>

    <section>
      <h2>Safety &amp; Compliance</h2>
      <p><strong>Compliant:</strong> {{ 'Yes' if inspection.is_compliant else 'No' if inspection.is_compliant is not none else '—' }}
         &nbsp;|&nbsp;
         <strong>Immediate Action Required:</strong>
         {{ 'YES — ESCALATE' if inspection.immediate_action_required else 'No' }}
      </p>
      {% if inspection.safety_hazards_detected %}
        <ul class="hazard-list">
          {% for h in inspection.safety_hazards_detected %}<li>{{ h }}</li>{% endfor %}
        </ul>
      {% else %}
        <p class="no-defects">No safety hazards detected.</p>
      {% endif %}
    </section>

    <div class="footer">
      Report generated by FieldCheck AI on {{ generated_at }}, submitted by {{ inspection.inspector_name or 'an unnamed inspector' }}{% if inspection.inspector_email %} ({{ inspection.inspector_email }}){% endif %}.
      Vision provider: {{ inspection.vision_provider_used or 'mock' }}.
      This report is AI-assisted and should be reviewed by a qualified inspector before final sign-off.
    </div>
  </div>
</body>
</html>
"""

_env = Environment(autoescape=select_autoescape(["html"]))
_template = _env.from_string(_TEMPLATE)


def render_inspection_html(inspection: Inspection) -> str:
    """Render a completed (or in-progress) Inspection ORM object to a
    self-contained HTML report string."""
    condition_key = inspection.overall_condition.value if inspection.overall_condition else None
    cond_fg, cond_bg, cond_label = _CONDITION_STYLES.get(
        condition_key, ("#374151", "#e5e7eb", "PENDING")
    )

    return _template.render(
        inspection=inspection,
        asset=inspection.asset,
        defects=inspection.defects,
        company_name=settings.company_name,
        severity_colors=_SEVERITY_COLORS,
        cond_fg=cond_fg,
        cond_bg=cond_bg,
        cond_label=cond_label,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )


def save_report_to_disk(inspection: Inspection, output_dir: Path | None = None) -> Path:
    """Render and persist the HTML report to `REPORT_OUTPUT_DIR` (used by the
    demo pipeline). Returns the written file path."""
    out_dir = output_dir or settings.report_output_path
    out_dir.mkdir(parents=True, exist_ok=True)
    html = render_inspection_html(inspection)
    path = out_dir / f"inspection_{inspection.id}.html"
    path.write_text(html, encoding="utf-8")
    return path
