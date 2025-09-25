# fno_screener.py
import streamlit as st
import pandas as pd
from kiteconnect import KiteConnect
from alpha_vantage.timeseries import TimeSeries
import re

# -----------------------------
# CONFIG
# -----------------------------
KITE_API_KEY = "j26mm94rwatmzarj"
KITE_ACCESS_TOKEN = "jDEHV55RcYV4X1Za6UwP6aUJqz0tnxLB"
ALPHA_VANTAGE_KEY = "ZTUYB9NTAZY2M9PC"

kite = KiteConnect(api_key=KITE_API_KEY)
kite.set_access_token(KITE_ACCESS_TOKEN)

ts = TimeSeries(key=ALPHA_VANTAGE_KEY, output_format="pandas")

st.set_page_config(page_title="F&O Screener", layout="wide")
st.title("📈 F&O Screener - All Underlying Stocks")

LOOKBACK = 30  # days for SMA/RSI
RSI_FILTER = True  # Filter RSI <30 or >70

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_sma_rsi(df):
    df["SMA20"] = df["4. close"].rolling(20).mean()
    df["SMA50"] = df["4. close"].rolling(50).mean()
    df["RSI"] = compute_rsi(df["4. close"], 14)
    return df

def extract_underlying(fut_symbol):
    """Extract underlying stock from F&O contract name"""
    match = re.match(r"[A-Z0-9]+", fut_symbol)
    if match:
        return match.group(0)
    return fut_symbol

def get_underlying_stocks():
    """Get unique underlying stock symbols for F&O"""
    instruments = kite.instruments("NFO")
    underlyings = sorted(set([extract_underlying(inst["tradingsymbol"])
                              for inst in instruments if inst["segment"]=="NFO-FUT"]))
    return underlyings

def get_fut_oi(stock):
    """Fetch futures OI for any active contract of the underlying stock"""
    instruments = kite.instruments("NFO")
    for inst in instruments:
        if inst["segment"]=="NFO-FUT" and inst["tradingsymbol"].startswith(stock):
            try:
                ltp_data = kite.ltp(f"NFO:{inst['tradingsymbol']}")
                return ltp_data[f"NFO:{inst['tradingsymbol']}"].get("oi", 0)
            except:
                return 0
    return 0

def get_option_pcr(stock):
    """Fetch CE/PE OI for PCR calculation"""
    try:
        ce_symbol = f"NFO:{stock}-CE"
        pe_symbol = f"NFO:{stock}-PE"
        ltp_data = kite.ltp([ce_symbol, pe_symbol])
        ce_oi = ltp_data.get(ce_symbol, {}).get("oi", 0)
        pe_oi = ltp_data.get(pe_symbol, {}).get("oi", 0)
        pcr = pe_oi / ce_oi if ce_oi != 0 else 0
        return ce_oi, pe_oi, pcr
    except:
        return 0, 0, 0

def get_alpha_data(stock):
    """Fetch OHLC from Alpha Vantage for underlying stock"""
    try:
        data, _ = ts.get_daily(symbol=f"{stock}.BSE", outputsize="compact")
        df = data.tail(LOOKBACK).copy()
        df = calculate_sma_rsi(df)
        last = df.iloc[-1]
        return last["4. close"], last["SMA20"], last["SMA50"], last["RSI"]
    except:
        return None, None, None, None

# -----------------------------
# FETCH DATA FOR ALL F&O STOCKS
# -----------------------------
st.info("Fetching data for all F&O underlying stocks... This may take a few minutes.")
underlying_stocks = get_underlying_stocks()
results = []

for stock in underlying_stocks:
    close, sma20, sma50, rsi = get_alpha_data(stock)
    fut_oi = get_fut_oi(stock)
    ce_oi, pe_oi, pcr = get_option_pcr(stock)

    if None in [close, sma20, sma50, rsi]:
        continue

    results.append({
        "Stock": stock,
        "Price": close,
        "SMA20": sma20,
        "SMA50": sma50,
        "RSI": rsi,
        "Fut_OI": fut_oi,
        "CE_OI": ce_oi,
        "PE_OI": pe_oi,
        "PCR": pcr
    })

df = pd.DataFrame(results)

if RSI_FILTER:
    df = df[(df["RSI"] < 30) | (df["RSI"] > 70)]

# -----------------------------
# DISPLAY TABLES
# -----------------------------
st.subheader("📊 All F&O Underlying Stocks Data")
st.dataframe(df, use_container_width=True)

# Top 5 Bullish: SMA20>SMA50 & PCR<1
bullish = df[(df["SMA20"] > df["SMA50"]) & (df["PCR"] < 1)].sort_values(by="Fut_OI", ascending=False).head(5)
st.subheader("⚡ Top 5 Bullish Stocks")
st.table(bullish[["Stock", "Price", "RSI", "Fut_OI", "PCR"]])

# Top 5 Bearish: SMA20<SMA50 & PCR>1
bearish = df[(df["SMA20"] < df["SMA50"]) & (df["PCR"] > 1)].sort_values(by="Fut_OI", ascending=False).head(5)
st.subheader("⚡ Top 5 Bearish Stocks")
st.table(bearish[["Stock", "Price", "RSI", "Fut_OI", "PCR"]])
