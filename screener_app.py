# screener_app.py

import streamlit as st
import pandas as pd
import numpy as np
from nsepython import *
from datetime import datetime, timedelta

st.set_page_config(page_title="F&O Max Pain Screener", layout="wide")

# ---------------------------------
# Helper Functions
# ---------------------------------

@st.cache_data
def get_fno_list():
    """Fetch all F&O stocks from NSE"""
    fno_df = nse_fno()
    return list(fno_df["SYMBOL"].unique())

@st.cache_data
def get_bhavcopy(date=None):
    """Fetch NSE bhavcopy for equities"""
    if date is None:
        date = datetime.today() - timedelta(days=1)  # yesterday
    try:
        bhav = bhavcopy_equities(date)
        return bhav
    except:
        return pd.DataFrame()

def calculate_max_pain(symbol):
    """Calculate max pain for a given stock"""
    try:
        oc = nse_optionchain_equity(symbol)
        calls = pd.DataFrame(oc["records"]["data"])
        ce_data = pd.json_normalize(calls["CE"].dropna())
        pe_data = pd.json_normalize(calls["PE"].dropna())
        ce_oi = ce_data.groupby("strikePrice")["openInterest"].sum()
        pe_oi = pe_data.groupby("strikePrice")["openInterest"].sum()
        total_oi = ce_oi.add(pe_oi, fill_value=0)
        max_pain_strike = total_oi.idxmax()
        return max_pain_strike
    except:
        return np.nan

def ema_trend(prices, span=20):
    """Return bullish if last price > EMA, else bearish"""
    if len(prices) < span:
        return "Neutral"
    ema = prices.ewm(span=span).mean().iloc[-1]
    last_price = prices.iloc[-1]
    return "Bullish" if last_price > ema else "Bearish"

# ---------------------------------
# Main App
# ---------------------------------

st.title("📊 NSE F&O Max Pain Screener")
st.write("This tool analyses all F&O stocks using max pain, price vs EMA, and volume trends.")

st.info("Fetching F&O list and Bhavcopy data... please wait.")

# Load data
fno_list = get_fno_list()
bhavcopy = get_bhavcopy()

if bhavcopy.empty:
    st.error("❌ Failed to fetch Bhavcopy. Try again later.")
    st.stop()

results = []

progress = st.progress(0)
for i, symbol in enumerate(fno_list):
    try:
        # CMP
        row = bhavcopy[bhavcopy["SYMBOL"] == symbol]
        if row.empty:
            continue
        cmp_price = float(row["CLOSE"].iloc[0])
        volume = int(row["TOTTRDQTY"].iloc[0])

        # Max Pain
        max_pain = calculate_max_pain(symbol)
        if pd.isna(max_pain):
            continue
        deviation = ((cmp_price - max_pain) / max_pain) * 100

        # EMA Trend (use Bhavcopy OHLC data if multiple days available)
        trend = "Neutral"
        try:
            hist = stock_history(symbol=symbol, from_date=(datetime.today() - timedelta(days=90)).strftime("%d-%m-%Y"),
                                 to_date=datetime.today().strftime("%d-%m-%Y"), series="EQ")
            if not hist.empty:
                prices = hist["CLOSE"]
                trend = ema_trend(prices)
        except:
            pass

        results.append({
            "Symbol": symbol,
            "CMP": cmp_price,
            "MaxPain": max_pain,
            "Deviation%": round(deviation, 2),
            "Trend": trend,
            "Volume": volume
        })

    except Exception as e:
        continue
    progress.progress((i + 1) / len(fno_list))

df = pd.DataFrame(results)

# Show full table
st.subheader("📌 All F&O Stocks Data")
st.dataframe(df.sort_values("Symbol"))

# Bullish & Bearish Ranking
st.subheader("🔥 Top 5 Bullish & Bearish Stocks")

# Bullish = CMP > Max Pain & Trend Bullish
bullish = df[(df["Deviation%"] > 0) & (df["Trend"] == "Bullish")]
bullish_top = bullish.sort_values(["Deviation%","Volume"], ascending=[False,False]).head(5)

# Bearish = CMP < Max Pain & Trend Bearish
bearish = df[(df["Deviation%"] < 0) & (df["Trend"] == "Bearish")]
bearish_top = bearish.sort_values(["Deviation%","Volume"], ascending=[True,False]).head(5)

col1, col2 = st.columns(2)

with col1:
    st.markdown("### ✅ Top 5 Bullish")
    st.table(bullish_top)

with col2:
    st.markdown("### ❌ Top 5 Bearish")
    st.table(bearish_top)

st.success("Analysis complete ✅")
