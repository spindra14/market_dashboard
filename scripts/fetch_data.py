import yfinance as yf
import pandas as pd
import json
import requests
from datetime import datetime, timezone

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def fetch_cnn_fg():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://edition.cnn.com/'
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return int(r.json()['fear_and_greed']['score'])
    except:
        pass
    
    try:
        proxy_url = "https://api.allorigins.win/raw?url=" + url
        r = requests.get(proxy_url, timeout=10)
        if r.status_code == 200:
            return int(r.json()['fear_and_greed']['score'])
    except:
        pass
    
    return None # 실패 시 임의의 값(50)을 넣지 않고 데이터 없음을 명시

def percentile_rank(arr, val):
    if not arr: return 50
    count = sum(1 for x in arr if x <= val)
    return (count / len(arr)) * 100

def main():
    tickers = [
        "QQQ", "SPY", "SOXX", "^VIX", "^VXN", "TLT", "HYG", "LQD", 
        "^GSPC", "^IXIC", "KRW=X", "CL=F", "BZ=F", "^TNX", 
        "BTC-USD", "GC=F", "^KS11", "^KQ11", "005930.KS", "000660.KS"
    ]
    
    print("Downloading market data...")
    df = yf.download(tickers, period="2y", interval="1d")['Close']
    
    market_data = {}
    for t in tickers:
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
            print(f"Error processing {t}: {e}")

    nasdaq_fg = None # 기본값을 None으로 설정하여 실패 시 조회불가 처리
    try:
        q = df["QQQ"].dropna().tolist()
        v = df["^VXN"].dropna().tolist()
        t = df["TLT"].dropna().tolist()
        h = df["HYG"].dropna().tolist()
        l = df["LQD"].dropna().tolist()
        
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

if __name__ == "__main__":
    main()
