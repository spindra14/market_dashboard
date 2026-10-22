import yfinance as yf
import pandas as pd
import json
import requests
from datetime import datetime, timezone

# RSI 계산 함수
def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# CNN 공포탐욕지수 크롤링 함수
def fetch_cnn_fg():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return int(r.json()['fear_and_greed']['score'])
    except:
        return 50 # 오류 시 중간값 반환

# 백분위수 계산 함수
def percentile_rank(arr, val):
    if not arr: return 50
    count = sum(1 for x in arr if x <= val)
    return (count / len(arr)) * 100

def main():
    # 수집할 전체 티커
    tickers = [
        "QQQ", "SPY", "SOXX", "^VIX", "^VXN", "TLT", "HYG", "LQD", 
        "^GSPC", "^IXIC", "KRW=X", "CL=F", "BZ=F", "^TNX", 
        "BTC-USD", "GC=F", "^KS11", "^KQ11", "005930.KS", "000660.KS"
    ]
    
    print("Downloading market data...")
    df = yfinance.download(tickers, period="2y", interval="1d")['Close']
    
    market_data = {}
    for t in tickers:
        try:
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

    # 나스닥 자체 공포탐욕지수 계산
    nasdaq_fg = 50
    try:
        q = df["QQQ"].dropna().tolist()
        v = df["^VXN"].dropna().tolist()
        t = df["TLT"].dropna().tolist()
        h = df["HYG"].dropna().tolist()
        l = df["LQD"].dropna().tolist()
        
        # 1. 모멘텀
        sma125 = sum(q[-125:])/125
        m_val = (q[-1] - sma125)/sma125
        m_hist = [(q[i] - sum(q[i-125:i])/125)/(sum(q[i-125:i])/125) for i in range(125, len(q))]
        s_mom = percentile_rank(m_hist, m_val)
        
        # 2. 강도
        q252 = q[-252:]
        s_str = ((q[-1] - min(q252)) / (max(q252) - min(q252))) * 100
        
        # 3. 변동성
        v_sma50 = sum(v[-50:])/50
        v_diff = v[-1] - v_sma50
        v_hist = [v[i] - sum(v[i-50:i])/50 for i in range(50, len(v))]
        s_vol = 100 - percentile_rank(v_hist, v_diff)
        
        # 4. 옵션 (VXN 20일 변화율)
        v_chg = (v[-1] - v[-21])/v[-21]
        v_chg_h = [(v[i]-v[i-20])/v[i-20] for i in range(21, len(v))]
        s_opt = 100 - percentile_rank(v_chg_h, v_chg)
        
        # 5. 안전자산 수요
        safe_val = (q[-1]-q[-21])/q[-21] - (t[-1]-t[-21])/t[-21]
        min_l = min(len(q), len(t))
        safe_h = [(q[i]-q[i-20])/q[i-20] - (t[i]-t[i-20])/t[i-20] for i in range(21, min_l)]
        s_safe = percentile_rank(safe_h, safe_val)
        
        # 6. 정크본드 수요
        junk_val = (h[-1]-h[-21])/h[-21] - (l[-1]-l[-21])/l[-21]
        min_b = min(len(h), len(l))
        junk_h = [(h[i]-h[i-20])/h[i-20] - (l[i]-l[i-20])/l[i-20] for i in range(21, min_b)]
        s_junk = percentile_rank(junk_h, junk_val)
        
        nasdaq_fg = round((s_mom + s_str + s_vol + s_opt + s_safe + s_junk) / 6)
    except Exception as e:
        print(f"Error calculating Nasdaq FG: {e}")

    # 최종 데이터를 JSON으로 저장
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
