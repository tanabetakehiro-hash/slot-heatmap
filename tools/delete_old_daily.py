from pathlib import Path
import datetime as dt

start = dt.date(2026, 2, 12)
end   = dt.date(2026, 2, 20)

bases = [Path("data/daily"), Path("docs/data/daily")]

for base in bases:
    if not base.exists():
        print("SKIP", base)
        continue

    d = start
    while d <= end:
        p = base / f"{d.isoformat()}.json"
        if p.exists():
            print("DELETE", p)
            p.unlink()
        d += dt.timedelta(days=1)
        