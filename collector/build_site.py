import json
import glob
from pathlib import Path
import pandas as pd

DATA_DIR = Path("data/daily")
DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def load_all_rows():
    files = sorted(glob.glob(str(DATA_DIR / "*.json")))
    rows = []
    for f in files:
        try:
            data = json.load(open(f, encoding="utf-8"))
            if isinstance(data, list):
                rows.extend(data)
        except Exception:
            continue
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # 型整形
    for c in ["bb", "rb", "art", "total_start", "max_medals", "diff_medals"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = df["date"].astype(str)
    df["machine_id"] = df["machine_id"].astype(str).str.zfill(4)
    df["machine_name"] = df["machine_name"].fillna("UNKNOWN").astype(str)
    return df


def write_style_css():
    css = """\
:root{--bg:#0b0f19;--card:#111827;--text:#e5e7eb;--muted:#9ca3af;--line:#1f2937;--accent:#60a5fa;}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial; background:var(--bg); color:var(--text);}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
header{padding:18px 16px;border-bottom:1px solid var(--line);background:rgba(17,24,39,.7);backdrop-filter: blur(8px);position:sticky;top:0;z-index:10}
h1{margin:0;font-size:18px}
.container{max-width:1100px;margin:0 auto;padding:14px 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0;box-shadow:0 10px 30px rgba(0,0,0,.25)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
label{font-size:12px;color:var(--muted)}
select,input[type=checkbox]{margin-left:6px}
.small{font-size:12px;color:var(--muted)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid var(--line);font-size:12px;color:var(--muted)}
.table-wrap{overflow:auto;border-radius:12px;border:1px solid var(--line)}
table{border-collapse:collapse;width:100%;min-width:900px}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;font-size:13px;white-space:nowrap}
th{position:sticky;top:0;background:#0f172a;z-index:5}
td.num{text-align:right;font-variant-numeric: tabular-nums}
.legend{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.swatch{width:16px;height:16px;border-radius:4px;border:1px solid var(--line)}
hr{border:none;border-top:1px solid var(--line);margin:10px 0}
"""
    (DOCS_DIR / "style.css").write_text(css, encoding="utf-8")


def build_index_html():
    html = f"""\
<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>slot-heatmap</title>
<link rel="stylesheet" href="style.css">
</head><body>
<header><div class="container"><h1>slot-heatmap</h1><div class="small">差枚が取れない日は自動で最大持玉で表示します</div></div></header>
<div class="container">
  <div class="card">
    <div class="row">
      <a class="badge" href="heatmap.html">差枚/最大持玉 ヒートマップ</a>
      <a class="badge" href="ranking.html">ランキング</a>
    </div>
    <hr>
    <div class="small">
      ・machine4 が一時停止中（Service temporarily unavailable）のときは、差枚が null になります。<br>
      ・その場合、このサイトは自動で「最大持玉」で集計します。<br>
      ・プラスだけ表示は「差枚モード」のときだけ有効です。
    </div>
  </div>
</div>
</body></html>
"""
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")


def build_pages(df: pd.DataFrame):
    if df.empty:
        # 空ページ
        (DOCS_DIR / "heatmap.html").write_text(empty_page("heatmap"), encoding="utf-8")
        (DOCS_DIR / "ranking.html").write_text(empty_page("ranking"), encoding="utf-8")
        return

    dates = sorted(df["date"].dropna().unique().tolist())
    machine_names = sorted(df["machine_name"].dropna().unique().tolist())

    # JSONを埋め込む（静的サイト用）
    payload = df[
        ["date", "machine_id", "machine_name", "bb", "rb", "art", "total_start", "max_medals", "diff_medals"]
    ].to_dict(orient="records")

    data_js = json.dumps(
        {
            "dates": dates,
            "machine_names": machine_names,
            "rows": payload,
        },
        ensure_ascii=False,
    )

    build_heatmap_html(data_js)
    build_ranking_html(data_js)


def empty_page(kind: str) -> str:
    title = "ヒートマップ" if kind == "heatmap" else "ランキング"
    return f"""\
<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="style.css"></head>
<body>
<header><div class="container"><h1>{title}</h1><div class="small"><a href="index.html">← 戻る</a></div></div></header>
<div class="container"><div class="card">データがありません。先に collector/collect_daily.py を実行してください。</div></div>
</body></html>
"""


def build_heatmap_html(data_js: str):
    html = f"""\
<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ヒートマップ</title>
<link rel="stylesheet" href="style.css">
</head><body>
<header><div class="container">
  <h1>ヒートマップ</h1>
  <div class="small"><a href="index.html">← 戻る</a></div>
</div></header>

<div class="container">
  <div class="card">
    <div class="row">
      <div>
        <label>機種（絞り込み）
          <select id="machineName"></select>
        </label>
      </div>
      <div>
        <label>表示指標
          <select id="metric">
            <option value="auto">自動（差枚→取れなければ最大持玉）</option>
            <option value="diff_medals">差枚</option>
            <option value="max_medals">最大持玉</option>
          </select>
        </label>
      </div>
      <div>
        <label>プラスだけ（差枚のみ）
          <input type="checkbox" id="plusOnly">
        </label>
      </div>
      <div class="badge" id="modeBadge">-</div>
      <div class="small" id="note"></div>
    </div>
  </div>

  <div class="card">
    <div class="legend">
      <span class="small">色：表示中の指標の最大値を基準（最大=濃い）</span>
      <span class="swatch" style="background:rgb(255,220,220)"></span><span class="small">プラス</span>
      <span class="swatch" style="background:rgb(220,220,255)"></span><span class="small">マイナス</span>
      <span class="swatch" style="background:rgb(30,41,59)"></span><span class="small">データなし</span>
    </div>
    <hr>
    <div class="table-wrap"><div id="table"></div></div>
  </div>
</div>

<script>
const DATA = {data_js};

function esc(s) {{
  return String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}}

function toNum(v) {{
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}}

function pickMetric(rows, userChoice) {{
  if (userChoice && userChoice !== "auto") return userChoice;
  // auto: その画面の対象データで diff が1つでもあれば diff、なければ max
  const hasDiff = rows.some(r => toNum(r.diff_medals) !== null);
  return hasDiff ? "diff_medals" : "max_medals";
}}

function modeText(metric) {{
  return metric === "diff_medals" ? "差枚" : "最大持玉";
}}

function noteText(metric, rows) {{
  if (metric === "max_medals") {{
    // diffが無いからmaxになった可能性が高いのでメッセージ出す
    const hasDiff = rows.some(r => toNum(r.diff_medals) !== null);
    if (!hasDiff) return "※ 差枚が取得できないため最大持玉で表示中（machine4が一時停止中の可能性）";
  }}
  return "";
}}

function colorFor(v, metric, maxAbs) {{
  if (v === null) return "rgb(30,41,59)";
  if (maxAbs <= 0) return "rgb(30,41,59)";
  // 差枚はプラス/マイナス色分け。最大持玉はプラス色固定。
  if (metric === "max_medals") {{
    const t = Math.min(1, Math.max(0, v / maxAbs));
    const r = Math.round(255 - 0 * t);
    const g = Math.round(220 - 120 * t);
    const b = Math.round(220 - 120 * t);
    return `rgb(${{r}},${{g}},${{b}})`;
  }} else {{
    const t = Math.min(1, Math.max(0, Math.abs(v) / maxAbs));
    if (v >= 0) {{
      const r = Math.round(255 - 0 * t);
      const g = Math.round(220 - 120 * t);
      const b = Math.round(220 - 120 * t);
      return `rgb(${{r}},${{g}},${{b}})`;
    }} else {{
      const r = Math.round(220 - 120 * t);
      const g = Math.round(220 - 120 * t);
      const b = Math.round(255 - 0 * t);
      return `rgb(${{r}},${{g}},${{b}})`;
    }}
  }}
}}

function buildTable(rows, metric, plusOnly) {{
  // 横：日付、縦：台番号
  const dates = Array.from(new Set(rows.map(r => r.date))).sort();
  const ids = Array.from(new Set(rows.map(r => r.machine_id))).sort();

  // 値マップ
  const map = new Map();
  for (const r of rows) {{
    const key = r.machine_id + "||" + r.date;
    const val = toNum(r[metric]);
    map.set(key, val);
  }}

  // maxAbs（色の基準。最大値で濃く）
  let maxAbs = 0;
  for (const r of rows) {{
    const v = toNum(r[metric]);
    if (v === null) continue;
    if (metric === "diff_medals") {{
      if (plusOnly && v <= 0) continue;
      maxAbs = Math.max(maxAbs, Math.abs(v));
    }} else {{
      maxAbs = Math.max(maxAbs, v);
    }}
  }}

  // 表（plusOnlyの場合は、行全体でプラスが1つもない台は薄く）
  let html = "<table><thead><tr><th>台番号</th>";
  for (const d of dates) html += `<th>${{esc(d)}}</th>`;
  html += "</tr></thead><tbody>";

  for (const id of ids) {{
    html += `<tr><td>${{esc(id)}}</td>`;
    for (const d of dates) {{
      const key = id + "||" + d;
      const v = map.has(key) ? map.get(key) : null;

      let show = v;
      if (metric === "diff_medals" && plusOnly) {{
        if (v === null || v <= 0) show = null; // プラスだけ表示
      }}

      const bg = colorFor(show, metric, maxAbs);
      const txt = (show === null) ? "" : String(show);
      html += `<td class="num" style="background:${{bg}}" data-v="${{show===null?"":show}}">${{esc(txt)}}</td>`;
    }}
    html += "</tr>";
  }}

  html += "</tbody></table>";
  return {{ html, maxAbs }};
}}

function render() {{
  const machineSel = document.getElementById("machineName");
  const metricSel = document.getElementById("metric");
  const plusOnly = document.getElementById("plusOnly").checked;

  const chosen = machineSel.value;
  const rows0 = DATA.rows.filter(r => chosen === "__ALL__" ? true : r.machine_name === chosen);

  const metric = pickMetric(rows0, metricSel.value);

  // plusOnlyは差枚以外は強制OFF
  const plusOk = (metric === "diff_medals") ? plusOnly : false;
  document.getElementById("plusOnly").disabled = (metric !== "diff_medals");

  document.getElementById("modeBadge").textContent = "表示：" + modeText(metric);
  document.getElementById("note").textContent = noteText(metric, rows0);

  const built = buildTable(rows0, metric, plusOk);
  document.getElementById("table").innerHTML = built.html;
}}

function init() {{
  const machineSel = document.getElementById("machineName");
  machineSel.innerHTML = `<option value="__ALL__">全機種</option>` +
    DATA.machine_names.map(n => `<option value="${{esc(n)}}">${{esc(n)}}</option>`).join("");

  document.getElementById("metric").addEventListener("change", render);
  document.getElementById("machineName").addEventListener("change", render);
  document.getElementById("plusOnly").addEventListener("change", render);

  render();
}}
init();
</script>

</body></html>
"""
    (DOCS_DIR / "heatmap.html").write_text(html, encoding="utf-8")


def build_ranking_html(data_js: str):
    html = f"""\
<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ランキング</title>
<link rel="stylesheet" href="style.css">
</head><body>
<header><div class="container">
  <h1>ランキング</h1>
  <div class="small"><a href="index.html">← 戻る</a></div>
</div></header>

<div class="container">
  <div class="card">
    <div class="row">
      <div>
        <label>日付
          <select id="dateSel"></select>
        </label>
      </div>
      <div>
        <label>機種（絞り込み）
          <select id="machineName"></select>
        </label>
      </div>
      <div>
        <label>表示指標
          <select id="metric">
            <option value="auto">自動（差枚→取れなければ最大持玉）</option>
            <option value="diff_medals">差枚</option>
            <option value="max_medals">最大持玉</option>
          </select>
        </label>
      </div>
      <div>
        <label>プラスだけ（差枚のみ）
          <input type="checkbox" id="plusOnly">
        </label>
      </div>
      <div class="badge" id="modeBadge">-</div>
      <div class="small" id="note"></div>
    </div>
  </div>

  <div class="card">
    <div class="table-wrap"><div id="table"></div></div>
  </div>
</div>

<script>
const DATA = {data_js};

function esc(s) {{
  return String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}}
function toNum(v) {{
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}}
function pickMetric(rows, userChoice) {{
  if (userChoice && userChoice !== "auto") return userChoice;
  const hasDiff = rows.some(r => toNum(r.diff_medals) !== null);
  return hasDiff ? "diff_medals" : "max_medals";
}}
function modeText(metric) {{
  return metric === "diff_medals" ? "差枚" : "最大持玉";
}}
function noteText(metric, rows) {{
  if (metric === "max_medals") {{
    const hasDiff = rows.some(r => toNum(r.diff_medals) !== null);
    if (!hasDiff) return "※ 差枚が取得できないため最大持玉で表示中（machine4が一時停止中の可能性）";
  }}
  return "";
}}

function buildRanking(rows, metric, plusOnly) {{
  const list = [];
  for (const r of rows) {{
    const v = toNum(r[metric]);
    if (v === null) continue;
    if (metric === "diff_medals" && plusOnly && v <= 0) continue;
    list.push({{
      machine_id: r.machine_id,
      machine_name: r.machine_name,
      value: v,
      bb: toNum(r.bb),
      rb: toNum(r.rb),
      art: toNum(r.art),
      total_start: toNum(r.total_start),
      max_medals: toNum(r.max_medals),
      diff_medals: toNum(r.diff_medals),
    }});
  }}
  list.sort((a,b) => b.value - a.value);
  return list;
}}

function render() {{
  const dateSel = document.getElementById("dateSel").value;
  const machineSel = document.getElementById("machineName").value;
  const metricSel = document.getElementById("metric").value;
  const plusOnlyChk = document.getElementById("plusOnly").checked;

  let rows = DATA.rows.filter(r => r.date === dateSel);
  if (machineSel !== "__ALL__") rows = rows.filter(r => r.machine_name === machineSel);

  const metric = pickMetric(rows, metricSel);
  const plusOk = (metric === "diff_medals") ? plusOnlyChk : false;
  document.getElementById("plusOnly").disabled = (metric !== "diff_medals");

  document.getElementById("modeBadge").textContent = "表示：" + modeText(metric);
  document.getElementById("note").textContent = noteText(metric, rows);

  const ranking = buildRanking(rows, metric, plusOk);

  let html = "<table><thead><tr>";
  html += "<th>順位</th><th>台番号</th><th>機種</th>";
  html += `<th>${{metric === "diff_medals" ? "差枚" : "最大持玉"}}</th>`;
  html += "<th>BB</th><th>RB</th><th>AT/ART</th><th>累計</th>";
  html += "</tr></thead><tbody>";

  if (ranking.length === 0) {{
    html += `<tr><td colspan="8" class="small">該当データなし（この指標が全てnull、またはプラスだけで絞り込み）</td></tr>`;
  }} else {{
    const topN = Math.min(50, ranking.length);
    for (let i=0;i<topN;i++) {{
      const r = ranking[i];
      html += "<tr>";
      html += `<td class="num">${{i+1}}</td>`;
      html += `<td>${{esc(r.machine_id)}}</td>`;
      html += `<td>${{esc(r.machine_name)}}</td>`;
      html += `<td class="num">${{esc(r.value)}}</td>`;
      html += `<td class="num">${{r.bb ?? ""}}</td>`;
      html += `<td class="num">${{r.rb ?? ""}}</td>`;
      html += `<td class="num">${{r.art ?? ""}}</td>`;
      html += `<td class="num">${{r.total_start ?? ""}}</td>`;
      html += "</tr>";
    }}
  }}

  html += "</tbody></table>";
  document.getElementById("table").innerHTML = html;
}}

function init() {{
  const dateSel = document.getElementById("dateSel");
  dateSel.innerHTML = DATA.dates.map(d => `<option value="${{esc(d)}}">${{esc(d)}}</option>`).join("");
  dateSel.value = DATA.dates[DATA.dates.length - 1];

  const machineSel = document.getElementById("machineName");
  machineSel.innerHTML = `<option value="__ALL__">全機種</option>` +
    DATA.machine_names.map(n => `<option value="${{esc(n)}}">${{esc(n)}}</option>`).join("");

  document.getElementById("metric").addEventListener("change", render);
  document.getElementById("dateSel").addEventListener("change", render);
  document.getElementById("machineName").addEventListener("change", render);
  document.getElementById("plusOnly").addEventListener("change", render);

  render();
}}
init();
</script>

</body></html>
"""
    (DOCS_DIR / "ranking.html").write_text(html, encoding="utf-8")


def main():
    df = load_all_rows()
    write_style_css()
    build_index_html()
    build_pages(df)
    print("Built docs/: index.html heatmap.html ranking.html style.css")


if __name__ == "__main__":
    main()
