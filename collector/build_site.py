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
table{border-collapse:collapse; width:100%}
td,th{border:1px solid #ccc;padding:6px; text-align:right; white-space:nowrap}
th{text-align:center; position:sticky; top:0; background:#fff; z-index:2}
td:first-child, th:first-child{text-align:center}
.note{color:#666;font-size:0.9em}
.small{font-size:0.85em}
.hm-wrap{overflow:auto; border:1px solid #ddd; max-height:75vh}
.hm td{min-width:88px}
.legend{display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:10px 0}
.swatch{width:46px; height:14px; border:1px solid #ccc}
.btns{display:flex; gap:8px; flex-wrap:wrap; margin:10px 0}
.btn{padding:8px 10px; border:1px solid #aaa; border-radius:8px; cursor:pointer; background:#fff}
.btn.active{border-color:#000; font-weight:700}
.section{display:none}
.section.active{display:block}
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

    script = f"""
<script>
(function() {{
  const cap = {float(cap_abs)};
  const cells = document.querySelectorAll('td[data-v]');
  cells.forEach(function(td) {{
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
    td.style.backgroundColor = "rgb(" + r + "," + g + "," + b + ")";
    td.style.color = "#111";
  }});
}})();
</script>
"""
    parts.append(script)
    return "\n".join(parts)


def last_n_dates(df: pd.DataFrame, n: int, latest_day: str):
    ds = sorted([str(x) for x in df["date"].dropna().unique() if str(x) <= latest_day])
    return ds[-n:] if len(ds) >= 1 else []


def ranking_table_for_dates_max(df: pd.DataFrame, dates: list[str], title: str):
    """
    期間内の「最大差枚(MAX)」でランキング
    max_day = 最大差枚を出した日付
    days = 期間内にデータがある日数
    """
    d = df[df["date"].isin(dates)].copy()
    d = d.dropna(subset=["diff_medals"])
    if d.empty:
        return f"<h2>{title}</h2><p>該当データなし</p>"

    # 台ごとに最大差枚とその日付を取る
    d["diff_medals"] = pd.to_numeric(d["diff_medals"], errors="coerce")
    d = d.dropna(subset=["diff_medals"])

    # machine_name は最後に見つかったものを採用
    name_map = (
        d.sort_values(["date"])
        .groupby("machine_id")["machine_name"]
        .last()
        .to_dict()
    )

    # days
    days_map = d.groupby("machine_id")["date"].nunique().to_dict()

    # max と日付
    idx = d.groupby("machine_id")["diff_medals"].idxmax()
    best = d.loc[idx, ["machine_id", "date", "diff_medals"]].copy()
    best = best.rename(columns={"date": "max_day", "diff_medals": "max_diff"})
    best["machine_name"] = best["machine_id"].map(name_map)
    best["days"] = best["machine_id"].map(days_map).fillna(0).astype(int)
    best["max_diff"] = best["max_diff"].round(0).astype(int)

    best = best.sort_values(["max_diff"], ascending=False).head(50)

    html = f"<h2>{title}</h2>"
    html += '<p class="note">max=期間内最大差枚 / max_day=最大差枚の日付 / days=データがある日数</p>'
    html += best[["machine_id", "machine_name", "days", "max_diff", "max_day"]].to_html(index=False)
    return html


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

    # index
    body = f"<h1>最新日: {latest_day}</h1><p>総レコード: {len(df)}</p>"
    body += '<p class="note">※ 差枚(diff_medals) を元に集計しています</p>'
    if events:
        body += "<h2>イベント</h2><ul>"
        for e in events[-30:]:
            body += f"<li>{e.get('date','')}：{e.get('title','')}（{e.get('memo','')}）</li>"
        body += "</ul>"
    save_page("index.html", "トップ", body)

    # ranking: 最新日 / 直近7日 / 直近30日（MAX）
    d1 = [latest_day]
    d7 = last_n_dates(df, 7, latest_day)
    d30 = last_n_dates(df, 30, latest_day)

    sec1 = ranking_table_for_dates_max(df, d1, f"差枚ランキング（{latest_day} / 1日）")
    sec7 = ranking_table_for_dates_max(df, d7, f"差枚ランキング（直近7日 MAX：{d7[0]}〜{d7[-1]}）" if d7 else "差枚ランキング（直近7日 MAX）")
    sec30 = ranking_table_for_dates_max(df, d30, f"差枚ランキング（直近30日 MAX：{d30[0]}〜{d30[-1]}）" if d30 else "差枚ランキング（直近30日 MAX）")

    ranking_html = f"""
<h1>差枚ランキング（期間内 最大値 MAX）</h1>
<div class="btns">
  <button class="btn active" data-target="sec1">最新日</button>
  <button class="btn" data-target="sec7">直近7日 MAX</button>
  <button class="btn" data-target="sec30">直近30日 MAX</button>
</div>

<div id="sec1" class="section active">{sec1}</div>
<div id="sec7" class="section">{sec7}</div>
<div id="sec30" class="section">{sec30}</div>

<script>
(function() {{
  const btns = document.querySelectorAll('.btn');
  const secs = document.querySelectorAll('.section');
  btns.forEach(function(b) {{
    b.addEventListener('click', function() {{
      btns.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      const t = b.getAttribute('data-target');
      secs.forEach(function(s) {{
        if (s.id === t) s.classList.add('active');
        else s.classList.remove('active');
      }});
    }});
  }});
}})();
</script>
""".strip()

    save_page("ranking.html", "差枚ランキング", ranking_html)

    # heatmap
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