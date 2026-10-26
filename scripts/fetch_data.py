import yfinance as yf
import pandas as pd
import json
import requests
import time
import math
import sys
import urllib.parse
from datetime import datetime, timezone

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://edition.cnn.com',
    'Referer': 'https://edition.cnn.com/markets/fear-and-greed',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}

def cnn_rating_from_score(score):
    # CNN 공식 구간: 0-24 / 25-44 / 45-55 / 56-75 / 76-100
    if score <= 24: return "extreme fear"
    if score <= 44: return "fear"
    if score <= 55: return "neutral"
    if score <= 75: return "greed"
    return "extreme greed"

def parse_cnn(payload):
    fg = payload['fear_and_greed']
    raw = float(fg['score'])
    # CNN 화면은 소수점을 '반올림'해서 보여준다. (기존 int()는 버림이라 1점씩 낮게 나왔음)
    # 파이썬 round()는 .5를 짝수로 보내므로 자바스크립트 Math.round와 같은 방식으로 직접 계산
    score = int(math.floor(raw + 0.5))
    return {
        "score": score,
        "raw": round(raw, 2),
        "rating": (fg.get('rating') or cnn_rating_from_score(score)).lower(),
        "cnn_time": fg.get('timestamp'),
    }

def fetch_cnn_fg():
    """CNN 공포탐욕지수를 가져온다. 실패하면 None (옛날 값을 대신 보여주지 않음)."""
    # 1. CNN 직접 호출 (3회 재시도) - 가장 정확하고 가장 최신
    for attempt in range(3):
        try:
            r = requests.get(f"{CNN_URL}?_={int(time.time() * 1000)}", headers=CNN_HEADERS, timeout=10)
            if r.status_code == 200:
                res = parse_cnn(r.json())
                res["source"] = "cnn"
                return res
            print(f"CNN direct HTTP {r.status_code} (attempt {attempt + 1})")
        except Exception as e:
            print(f"CNN direct error (attempt {attempt + 1}): {e}")
        time.sleep(2 * (attempt + 1))

    # 2. 우회 프록시 (프록시는 캐시된 오래된 값을 줄 수 있어 직접 호출 실패 시에만 사용)
    target_url = f"{CNN_URL}?_={int(time.time() * 1000)}"
    proxies = [
        ("codetabs", f"https://api.codetabs.com/v1/proxy?quest={target_url}"),
        ("allorigins", f"https://api.allorigins.win/raw?url={urllib.parse.quote(target_url, safe='')}"),
    ]
    for name, url in proxies:
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                res = parse_cnn(r.json())
                res["source"] = name
                return res
        except Exception as e:
            print(f"CNN proxy {name} error: {e}")

    return None

def fetch_naver_basic(code, type_str):
    if type_str == "world_index":
        url = f"https://m.stock.naver.com/api/index/world/{code}/basic"
    else:
        url = f"https://m.stock.naver.com/api/{type_str}/{code}/basic"
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        data = r.json()
        price = float(data['closePrice'].replace(',', ''))
        chg = float(data['compareToPreviousClosePrice'].replace(',', ''))
        pct = float(data['fluctuationsRatio'].replace(',', ''))

        if pct < 0 and chg > 0: chg = -chg
        elif pct > 0 and chg < 0: chg = abs(chg)
        elif pct == 0: chg = 0.0

        return {"price": price, "chg": chg, "chg_pct": pct}
    except:
        return None

def fetch_naver_marketindex(category, reuters_code):
    url = f"https://m.stock.naver.com/front-api/v1/marketIndex/prices?category={category}&reutersCode={reuters_code}"
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        data = r.json().get('result', [])
        if data:
            latest = data[0]
            price = float(latest['closePrice'].replace(',', ''))
            chg = float(latest['compareToPreviousClosePrice'].replace(',', ''))
            pct = float(latest['fluctuationsRatio'].replace(',', ''))

            if pct < 0 and chg > 0: chg = -chg
            elif pct > 0 and chg < 0: chg = abs(chg)
            elif pct == 0: chg = 0.0

            return {"price": price, "chg": chg, "chg_pct": pct}
    except:
        return None

def percentile_rank(arr, val):
    if not arr: return 50
    count = sum(1 for x in arr if x <= val)
    return (count / len(arr)) * 100

def main():
    yf_tickers = [
        "QQQ", "SPY", "SOXX", "^SOX", "^VIX", "^VXN", "TLT", "HYG", "LQD", 
        "^GSPC", "^IXIC", "KRW=X", "CL=F", "BZ=F", "^TNX", 
        "BTC-USD", "GC=F", "^KS11", "^KQ11", "005930.KS", "000660.KS"
    ]
    
    print("Downloading Yahoo Finance base data...")
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    market_data = {}
    
    try:
        df = yf.download(yf_tickers, period="2y", interval="1d", progress=False)['Close']
        for t in yf_tickers:
            try:
                if t not in df.columns:
                    continue
                s = df[t].dropna()
                if len(s) >= 2:
                    curr = float(s.iloc[-1])
                    prev = float(s.iloc[-2])
                    chg = curr - prev
                    pct = (chg / prev) * 100
                    
                    rsi = None
                    if len(s) >= 15:
                        rsi_series = calc_rsi(s)
                        rsi = float(rsi_series.iloc[-1])
                    
                    market_data[t] = {
                        "price": curr,
                        "chg": chg,
                        "chg_pct": pct,
                        "rsi": round(rsi, 1) if pd.notnull(rsi) else None
                    }
            except Exception as e:
                pass
    except Exception as e:
        print(f"Yahoo Data download failed: {e}")

    # 한꺼번에 받을 때 빠진 종목(예: ^TNX)은 하나씩 다시 시도
    for t in yf_tickers:
        if t in market_data:
            continue
        try:
            s1 = yf.Ticker(t).history(period="2y", interval="1d")['Close'].dropna()
            if len(s1) >= 2:
                curr, prev = float(s1.iloc[-1]), float(s1.iloc[-2])
                rsi1 = float(calc_rsi(s1).iloc[-1]) if len(s1) >= 15 else None
                market_data[t] = {"price": curr, "chg": curr - prev, "chg_pct": (curr - prev) / prev * 100,
                                  "rsi": round(rsi1, 1) if rsi1 is not None and pd.notnull(rsi1) else None}
                print(f"Recovered {t} by single download")
        except Exception as e:
            print(f"Single download failed for {t}: {e}")

    print("Overwriting with Naver real-time data...")
    naver_mapping = {
        "^KS11": lambda: fetch_naver_basic("KOSPI", "index"),
        "^KQ11": lambda: fetch_naver_basic("KOSDAQ", "index"),
        "005930.KS": lambda: fetch_naver_basic("005930", "stock"),
        "000660.KS": lambda: fetch_naver_basic("000660", "stock"),
        "^GSPC": lambda: fetch_naver_basic("SPI@SPX", "world_index"),
        "^IXIC": lambda: fetch_naver_basic("NII@IXIC", "world_index"),
        "^VIX": lambda: fetch_naver_basic("CBI@VIX", "world_index"),
        "^SOX": lambda: fetch_naver_basic("NII@SOX", "world_index"),
        "KRW=X": lambda: fetch_naver_marketindex("exchange", "FX_USDKRW"),
        "CL=F": lambda: fetch_naver_marketindex("oil", "OIL_CL"),
        "BZ=F": lambda: fetch_naver_marketindex("oil", "OIL_BRT"),
        "GC=F": lambda: fetch_naver_marketindex("metal", "CMDT_GC")
    }
    
    for yf_ticker, fetch_func in naver_mapping.items():
        try:
            naver_data = fetch_func()
            if naver_data:
                if yf_ticker in market_data:
                    market_data[yf_ticker]["price"] = naver_data["price"]
                    market_data[yf_ticker]["chg"] = naver_data["chg"]
                    market_data[yf_ticker]["chg_pct"] = naver_data["chg_pct"]
                else:
                    market_data[yf_ticker] = {
                        "price": naver_data["price"],
                        "chg": naver_data["chg"],
                        "chg_pct": naver_data["chg_pct"],
                        "rsi": None
                    }
        except Exception as e:
            print(f"Error fetching Naver data for {yf_ticker}: {e}")

    nasdaq_fg = None
    try:
        if 'df' in locals() and all(x in df.columns for x in ["QQQ", "^VXN", "TLT", "HYG", "LQD"]):
            q = df["QQQ"].dropna().tolist()
            v = df["^VXN"].dropna().tolist()
            t = df["TLT"].dropna().tolist()
            h = df["HYG"].dropna().tolist()
            l = df["LQD"].dropna().tolist()
            
            if len(q) >= 252 and len(v) >= 50:
                sma125 = sum(q[-125:])/125
                m_val = (q[-1] - sma125)/sma125
                s_mom = percentile_rank([(q[i] - sum(q[i-125:i])/125)/(sum(q[i-125:i])/125) for i in range(125, len(q))], m_val)
                
                q252 = q[-252:]
                s_str = ((q[-1] - min(q252)) / (max(q252) - min(q252))) * 100
                
                v_sma50 = sum(v[-50:])/50
                v_diff = v[-1] - v_sma50
                s_vol = 100 - percentile_rank([v[i] - sum(v[i-50:i])/50 for i in range(50, len(v))], v_diff)
                
                v_chg = (v[-1] - v[-21])/v[-21]
                s_opt = 100 - percentile_rank([(v[i]-v[i-20])/v[i-20] for i in range(21, len(v))], v_chg)
                
                safe_val = (q[-1]-q[-21])/q[-21] - (t[-1]-t[-21])/t[-21]
                min_l = min(len(q), len(t))
                s_safe = percentile_rank([(q[i]-q[i-20])/q[i-20] - (t[i]-t[i-20])/t[i-20] for i in range(21, min_l)], safe_val)
                
                junk_val = (h[-1]-h[-21])/h[-21] - (l[-1]-l[-21])/l[-21]
                min_b = min(len(h), len(l))
                s_junk = percentile_rank([(h[i]-h[i-20])/h[i-20] - (l[i]-l[i-20])/l[i-20] for i in range(21, min_b)], junk_val)
                
                nasdaq_fg = round((s_mom + s_str + s_vol + s_opt + s_safe + s_junk) / 6)
    except Exception as e:
        print(f"Error calculating Nasdaq FG: {e}")

    if not market_data:
        print("No market data collected - keeping previous data.json")
        sys.exit(1)

    cnn = fetch_cnn_fg()
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cnn_fg": cnn["score"] if cnn else None,
        "cnn_fg_raw": cnn["raw"] if cnn else None,
        "cnn_fg_rating": cnn["rating"] if cnn else None,
        "cnn_fg_time": cnn["cnn_time"] if cnn else None,
        "cnn_fg_source": cnn["source"] if cnn else None,
        "nasdaq_fg": nasdaq_fg,
        "market": market_data
    }
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        
    print("data.json successfully updated.")

if __name__ == "__main__":
    main()
