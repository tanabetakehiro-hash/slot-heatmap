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
.hr{margin:14px 0;border:0;border-top:1px solid #ddd}
.subtabs{display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 12px}
.pill{padding:6px 10px; border:1px solid #aaa; border-radius:999px; cursor:pointer; background:#fff; font-size:0.9em}
.pill.active{border-color:#000; font-weight:700}
.block{display:none}
.block.active{display:block}
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


def period_df(df: pd.DataFrame, dates: list[str]):
    d = df[df["date"].isin(dates)].copy()
    d["diff_medals"] = pd.to_numeric(d.get("diff_medals"), errors="coerce")
    d = d.dropna(subset=["diff_medals", "machine_id", "machine_name", "date"])
    return d


def _metric_tables_machine(d: pd.DataFrame, title: str):
    """
    機種別：MAX/AVG/SUMはプラス差枚のみ、WINはプラス率
    """
    # 集計ベース
    d_valid = d.copy()
    d_pos = d_valid[d_valid["diff_medals"] > 0].copy()

    if d_valid.empty:
        empty = f"<h3>{title}（機種別）</h3><p>該当データなし</p>"
        return {"max": empty, "avg": empty, "sum": empty, "win": empty}

    # units/days
    units_map = d_valid.groupby("machine_name")["machine_id"].nunique().to_dict()
    days_map = d_valid.groupby("machine_name")["date"].nunique().to_dict()

    # WIN率（%）
    pos_days = d_valid.assign(pos=(d_valid["diff_medals"] > 0).astype(int))
    win = pos_days.groupby("machine_name").agg(
        win_rate=("pos", "mean"),
        samples=("pos", "count"),
    ).reset_index()
    win["units"] = win["machine_name"].map(units_map).fillna(0).astype(int)
    win["days"] = win["machine_name"].map(days_map).fillna(0).astype(int)
    win["win_rate"] = (win["win_rate"] * 100).round(1)

    win = win.sort_values(["win_rate", "samples"], ascending=False).head(50)
    win_html = f"<h3>{title}（機種別 / 勝率）</h3>"
    win_html += '<p class="note">勝率=（差枚が取れた日のうちプラスだった割合） / units=台数 / days=日数 / samples=レコード数</p>'
    win_html += win[["machine_name", "units", "days", "win_rate", "samples"]].to_html(index=False)

    # MAX/AVG/SUM（プラスのみ）
    if d_pos.empty:
        empty_pos = f"<h3>{title}（機種別）</h3><p>プラス差枚がありません</p>"
        return {"max": empty_pos, "avg": empty_pos, "sum": empty_pos, "win": win_html}

    # MAX（プラスのみ）: 最大を出した台と日も
    idx = d_pos.groupby("machine_name")["diff_medals"].idxmax()
    best = d_pos.loc[idx, ["machine_name", "machine_id", "date", "diff_medals"]].copy()
    best = best.rename(columns={
        "machine_id": "best_machine_id",
        "date": "best_day",
        "diff_medals": "max_plus",
    })
    best["units"] = best["machine_name"].map(units_map).fillna(0).astype(int)
    best["days"] = best["machine_name"].map(days_map).fillna(0).astype(int)
    best["max_plus"] = best["max_plus"].round(0).astype(int)
    best = best.sort_values(["max_plus"], ascending=False).head(50)

    max_html = f"<h3>{title}（機種別 / MAX）</h3>"
    max_html += '<p class="note">MAX=期間内最大差枚（プラスのみ） / best_machine_id=最大を出した台 / best_day=日付</p>'
    max_html += best[["machine_name", "units", "days", "max_plus", "best_day", "best_machine_id"]].to_html(index=False)

    # AVG/SUM（プラスのみ）
    ag = d_pos.groupby("machine_name").agg(
        avg_plus=("diff_medals", "mean"),
        sum_plus=("diff_medals", "sum"),
        pos_samples=("diff_medals", "count"),
    ).reset_index()
    ag["units"] = ag["machine_name"].map(units_map).fillna(0).astype(int)
    ag["days"] = ag["machine_name"].map(days_map).fillna(0).astype(int)
    ag["avg_plus"] = ag["avg_plus"].round(1)
    ag["sum_plus"] = ag["sum_plus"].round(0).astype(int)

    avg = ag.sort_values(["avg_plus", "pos_samples"], ascending=False).head(50)
    avg_html = f"<h3>{title}（機種別 / 平均）</h3>"
    avg_html += '<p class="note">平均=プラス差枚のみの平均 / pos_samples=プラス差枚のレコード数</p>'
    avg_html += avg[["machine_name", "units", "days", "avg_plus", "pos_samples"]].to_html(index=False)

    summ = ag.sort_values(["sum_plus", "pos_samples"], ascending=False).head(50)
    sum_html = f"<h3>{title}（機種別 / 合計）</h3>"
    sum_html += '<p class="note">合計=プラス差枚のみの合計 / pos_samples=プラス差枚のレコード数</p>'
    sum_html += summ[["machine_name", "units", "days", "sum_plus", "pos_samples"]].to_html(index=False)

    return {"max": max_html, "avg": avg_html, "sum": sum_html, "win": win_html}


def _metric_tables_unit(d: pd.DataFrame, title: str):
    """
    台別：MAX/AVG/SUMはプラス差枚のみ、WINはプラス率
    """
    d_valid = d.copy()
    d_pos = d_valid[d_valid["diff_medals"] > 0].copy()

    if d_valid.empty:
        empty = f"<h3>{title}（台別）</h3><p>該当データなし</p>"
        return {"max": empty, "avg": empty, "sum": empty, "win": empty}

    # days
    days_map = d_valid.groupby("machine_id")["date"].nunique().to_dict()
    # 機種名（最後の表記）
    name_map = d_valid.sort_values(["date"]).groupby("machine_id")["machine_name"].last().to_dict()

    # WIN
    pos_days = d_valid.assign(pos=(d_valid["diff_medals"] > 0).astype(int))
    win = pos_days.groupby("machine_id").agg(
        win_rate=("pos", "mean"),
        samples=("pos", "count"),
    ).reset_index()
    win["machine_name"] = win["machine_id"].map(name_map)
    win["days"] = win["machine_id"].map(days_map).fillna(0).astype(int)
    win["win_rate"] = (win["win_rate"] * 100).round(1)
    win = win.sort_values(["win_rate", "samples"], ascending=False).head(50)

    win_html = f"<h3>{title}（台別 / 勝率）</h3>"
    win_html += '<p class="note">勝率=（差枚が取れた日のうちプラスだった割合） / samples=レコード数</p>'
    win_html += win[["machine_id", "machine_name", "days", "win_rate", "samples"]].to_html(index=False)

    # MAX/AVG/SUM（プラスのみ）
    if d_pos.empty:
        empty_pos = f"<h3>{title}（台別）</h3><p>プラス差枚がありません</p>"
        return {"max": empty_pos, "avg": empty_pos, "sum": empty_pos, "win": win_html}

    # MAX
    idx = d_pos.groupby("machine_id")["diff_medals"].idxmax()
    best = d_pos.loc[idx, ["machine_id", "date", "diff_medals"]].copy()
    best = best.rename(columns={"date": "best_day", "diff_medals": "max_plus"})
    best["machine_name"] = best["machine_id"].map(name_map)
    best["days"] = best["machine_id"].map(days_map).fillna(0).astype(int)
    best["max_plus"] = best["max_plus"].round(0).astype(int)
    best = best.sort_values(["max_plus"], ascending=False).head(50)

    max_html = f"<h3>{title}（台別 / MAX）</h3>"
    max_html += '<p class="note">MAX=期間内最大差枚（プラスのみ） / best_day=日付</p>'
    max_html += best[["machine_id", "machine_name", "days", "max_plus", "best_day"]].to_html(index=False)

    # AVG/SUM
    ag = d_pos.groupby("machine_id").agg(
        avg_plus=("diff_medals", "mean"),
        sum_plus=("diff_medals", "sum"),
        pos_samples=("diff_medals", "count"),
    ).reset_index()
    ag["machine_name"] = ag["machine_id"].map(name_map)
    ag["days"] = ag["machine_id"].map(days_map).fillna(0).astype(int)
    ag["avg_plus"] = ag["avg_plus"].round(1)
    ag["sum_plus"] = ag["sum_plus"].round(0).astype(int)

    avg = ag.sort_values(["avg_plus", "pos_samples"], ascending=False).head(50)
    avg_html = f"<h3>{title}（台別 / 平均）</h3>"
    avg_html += '<p class="note">平均=プラス差枚のみの平均 / pos_samples=プラス差枚のレコード数</p>'
    avg_html += avg[["machine_id", "machine_name", "days", "avg_plus", "pos_samples"]].to_html(index=False)

    summ = ag.sort_values(["sum_plus", "pos_samples"], ascending=False).head(50)
    sum_html = f"<h3>{title}（台別 / 合計）</h3>"
    sum_html += '<p class="note">合計=プラス差枚のみの合計 / pos_samples=プラス差枚のレコード数</p>'
    sum_html += summ[["machine_id", "machine_name", "days", "sum_plus", "pos_samples"]].to_html(index=False)

    return {"max": max_html, "avg": avg_html, "sum": sum_html, "win": win_html}


def metric_switch_block(block_id_prefix: str, machine_tables: dict, unit_tables: dict):
    """
    block_id_prefix 例: "p1" / "p7" / "p30"
    """
    # 初期は max
    html = []
    html.append("""
<div class="subtabs">
  <button class="pill active" data-m="max">MAX</button>
  <button class="pill" data-m="avg">平均</button>
  <button class="pill" data-m="sum">合計</button>
  <button class="pill" data-m="win">勝率</button>
</div>
""".strip())

    # 機種別
    for m in ["max", "avg", "sum", "win"]:
        active = " active" if m == "max" else ""
        html.append(f'<div class="block{active}" data-kind="machine" data-metric="{m}" id="{block_id_prefix}_machine_{m}">{machine_tables[m]}</div>')

    html.append('<hr class="hr"/>')

    # 台別
    for m in ["max", "avg", "sum", "win"]:
        active = " active" if m == "max" else ""
        html.append(f'<div class="block{active}" data-kind="unit" data-metric="{m}" id="{block_id_prefix}_unit_{m}">{unit_tables[m]}</div>')

    # 切替JS（期間ブロック内だけを操作）
    html.append(f"""
<script>
(function() {{
  const root = document.getElementById("{block_id_prefix}_root");
  const pills = root.querySelectorAll(".pill");
  function setMetric(m) {{
    pills.forEach(p => p.classList.toggle("active", p.getAttribute("data-m") === m));
    root.querySelectorAll(".block").forEach(b => {{
      b.classList.toggle("active", b.getAttribute("data-metric") === m);
    }});
  }}
  pills.forEach(p => {{
    p.addEventListener("click", function() {{
      setMetric(p.getAttribute("data-m"));
    }});
  }});
}})();
</script>
""".strip())

    return "\n".join(html)


def ranking_section(df: pd.DataFrame, dates: list[str], title: str, prefix: str):
    d = period_df(df, dates)
    mt = _metric_tables_machine(d, title)
    ut = _metric_tables_unit(d, title)
    inner = metric_switch_block(prefix, mt, ut)
    return f'<div id="{prefix}_root">{inner}</div>'


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

    # ranking（期間タブ + 指標ピル切替）
    d1 = [latest_day]
    d7 = last_n_dates(df, 7, latest_day)
    d30 = last_n_dates(df, 30, latest_day)

    sec1 = ranking_section(df, d1, f"差枚ランキング（{latest_day} / 1日）", "p1")
    sec7 = ranking_section(df, d7, f"差枚ランキング（直近7日）" + (f"：{d7[0]}〜{d7[-1]}" if d7 else ""), "p7")
    sec30 = ranking_section(df, d30, f"差枚ランキング（直近30日）" + (f"：{d30[0]}〜{d30[-1]}" if d30 else ""), "p30")

    ranking_html = f"""
<h1>差枚ランキング（プラス系指標 + 勝率）</h1>
<p class="note">
MAX/平均/合計は「プラス差枚のみ」で計算。勝率は「差枚が取れた日のうちプラスだった割合」。
各期間ごとに「機種別（まとめ）」→（区切り線）→「台別」を表示します。
</p>

<div class="btns">
  <button class="btn active" data-target="sec1">最新日</button>
  <button class="btn" data-target="sec7">直近7日</button>
  <button class="btn" data-target="sec30">直近30日</button>
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
