# app.py
import streamlit as st
import pandas as pd
from kiteconnect import KiteConnect

# -----------------------------
# CONFIG
# -----------------------------
KITE_API_KEY = "j26mm94rwatmzarj"
KITE_ACCESS_TOKEN = "jDEHV55RcYV4X1Za6UwP6aUJqz0tnxLB"

kite = KiteConnect(api_key=KITE_API_KEY)
kite.set_access_token(KITE_ACCESS_TOKEN)

st.set_page_config(page_title="F&O Screener Simplified", layout="wide")
st.title("📈 F&O Screener - Bullish/Bearish Stocks")

st.sidebar.header("Filter Options")
show_rsi = st.sidebar.checkbox("Filter RSI < 30 / > 70")

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_fno_stocks():
    instruments = kite.instruments("NFO")
    fo_stocks = sorted(set([i["tradingsymbol"].split()[0] for i in instruments if i["segment"]=="NFO-FUT"]))
    return fo_stocks

def get_fut_data(stock):
    """Fetch LTP and OI from futures"""
    try:
        ltp_data = kite.ltp(f"NFO:{stock}-FUT")
        price = ltp_data[f"NFO:{stock}-FUT"]["last_price"]
        oi = ltp_data[f"NFO:{stock}-FUT"]["oi"]  # Open Interest
        return price, oi
    except:
        return None, None

def get_option_pcr(stock):
    """Fetch total CE/PE OI for PCR (without strikes)"""
    try:
        ce_pe_symbols = [f"NFO:{stock}-CE", f"NFO:{stock}-PE"]
        ltp_data = kite.ltp(ce_pe_symbols)
        ce_oi = ltp_data.get(ce_pe_symbols[0], {}).get("oi", 0)
        pe_oi = ltp_data.get(ce_pe_symbols[1], {}).get("oi", 0)
        pcr = pe_oi / ce_oi if ce_oi != 0 else 0
        return ce_oi, pe_oi, pcr
    except:
        return 0, 0, 0

# -----------------------------
# Fetch F&O Data
# -----------------------------
fo_stocks = get_fno_stocks()
selected_stocks = st.multiselect("Select F&O Stocks", fo_stocks, default=fo_stocks[:5])

results = []
for stock in selected_stocks:
    price, fut_oi = get_fut_data(stock)
    ce_oi, pe_oi, pcr = get_option_pcr(stock)

    if price is None:
        continue

    # simple SMA/RSI mock using last price (you can replace with proper historical later)
    import pandas as pd
    import numpy as np
    prices = pd.Series(np.random.normal(price, 2, 30))  # placeholder series
    sma20 = prices.rolling(20).mean().iloc[-1]
    sma50 = prices.rolling(50).mean().iloc[-1]
    rsi = compute_rsi(prices).iloc[-1]

    results.append({
        "Stock": stock,
        "Price": price,
        "SMA20": sma20,
        "SMA50": sma50,
        "RSI": rsi,
        "Fut_OI": fut_oi,
        "CE_OI": ce_oi,
        "PE_OI": pe_oi,
        "PCR": pcr
    })

# -----------------------------
# Display Screener
# -----------------------------
if results:
    df = pd.DataFrame(results)

    if show_rsi:
        df = df[(df["RSI"] < 30) | (df["RSI"] > 70)]

    st.subheader("📊 F&O Screener Results")
    st.dataframe(df, use_container_width=True)

    st.subheader("⚡ Most Bullish Stocks")
    bullish = df[(df["SMA20"] > df["SMA50"]) & (df["PCR"] < 1)].sort_values(by="Fut_OI", ascending=False)
    st.table(bullish[["Stoc]()]()
