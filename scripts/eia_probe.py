"""EIA crude inventory probe (план 39.2/39.3-prep).

Читает EIA_API_KEY из окружения/.env. Нет ключа → честный
СТОП (не выдумываем). Есть ключ → тянет недельный crude stock
change (EIA v2 petroleum/stoc/wstk, серия WCESTUS1 — запасы
коммерческие, ex-SPR) в data/eia/crude_stocks.jsonl для
плана 39.3 (предзаданное событийное правило + строгий гейт).
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

_OUT = Path("data/eia/crude_stocks.jsonl")
_SERIES = "PET.WCESTUS1.W"  # недельные коммерческие запасы нефти (ex-SPR)


def _key() -> str | None:
    k = os.environ.get("EIA_API_KEY")
    if k:
        return k
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("EIA_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return None


def main() -> None:
    key = _key()
    if not key:
        print("EIA_API_KEY не найден (env/.env). СТОП — данных нет.")
        print("Разблокировка: ключ на eia.gov/opendata/register.php →")
        print(".env: EIA_API_KEY=...  (по аналогии с COINGLASS_API_KEY).")
        print("39.3 не запускается без данных — это не «нет edge».")
        return
    params = urllib.parse.urlencode(
        {
            "api_key": key,
            "frequency": "weekly",
            "data[0]": "value",
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "length": 5000,
        }
    )
    url = (
        "https://api.eia.gov/v2/petroleum/stoc/wstk/data/?"
        + params
        + "&facets[series][]="
        + _SERIES
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as fh:
            d = json.load(fh)
    except Exception as e:
        print(f"EIA запрос ошибка: {type(e).__name__} {str(e)[:160]}")
        print("Если 403 — ключ неверен/не активирован. Честный СТОП.")
        return
    rows = (d.get("response") or {}).get("data") or []
    if not rows:
        print(f"EIA вернул 0 строк (проверь серию {_SERIES}). СТОП.")
        return
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with _OUT.open("w") as out:
        for r in rows:
            per = r.get("period")
            val = r.get("value")
            if per is None or val is None:
                continue
            out.write(json.dumps({"period": per, "value": float(val)}) + "\n")
            n += 1
    print(f"EIA crude stocks: {n} недель → {_OUT}")
    print("Готово к 39.3 (предзаданное событийное правило, строгий гейт).")


if __name__ == "__main__":
    main()
