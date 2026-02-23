import argparse
import json
import os
import re
from glob import glob
from datetime import datetime

def norm_unit(x) -> str:
    if x is None:
        return ""
    return str(x).strip()

def extract_rows(daily_json):
    if isinstance(daily_json, list):
        return daily_json
    if isinstance(daily_json, dict):
        for k in ("rows", "data", "machines"):
            v = daily_json.get(k)
            if isinstance(v, list):
                return v
    return []

def pick_latest_daily_file(search_dirs):
    candidates = []
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        candidates += glob(os.path.join(d, "*.json"))
    # 2026-02-21.json みたいなファイル名を優先して最新日を選ぶ
    def key(p):
        base = os.path.basename(p)
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.json$", base)
        if m:
            try:
                return (1, datetime.strptime(m.group(1), "%Y-%m-%d"), p)
            except:
                pass
        # だめなら更新時刻
        return (0, datetime.fromtimestamp(os.path.getmtime(p)), p)
    candidates.sort(key=key, reverse=True)
    return candidates[0] if candidates else None

def sort_units(units):
    def unit_key(u):
        # 数値化できるものは数値順、できないものは文字列
        try:
            return (0, int(u))
        except:
            return (1, u)
    return sorted(units, key=unit_key)

def build_layout(units, cols, cell_w, cell_h, gap_x, gap_y, margin_x, margin_y):
    units_sorted = sort_units(units)
    machines = []
    for i, unit in enumerate(units_sorted):
        col = i % cols
        row = i // cols
        x = margin_x + col * (cell_w + gap_x)
        y = margin_y + row * (cell_h + gap_y)
        machines.append({
            "unit_no": unit,
            "x": x,
            "y": y,
            "w": cell_w,
            "h": cell_h,
            "label": unit
        })
    rows = max(1, (len(units_sorted) + cols - 1) // cols)
    width = margin_x * 2 + cols * cell_w + (cols - 1) * gap_x
    height = margin_y * 2 + rows * cell_h + (rows - 1) * gap_y
    return {
        "width": width,
        "height": height,
        "machines": machines
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD（省略で最新）")
    ap.add_argument("--cols", type=int, default=20)
    ap.add_argument("--cell-w", type=int, default=86)
    ap.add_argument("--cell-h", type=int, default=56)
    ap.add_argument("--gap-x", type=int, default=10)
    ap.add_argument("--gap-y", type=int, default=10)
    ap.add_argument("--margin-x", type=int, default=18)
    ap.add_argument("--margin-y", type=int, default=18)
    ap.add_argument("--out", default="docs/data/floor_layout.json")
    args = ap.parse_args()

    # 日別JSONの候補ディレクトリ（あなたの構成に合わせて両方探す）
    search_dirs = [
        os.path.join("docs", "data", "daily"),
        os.path.join("data", "daily"),
    ]

    daily_path = None
    if args.date:
        # 指定日
        for d in search_dirs:
            p = os.path.join(d, f"{args.date}.json")
            if os.path.isfile(p):
                daily_path = p
                break
        if not daily_path:
            raise SystemExit(f"指定日のJSONが見つかりません: {args.date}（探索: {search_dirs}）")
    else:
        # 最新
        daily_path = pick_latest_daily_file(search_dirs)
        if not daily_path:
            raise SystemExit(f"日別JSONが見つかりません（探索: {search_dirs}）")

    with open(daily_path, "r", encoding="utf-8") as f:
        daily_json = json.load(f)

    rows = extract_rows(daily_json)
    if not rows:
        raise SystemExit(f"日別JSONの中身が配列ではありません: {daily_path}")

    units = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        u = norm_unit(r.get("unit_no") or r.get("machine_id") or r.get("n") or r.get("unit"))
        if u:
            units.add(u)

    if not units:
        raise SystemExit(f"台番号が取れません（unit_no / machine_id 等が見つからない）: {daily_path}")

    layout = build_layout(
        units=units,
        cols=args.cols,
        cell_w=args.cell_w,
        cell_h=args.cell_h,
        gap_x=args.gap_x,
        gap_y=args.gap_y,
        margin_x=args.margin_x,
        margin_y=args.margin_y
    )

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)

    print("OK")
    print(" daily:", daily_path)
    print(" machines:", len(layout["machines"]))
    print(" out:", args.out)
    print(" size:", layout["width"], "x", layout["height"])

if __name__ == "__main__":
    main()