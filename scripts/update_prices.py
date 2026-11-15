"""개미노트 시세 업데이트 (GitHub Actions에서 실행)

stocks.js 의 한국·미국 종목 200개에 대해 최근 5년 일봉(시가·고가·저가·종가)을 받아
  data/history/<종목>.json   차트용  {"id":..., "currency":..., "d":[[날짜,시,고,저,종], ...]}
  data/stocks/popular.json   목록용  최신 가격·등락·52주 최고/최저
을 만든다. 데이터 출처: Yahoo Finance (yfinance 라이브러리).
"""
import json, math, re, sys, datetime as dt
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HIST = DATA / "history"
HIST.mkdir(parents=True, exist_ok=True)

src = (ROOT / "stocks.js").read_text(encoding="utf-8")
base = json.loads(re.search(r"window\.STOCK_BASE\s*=\s*(\{.*\});?\s*$", src, re.S).group(1))


def yahoo_candidates(item, mkt):
    sid = item["id"]
    if mkt == "kr":
        return [sid + ".KS", sid + ".KQ"] if re.fullmatch(r"\d{6}", sid) else []
    return [sid.replace(".", "-")]


def clean(v, krw):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return int(round(v)) if krw else round(float(v), 2)


def fetch(symbol):
    df = yf.Ticker(symbol).history(period="5y", interval="1d", auto_adjust=True)
    if df is None or df.empty:
        return None
    return df


out = {"kr": [], "us": []}
missing = []
for mkt in ("kr", "us"):
    for item in base[mkt]:
        krw = mkt == "kr"
        df = None
        for sym in yahoo_candidates(item, mkt):
            try:
                df = fetch(sym)
            except Exception as e:  # 네트워크 오류 등
                print("오류", sym, e, file=sys.stderr)
                df = None
            if df is not None:
                break
        if df is None:
            missing.append(item["id"])
            continue
        rows = []
        for idx, r in df.iterrows():
            o, h, l, c = (clean(r[k], krw) for k in ("Open", "High", "Low", "Close"))
            if c is None:
                continue
            o = o if o is not None else c
            h = h if h is not None else max(o, c)
            l = l if l is not None else min(o, c)
            rows.append([idx.strftime("%Y-%m-%d"), o, h, l, c])
        if len(rows) < 2:
            missing.append(item["id"])
            continue
        (HIST / f"{item['id']}.json").write_text(
            json.dumps({"id": item["id"], "currency": "KRW" if krw else "USD", "d": rows}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        last, prev = rows[-1], rows[-2]
        year = rows[-252:]
        change = (last[4] - prev[4]) if krw else round(last[4] - prev[4], 2)
        out[mkt].append({
            "id": item["id"],
            "price": last[4],
            "change": change,
            "pct": round((last[4] - prev[4]) / prev[4] * 100, 2) if prev[4] else None,
            "w52Low": min(r[3] for r in year),
            "w52High": max(r[2] for r in year),
            "asOf": last[0],
        })

dates = [x["asOf"] for m in ("kr", "us") for x in out[m]]
latest = max(dates) if dates else dt.date.today().isoformat()
d = dt.date.fromisoformat(latest)
label = f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]}) 종가"
popular = {
    "asOfLabel": label,
    "note": "Yahoo Finance 일봉 기준으로 장 마감 뒤 자동으로 바뀌어요.",
    "kr": out["kr"], "us": out["us"],
    "sources": [{"title": "Yahoo Finance (yfinance) · 일봉 시세", "url": "https://finance.yahoo.com/"}],
    "updatedAt": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
}
(DATA / "stocks").mkdir(parents=True, exist_ok=True)
(DATA / "stocks" / "popular.json").write_text(json.dumps(popular, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료: 한국 {len(out['kr'])}개, 미국 {len(out['us'])}개, 못 찾음 {len(missing)}개 {missing}")
