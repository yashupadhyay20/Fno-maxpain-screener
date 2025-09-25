# app.py
import streamlit as st
import pandas as pd
from kiteconnect import KiteConnect
import datetime

# -----------------------------------
# CONFIG
# -----------------------------------
KITE_API_KEY = "j26mm94rwatmzarj"
KITE_ACCESS_TOKEN = "jDEHV55RcYV4X1Za6UwP6aUJqz0tnxLB"

kite = KiteConnect(api_key=KITE_API_KEY)
kite.set_access_token(KITE_ACCESS_TOKEN)

st.set_page_config(page_title="F&O Screener with OI", layout="wide")
st.title("📈 F&O Screener with Open Interest & Option Chain Analysis")

st.sidebar.header("Filter Options")
lookback = st.sidebar.slider("Lookback (days for SMA/RSI)", 10, 90, 30)
show_rsi = st.sidebar.checkbox("Filter RSI < 30 / > 70")

# -----------------------------------
# HELPER FUNCTIONS
# -----------------------------------
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_sma_rsi(df):
    df["SMA20"] = df["close"].rolling(20).mean()
    df["SMA50"] = df["close"].rolling(50).mean()
    df["RSI"] = compute_rsi(df["close"], 14)
    return df

def get_fno_stocks():
    """Fetch all F&O stocks from NFO segment"""
    instruments = kite.instruments("NFO")
    fo_stocks = sorted(set([i["tradingsymbol"].split()[0] for i in instruments if i["segment"] == "NFO-FUT"]))
    return fo_stocks

def get_option_chain(stock_symbol):
    """Fetch option chain for a stock and compute PCR"""
    try:
        option_data = kite.ltp(["NFO:" + stock_symbol + "-CE", "NFO:" + stock_symbol + "-PE"])
        ce_oi = option_data.get(f"NFO:{stock_symbol}-CE", {}).get("oi", 0)
        pe_oi = option_data.get(f"NFO:{stock_symbol}-PE", {}).get("oi", 0)
        pcr = pe_oi / ce_oi if ce_oi != 0 else 0
        return ce_oi, pe_oi, pcr
    except Exception as e:
        return 0, 0, 0

# -----------------------------------
# F&O Stocks Selection
# -----------------------------------
fo_stocks = get_fno_stocks()
selected_stocks = st.multiselect("Select F&O Stocks", fo_stocks, default=fo_stocks[:5])

# -----------------------------------
# Fetch Market Data & Option Chain
# -----------------------------------
results = []

for stock in selected_stocks:
    try:
        # Get historical OHLC (past 90 days)
        historical = kite.historical_data(instrument_token=kite.ltp("NSE:" + stock)["NSE:" + stock]["instrument_token"],
                                          from_date=datetime.date.today()-datetime.timedelta(days=lookback*2),
                                          to_date=datetime.date.today(),
                                          interval="day")
        if not historical:
            continue

        df = pd.DataFrame(historical)
        df.rename(columns={"close": "close", "volume": "volume"}, inplace=True)
        df = calculate_sma_rsi(df)

        last = df.iloc[-1]

        # Option Chain OI
        ce_oi, pe_oi, pcr = get_option_chain(stock)

        results.append({
            "Stock": stock,
            "Close": last["close"],
            "SMA20": last["SMA20"],
            "SMA50": last["SMA50"],
            "RSI": last["RSI"],
            "CE_OI": ce_oi,
            "PE_OI": pe_oi,
            "PCR": pcr
        })

    except Exception as e:
        st.warning(f"Data fetch failed for {stock}: {e}")

# -----------------------------------
# Display Screener
# -----------------------------------
if results:
    df_result = pd.DataFrame(results)

    if show_rsi:
        df_result = df_result[(df_result["RSI"] < 30) | (df_result["RSI"] > 70)]

    st.subheader("📊 Screener Results")
    st.dataframe(df_result, use_container_width=True)

    st.subheader("⚡ Trade Signals based on SMA + OI")
    bullish = df_result[(df_result["SMA20"] > df_result["SMA50"]) & (df_result["PCR"] < 1)]
    bearish = df_result[(df_result["SMA20"] < df_result["SMA50"]) & (df_result["PCR"] > 1)]

    st.write("**Bullish Candidates (Golden Cross + PCR < 1):**")
    st.table(bullish[["Stock", "Close", "RSI", "CE_OI", "PE_OI", "PCR"]])

    st.write("**Bearish Candidates (Death Cross + PCR > 1):**")
    st.table(bearish[["Stock", "Close", "RSI", "CE_OI", "PE_OI", "PCR"]])
