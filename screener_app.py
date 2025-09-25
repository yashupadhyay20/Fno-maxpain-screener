import streamlit as st
import pandas as pd
import numpy as np
from nsepython import nse_optionchain_scrapper, nse_eq
import requests
import io
import datetime

# -------- Fetch Latest F&O Stock List --------
@st.cache_data(show_spinner=False)
def get_fno_list():
    url = "https://www1.nseindia.com/content/fo/fo_underlyinglist.csv"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return []
    df = pd.read_csv(io.StringIO(r.text))
    return df["SYMBOL"].dropna().unique().tolist()

# -------- Download Bhavcopy --------
@st.cache_data(show_spinner=False)
def get_bhavcopy(date=None):
    if date is None:
        date = datetime.date.today() - datetime.timedelta(days=1)
    date_str = date.strftime("%d%m%Y")
    url = f"https://www1.nseindia.com/content/historical/EQUITIES/{date.year}/{date.strftime('%b').upper()}/cm{date_str}bhav.csv.zip"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return None
    df = pd.read_csv(io.BytesIO(r.content), compression="zip")
    return df

# -------- Max Pain Calculation from Option Chain --------
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

# -------- Stock Analysis Combining Bhavcopy + Option Chain --------
def analyze_stocks(fno_list, bhav_df):
    results = []
    for symbol in fno_list:
        try:
            stock_data = bhav_df[bhav_df["SYMBOL"] == symbol]
            if stock_data.empty:
                continue

            price = stock_data["CLOSE"].iloc[-1]
            volumes = stock_data["TOTTRDQTY"].tail(50)  # last 50 days
            prices = stock_data["CLOSE"].tail(50)

            ema20 = prices.ewm(span=20, adjust=False).mean().iloc[-1]
            ema50 = prices.ewm(span=50, adjust=False).mean().iloc[-1]
            avg_volume = volumes.rolling(20).mean().iloc[-1]
            vol_strength = (volumes.iloc[-1] / avg_volume) if avg_volume > 0 else 0

            max_pain, underlying_value = get_max_pain(symbol)
            deviation_pct = ((price - max_pain) / max_pain) * 100 if max_pain else None

            trend = "Bullish" if price > ema20 > ema50 else "Bearish" if price < ema20 < ema50 else "Neutral"

            results.append({
                "Ticker": symbol,
                "Price": round(price, 2),
                "MaxPain": round(max_pain, 2) if max_pain else None,
                "Deviation%": round(deviation_pct, 2) if deviation_pct else None,
                "EMA20": round(ema20, 2),
                "EMA50": round(ema50, 2),
                "VolumeStrength": round(vol_strength, 2),
                "Trend": trend
            })
        except Exception:
            continue
    return pd.DataFrame(results)

def pick_top_stocks(df):
    bullish = df[(df['Trend'] == "Bullish") & (df['VolumeStrength'] >= 1)]
    bearish = df[(df['Trend'] == "Bearish") & (df['VolumeStrength'] >= 1)]
    top_bullish = bullish.sort_values(by=["Deviation%", "VolumeStrength"], ascending=[False, False]).head(5)
    top_bearish = bearish.sort_values(by=["Deviation%", "VolumeStrength"], ascending=[True, False]).head(5)
    return top_bullish, top_bearish

# -------- Streamlit App --------
st.title("📊 NSE F&O Screener (Max Pain, EMA & Volume) - NSE + Bhavcopy")

if st.button("Run Screener"):
    with st.spinner("Fetching F&O list..."):
        fno_list = get_fno_list()

    with st.spinner("Fetching Bhavcopy..."):
        bhav_df = get_bhavcopy()
        if bhav_df is None:
            st.error("Failed to fetch Bhavcopy data.")
            st.stop()

    with st.spinner("Analyzing stocks..."):
        df = analyze_stocks(fno_list, bhav_df)

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
