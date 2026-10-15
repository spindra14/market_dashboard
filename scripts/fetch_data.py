#!/usr/bin/env python3
"""시장 데이터를 서버(GitHub Actions)에서 받아 data.json 으로 저장한다.

브라우저에서 Yahoo/CNN 을 직접 호출하면 CORS 때문에 막히지만,
서버에서 호출하면 막히지 않는다. 대시보드(index.html)는 이 data.json 만 읽는다.
표준 라이브러리만 사용하므로 pip install 이 필요 없다.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data.json")

SYMBOLS = [
    "QQQ", "^VIX", "^VXN", "TLT", "HYG", "LQD", "^GSPC", "^IXIC",
    "KRW=X", "CL=F", "BZ=F", "^TNX", "SOXX", "BTC-USD", "GC=F",
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def http_get_json(url, headers=None, timeout=20):
    h = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_yahoo(symbol):
    """일봉 종가 배열(최근 2년, 결측 제거)을 반환. 실패하면 None."""
    sym = urllib.request.quote(symbol, safe="")
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    for attempt in range(4):
        host = hosts[attempt % 2]
        url = f"https://{host}/v8/finance/chart/{sym}?range=2y&interval=1d"
        try:
            data = http_get_json(url)
            result = data["chart"]["result"][0]
            closes = result["indicators"]["quote"][0]["close"]
            closes = [round(c, 4) for c in closes if c is not None]
            if len(closes) >= 30:
                return closes
            raise ValueError("too few data points")
        except Exception as e:  # noqa: BLE001
            print(f"  [{symbol}] attempt {attempt + 1} failed: {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None


def fetch_cnn():
    """CNN Fear & Greed 점수. 실패하면 None."""
    base = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    headers = {
        "Origin": "https://edition.cnn.com",
        "Referer": "https://edition.cnn.com/markets/fear-and-greed",
    }
    for url in (base, f"{base}/{today}"):
        for attempt in range(2):
            try:
                data = http_get_json(url, headers=headers)
                fg = data["fear_and_greed"]
                return {"score": round(float(fg["score"])), "rating": fg.get("rating")}
            except Exception as e:  # noqa: BLE001
                print(f"  [CNN] {url} attempt {attempt + 1} failed: {e}", file=sys.stderr)
                time.sleep(2)
    return None


def load_previous():
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def main():
    prev = load_previous()
    prev_yahoo = prev.get("yahoo", {})

    yahoo = {}
    failed = []
    for s in SYMBOLS:
        print(f"fetching {s} ...")
        closes = fetch_yahoo(s)
        if closes:
            yahoo[s] = closes
        elif s in prev_yahoo:
            # 이번에 실패했으면 이전 값을 유지 (화면이 통째로 비는 것 방지)
            yahoo[s] = prev_yahoo[s]
            failed.append(s)
        else:
            failed.append(s)
        time.sleep(0.5)  # 요청 간격을 둬서 429(Too Many Requests) 방지

    if not yahoo:
        print("ERROR: no market data could be fetched", file=sys.stderr)
        sys.exit(1)

    print("fetching CNN fear & greed ...")
    cnn = fetch_cnn() or prev.get("cnn")

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "failed": failed,
        "cnn": cnn,
        "yahoo": yahoo,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    print(f"done: {len(yahoo)}/{len(SYMBOLS)} symbols, cnn={'ok' if cnn else 'none'}, failed={failed}")


if __name__ == "__main__":
    main()
