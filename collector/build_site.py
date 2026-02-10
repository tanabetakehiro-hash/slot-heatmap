import json
from pathlib import Path
import pandas as pd

DATA_DIR = Path("data/daily")
SITE_DIR = Path("site")

def load_latest():
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        return None, None
    latest = files[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    return latest.stem, pd.DataFrame(data)

def save_page(name, title, body):
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    html = f"""<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<style>
body{{font-family:system-ui;margin:16px;line-height:1.6}}
table{{border-collapse:collapse}} td,th{{border:1px solid #ccc;padding:6px}}
nav a{{margin-right:10px}}
</style>
</head><body>
<nav><a href="index.html">トップ</a> | <a href="ranking.html">ランキング</a> | <a href="heatmap.html">ヒートマップ</a></nav><hr/>
{body}
</body></html>"""
    (SITE_DIR / name).write_text(html, encoding="utf-8")

def main():
    day, df = load_latest()
    if df is None or df.empty:
        save_page("index.html","トップ","<h1>データがありません</h1>")
        return

    save_page("index.html","トップ",f"<h1>最新日: {day}</h1><p>件数: {len(df)}</p>")

    df["max_medals"] = pd.to_numeric(df["max_medals"], errors="coerce")
    rank = df.sort_values("max_medals", ascending=False).head(50)
    save_page("ranking.html","ランキング",
              f"<h1>最大持玉ランキング（{day}）</h1>" +
              rank[["machine_id","machine_name","bb","rb","art","max_medals"]].to_html(index=False))

    pivot = df.pivot_table(index="machine_id", values="max_medals", aggfunc="max")
    save_page("heatmap.html","ヒートマップ",
              f"<h1>ヒートマップ（仮：最大持玉 / {day}）</h1>" + pivot.to_html())

    print("OK: site/ を更新しました")

if __name__ == "__main__":
    main()