# src/report_export.py
"""Render an organizer report (see organizer.generate_report) to CSV or a standalone HTML page."""

import csv
from html import escape


def write_report_csv(path, report):
    counts = {item["name"]: item["count"] for item in report["popular_categories"]}
    size_map = {item["name"]: item for item in report["space_by_category"]}
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["FLCL File Organizer - Report"])
        writer.writerow(["Files organized", report["organized_files"]])
        writer.writerow(["Errors", len(report["errors"])])
        writer.writerow([])
        writer.writerow(["Category", "Files", "Size (bytes)", "Size (human)"])
        for name, count in counts.items():
            size = size_map.get(name, {"size_bytes": 0, "size_human": "0 B"})
            writer.writerow([name, count, size["size_bytes"], size["size_human"]])
        writer.writerow([])
        writer.writerow(["Timestamp", "Files", "Names"])
        for entry in report["recent_history"]:
            writer.writerow([entry.get("timestamp", "unknown"), entry.get("count", 0), "; ".join(entry.get("files", []))])


def render_report_html(report, palette):
    """Return a self-contained HTML report styled with ``palette``; every report value is escaped."""
    p = palette
    counts = {item["name"]: item["count"] for item in report["popular_categories"]}
    size_map = {item["name"]: item["size_human"] for item in report["space_by_category"]}
    names = sorted({*counts, *size_map}, key=lambda name: (-counts.get(name, 0), name))
    max_count = max(counts.values()) if counts else 1
    rows = []
    for index, name in enumerate(names):
        width = int(counts.get(name, 0) / max_count * 100)
        color = p["series"][index % len(p["series"])]
        rows.append(
            f'<div class="cat"><span class="name">{escape(name)}</span>'
            f'<div class="bar"><div class="fill" style="width:{width}%;background:{color}"></div></div>'
            f'<span class="count">{counts.get(name, 0)} file(s) · {escape(size_map.get(name, "0 B"))}</span></div>'
        )
    errors = "".join(f"<li>{escape(str(error))}</li>" for error in report["errors"][:20]) or '<li class="empty">No recorded errors</li>'
    history = "".join(
        f"<li><time>{escape(str(entry.get('timestamp') or 'unknown'))}</time> {entry.get('count', 0)} file(s)"
        f"<small>{escape(', '.join(entry.get('files', [])))}</small></li>"
        for entry in report["recent_history"][:20]
    ) or '<li class="empty">No recorded operations</li>'
    top = escape(report["popular_categories"][0]["name"]) if report["popular_categories"] else "None"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FLCL File Organizer - Report</title>
<style>
:root {{ --window:{p["window"]}; --panel:{p["panel"]}; --surface:{p["surface"]}; --border:{p["border"]};
  --text:{p["text"]}; --muted:{p["muted"]}; --accent:{p["accent"]}; --alt:{p["accent_alt"]}; --error:{p["error"]}; }}
* {{ box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--window); color: var(--text); margin: 0; padding: 32px 16px; }}
main {{ max-width: 920px; margin: 0 auto; }}
h1 {{ font-size: 28px; letter-spacing: .08em; margin: 0 0 4px; color: var(--accent); }}
h1 + p {{ color: var(--muted); margin: 0 0 24px; }}
h2 {{ font-size: 13px; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); margin: 32px 0 12px; }}
.metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
.metric {{ background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 16px 18px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .1em; }}
.metric b {{ display: block; margin-top: 6px; font-size: 26px; color: var(--text); letter-spacing: 0; text-transform: none; }}
.metric:first-child b {{ color: var(--accent); }}
.panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 16px 18px; }}
.cat {{ display: grid; grid-template-columns: minmax(90px, 160px) 1fr auto; align-items: center; gap: 12px; margin: 10px 0; }}
.name {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.bar {{ background: var(--surface); border-radius: 999px; height: 12px; overflow: hidden; }}
.fill {{ height: 100%; border-radius: 999px; animation: grow .8s cubic-bezier(.2,.8,.2,1) both; transform-origin: left; }}
.count {{ color: var(--muted); font-size: 13px; white-space: nowrap; }}
ul {{ list-style: none; margin: 0; padding: 0; }}
li {{ padding: 10px 0; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; }}
li:last-child {{ border-bottom: 0; }}
li small {{ display: block; color: var(--muted); }}
li time {{ color: var(--alt); margin-right: 8px; }}
.errors li {{ color: var(--error); }}
.empty {{ color: var(--muted) !important; }}
@keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
@media (prefers-reduced-motion: reduce) {{ .fill {{ animation: none; }} }}
</style>
</head>
<body>
<main>
<h1>FLCL FILE ORGANIZER</h1>
<p>Organization report</p>
<div class="metrics">
<div class="metric">Files organized<b>{report["organized_files"]}</b></div>
<div class="metric">Top category<b>{top}</b></div>
<div class="metric">Errors<b>{len(report["errors"])}</b></div>
</div>
<h2>Categories</h2>
<div class="panel">{''.join(rows) or '<p class="empty">No categorised files yet</p>'}</div>
<h2>Recent operations</h2>
<div class="panel"><ul>{history}</ul></div>
<h2>Errors</h2>
<div class="panel"><ul class="errors">{errors}</ul></div>
</main>
</body>
</html>"""
