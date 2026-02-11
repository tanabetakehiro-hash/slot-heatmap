import json
from pathlib import Path
import pandas as pd
import math

DATA_DIR = Path("data/daily")
SITE_DIR = Path("docs")  # GitHub Pages は /docs
EVENTS_PATH = Path("data/events/events.json")


def load_all():
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        return pd.DataFrame()
    rows = []
    for f in files:
        try:
            rows.extend(json.loads(f.read_text(encoding="utf-8")))
        except:
            pass
    return pd.DataFrame(rows)


def load_events():
    if not EVENTS_PATH.exists():
        return []
    try:
        return json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    except:
        return []


def ensure_css():
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    css = SITE_DIR / "style.css"
    css.write_text(
        """
body{font-family:system-ui;margin:16px;line-height:1.6}
nav a{margin-right:10px}
table{border-collapse:collapse}
td,th{border:1px solid #ccc;padding:6px; text-align:right; white-space:nowrap}
th{text-align:center; position:sticky; top:0; background:#fff; z-index:2}
td:first-child, th:first-child{position:sticky; left:0; background:#fff; z-index:3; text-align:center}
.note{color:#666;font-size:0.9em}
.small{font-size:0.85em}
.hm-wrap{overflow:auto; border:1px solid #ddd; max-height:75vh}
.hm td{min-width:88px}
.legend{display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:10px 0}
.swatch{width:46px; height:14px; border:1px solid #ccc}
""".strip(),
        encoding="utf-8"
    )


def save_page(name, title, body):
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    html = f"""<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<link rel="stylesheet" href="style.css"/>
</head><body>
<nav>
<a href="index.html">トップ</a> |
<a href="ranking.html">差枚ランキング</a> |
<a href="heatmap.html">差枚ヒートマップ</a>
</nav><hr/>
{body}
</body></html>"""
    (SITE_DIR / name).write_text(html, encoding="utf-8")


def safe_num(x):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return float(x)
    except:
        return None


def build_heatmap_html(pivot: pd.DataFrame, cap_abs: float):
    dates = list(pivot.columns)
    mids = list(pivot.index)

    legend = f"""
<div class="legend">
  <div class="small note">色の基準（最大濃さ）: ±{int(cap_abs)}枚</div>
  <div class="swatch" style="background:rgb(255,220,220)"></div><div class="small">プラス</div>
  <div class="swatch" style="background:rgb(220,220,255)"></div><div class="small">マイナス</div>
</div>
"""

    parts = []
    parts.append(legend)
    parts.append('<div class="hm-wrap">')
    parts.append('<table class="hm">')
    parts.append("<thead><tr><th>台番号</th>")
    for d in dates:
        parts.append(f"<th>{d}</th>")
    parts.append("</tr></thead><tbody>")

    for mid in mids:
        parts.append(f"<tr><td><b>{mid}</b></td>")
        row = pivot.loc[mid]
        for d in dates:
            v = safe_num(row.get(d))
            if v is None:
                parts.append('<td data-v=""></td>')
            else:
                parts.append(f'<td data-v="{v:.0f}">{int(v)}</td>')
        parts.append("</tr>")

    parts.append("</tbody></table></div>")

    # ★ここがポイント：Python f-string と JS の ${} が衝突するので {{ }} でエスケープ
    script = f"""
<script>
(function() {{
  const cap = {float(cap_abs)};
  const cells = document.querySelectorAll('td[data-v]');
  cells.forEach(td => {{
    const s = td.getAttribute('data-v');
    if (!s) return;
    const v = parseFloat(s);
    const a = Math.min(Math.abs(v) / cap, 1.0);

    let r=255, g=255, b=255;
    if (v > 0) {{
      r = 255;
      g = Math.round(255 - 110*a);
      b = Math.round(255 - 110*a);
    }} else if (v < 0) {{
      r = Math.round(255 - 110*a);
      g = Math.round(255 - 110*a);
      b = 255;
    }}

    td.style.backgroundColor = `rgb(${{r}},${{g}},${{b}})`;
    td.style.color = '#111';
  }});
}})();
</script>
"""
    parts.append(script)
    return "\n".join(parts)


def main():
    ensure_css()
    df = load_all()
    events = load_events()

    if df.empty:
        save_page("index.html", "トップ", "<h1>データがありません</h1>")
        save_page("ranking.html", "差枚ランキング", "<h1>データがありません</h1>")
        save_page("heatmap.html", "差枚ヒートマップ", "<h1>データがありません</h1>")
        print("data/daily が空なので空ページを作りました")
        return

    for col in ["bb", "rb", "art", "total_start", "max_medals", "diff_medals"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    latest_day = str(df["date"].dropna().max())
    body = f"<h1>最新日: {latest_day}</h1><p>総レコード: {len(df)}</p>"
    body += '<p class="note">※ 差枚(diff_medals) を元に集計しています</p>'

    if events:
        body += "<h2>イベント</h2><ul>"
        for e in events[-30:]:
            body += f"<li>{e.get('date','')}：{e.get('title','')}（{e.get('memo','')}）</li>"
        body += "</ul>"

    save_page("index.html", "トップ", body)

    dfl = df[df["date"] == latest_day].copy()
    dfl = dfl.dropna(subset=["diff_medals"])
    rank = dfl.sort_values("diff_medals", ascending=False).head(50)
    ranking_html = f"<h1>差枚ランキング（{latest_day}）</h1>"
    cols = [c for c in ["machine_id","machine_name","bb","rb","art","total_start","max_medals","diff_medals"] if c in rank.columns]
    ranking_html += rank[cols].to_html(index=False)
    save_page("ranking.html", "差枚ランキング", ranking_html)

    dfh = df.dropna(subset=["date", "machine_id"]).copy()
    dfh["machine_id"] = dfh["machine_id"].astype(str)

    pivot = dfh.pivot_table(index="machine_id", columns="date", values="diff_medals", aggfunc="last")
    pivot = pivot.sort_index()
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)

    vals = dfh["diff_medals"].dropna().astype(float)
    if len(vals) == 0:
        cap_abs = 1000.0
    else:
        cap_abs = float(vals.abs().quantile(0.90))
        cap_abs = max(cap_abs, 1000.0)

    heat_html = "<h1>差枚ヒートマップ（台番号 × 日付）</h1>"
    heat_html += '<p class="note">赤=プラス / 青=マイナス（濃いほど絶対値が大きい）</p>'
    heat_html += build_heatmap_html(pivot.fillna(""), cap_abs)

    save_page("heatmap.html", "差枚ヒートマップ", heat_html)

    print("OK: docs/ を更新しました")


if __name__ == "__main__":
    main()
