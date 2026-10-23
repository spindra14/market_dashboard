import yfinance as yf
import pandas as pd
import json
import requests
import time
import urllib.parse
from datetime import datetime, timezone

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def fetch_cnn_fg():
    base_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Referer': 'https://edition.cnn.com/'
    }
    
    # 캐시를 완벽히 무력화하기 위해 1밀리초 단위 타임스탬프 생성
    timestamp = int(time.time() * 1000)
    target_url = f"{base_url}?_={timestamp}"
    
    # 1. CNN 다이렉트 호출 시도
    try:
        r = requests.get(target_url, headers=headers, timeout=5)
        if r.status_code == 200:
            return int(r.json()['fear_and_greed']['score'])
    except:
        pass
    
    # 2. 강력한 우회 프록시 1 (CodeTabs)
    try:
        proxy_url1 = f"https://api.codetabs.com/v1/proxy?quest={target_url}"
        r = requests.get(proxy_url1, timeout=10)
        if r.status_code == 200:
            return int(r.json()['fear_and_greed']['score'])
    except:
        pass
        
    # 3. 강력한 우회 프록시 2 (AllOrigins) - URL 인코딩 적용
    try:
        encoded_url = urllib.parse.quote(target_url, safe='')
        proxy_url2 = f"https://api.allorigins.win/raw?url={encoded_url}"
        r = requests.get(proxy_url2, timeout=10)
        if r.status_code == 200:
            return int(r.json()['fear_and_greed']['score'])
    except:
        pass
    
    # 세 가지 방법을 모두 실패하면 옛날 데이터를 띄우지 않고 예외 처리 (조회실패)
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
        df = yf.download(yf_tickers, period="2y", interval="1d", session=session)['Close']
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

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cnn_fg": fetch_cnn_fg(),
        "nasdaq_fg": nasdaq_fg,
        "market": market_data
    }
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        
    print("data.json successfully updated.")

if __name__ == "__main__":
    main()
