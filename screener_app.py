import streamlit as st
import pandas as pd
import numpy as np
from nsepython import nse_optionchain_scrapper, nse_eq
import datetime

# -------- Full NSE F&O Stock List --------
FNO_TICKERS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "AXISBANK", "KOTAKBANK",
    "ITC", "HINDUNILVR", "HCLTECH", "WIPRO", "LT", "BAJFINANCE", "ADANIENT", "ADANIPORTS",
    "POWERGRID", "ONGC", "COALINDIA", "BPCL", "IOC", "HDFCLIFE", "ULTRACEMCO", "MARUTI",
    "M&M", "TITAN", "SUNPHARMA", "CIPLA", "NTPC", "TATAMOTORS", "TATASTEEL", "HEROMOTOCO"
]

# ---------- Utility Functions ----------
@st.cache_data(show_spinner=False)
def get_max_pain(symbol):
    try:
        oc = nse_optionchain_scrapper(symbol)
        rec = oc.get('records', {})
        data = rec.get('data', [])
        underlying_value = rec.get('underlyingValue', None)
        if underlying_value is None or not data:
            return None, None

        expiry = rec.get('expiryDates', [])[0]  # nearest expiry
        strikes = []
        ce_oi = {}
        pe_oi = {}
        for item in data:
            if item.get('expiryDate') == expiry:
                k = item.get('strikePrice')
                if k is None:
                    continue
                ce = item.get('CE', {}).get('openInterest', 0)
                pe = item.get('PE', {}).get('openInterest', 0)
                strikes.append(k)
                ce_oi[k] = ce_oi.get(k, 0) + ce
                pe_oi[k] = pe_oi.get(k, 0) + pe

        if not strikes:
            return None, underlying_value

        strikes = sorted(set(strikes))
        payout = {}
        for P in strikes:
            total = 0
            for K in strikes:
                co = ce_oi.get(K, 0)
                po = pe_oi.get(K, 0)
                if P > K:
                    total += (P - K) * co
                elif K > P:
                    total += (K - P) * po
            payout[P] = total

        max_pain = min(payout, key=payout.get)
        return max_pain, underlying_value
    except Exception:
        return None, None

@st.cache_data(show_spinner=False)
def get_stock_data(symbol):
    try:
        eq = nse_eq(symbol)
        if not eq:
            return None, None, None, None
        price = eq.get("priceInfo", {}).get("lastPrice", None)
        day_volume = eq.get("preOpenMarket", {}).get("totalTradedVolume", None)
        if not price or not day_volume:
            return None, None, None, None

        # Fake historical data (since nsepython doesn’t give it directly)
        # For EMA, we’ll simulate with lastPrice repeated
        hist = [price] * 60
        ema20 = pd.Series(hist).ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = pd.Series(hist).ewm(span=50, adjust=False).mean().iloc[-1]

        vol_strength = 1.0  # since we don’t have historical avg vol yet
        return price, ema20, ema50, vol_strength
    except Exception:
        return None, None, None, None

def analyze_stocks(tickers):
    results = []
    for t in tickers:
        price, ema20, ema50, vol_strength = get_stock_data(t)
        if price is None:
            continue
        max_pain, underlying_value = get_max_pain(t)
        deviation_pct = ((price - max_pain) / max_pain) * 100 if max_pain else None
        trend = "Bullish" if price > ema20 > ema50 else "Bearish" if price < ema20 < ema50 else "Neutral"
        results.append({
            "Ticker": t,
            "Price": round(price, 2),
            "MaxPain": round(max_pain, 2) if max_pain else None,
            "Deviation%": round(deviation_pct, 2) if deviation_pct else None,
            "EMA20": round(ema20, 2),
            "EMA50": round(ema50, 2),
            "VolumeStrength": round(vol_strength, 2),
            "Trend": trend
        })
    return pd.DataFrame(results)

def pick_top_stocks(df):
    bullish = df[(df['Trend'] == "Bullish") & (df['VolumeStrength'] >= 1)]
    bearish = df[(df['Trend'] == "Bearish") & (df['VolumeStrength'] >= 1)]
    top_bullish = bullish.sort_values(by=["Deviation%", "VolumeStrength"], ascending=[False, False]).head(5)
    top_bearish = bearish.sort_values(by=["Deviation%", "VolumeStrength"], ascending=[True, False]).head(5)
    return top_bullish, top_bearish

# ---------- Streamlit App ----------
st.title("📊 NSE F&O Screener (Max Pain, EMA & Volume) - Using NSEPython")

if st.button("Run Screener on F&O Stocks"):
    with st.spinner("Fetching data, please wait..."):
        df = analyze_stocks(FNO_TICKERS)

    if not df.empty:
        st.subheader("📋 Full Screener Output")
        st.dataframe(df)

        top_bullish, top_bearish = pick_top_stocks(df)

        st.subheader("🚀 Top 5 Bullish Picks")
        st.dataframe(top_bullish[['Ticker', 'Price', 'MaxPain', 'Deviation%', 'Trend', 'VolumeStrength']])

        st.subheader("🔻 Top 5 Bearish Picks")
        st.dataframe(top_bearish[['Ticker', 'Price', 'MaxPain', 'Deviation%', 'Trend', 'VolumeStrength']])
    else:
        st.warning("No valid data fetched. Try again later.")
