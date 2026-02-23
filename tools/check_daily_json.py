import json

p = r"docs\data\daily\2026-02-22.json"
with open(p, encoding="utf-8") as f:
    data = json.load(f)

if isinstance(data, list):
    rows = data
else:
    rows = (data.get("rows") or data.get("data") or [])

print("rows=", len(rows))

dates = sorted({r.get("date") for r in rows if isinstance(r, dict) and r.get("date")})
print("unique_dates=", dates[:10], "count=", len(dates))

keys = ["diff_medals", "max_medals", "total_start", "bb", "rb"]

for k in keys:
    miss = sum(1 for r in rows if (not isinstance(r, dict)) or (r.get(k) is None))
    print(k, "missing=", miss)

def is_number(v):
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        s = v.replace(",", "").strip()
        if s == "":
            return False
        try:
            float(s)
            return True
        except Exception:
            return False
    return False

for k in keys:
    nonnum = sum(
        1
        for r in rows
        if isinstance(r, dict)
        and r.get(k) is not None
        and not is_number(r.get(k))
    )
    print(k, "non_numeric=", nonnum)

print("first_row=", rows[0] if rows else None)