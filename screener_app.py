# fast_fno_screener.py
import streamlit as st
import pandas as pd
from kiteconnect import KiteConnect
import re

# -----------------------------
# CONFIG
# -----------------------------
KITE_API_KEY = "j26mm94rwatmzarj"
KITE_ACCESS_TOKEN = "jDEHV55RcYV4X1Za6UwP6aUJqz0tnxLB"

kite = KiteConnect(api_key=KITE_API_KEY)
kite.set_access_token(KITE_ACCESS_TOKEN)

st.set_page_config(page_title="Fast F&O Screener", layout="wide")
st.title("⚡ Fast F&O Screener - Underlying Stocks Only")

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def extract_underlying(fut_symbol):
    match = re.match(r"[A-Z0-9]+", fut_symbol)
    if match:
        return match.group(0)
    return fut_symbol

def get_underlying_stocks():
    instruments = kite.instruments("NFO")
    underlyings = sorted(set([extract_underlying(inst["tradingsymbol"])
                              for inst in instruments if inst["segment"]=="NFO-FUT"]))
    return underlyings

def get_fut_oi_and_price(stock):
    """Fetch LTP and Futures OI for the first active contract of stock"""
    instruments = kite.instruments("NFO")
    for inst in instruments:
        if inst["segment"] == "NFO-FUT" and inst["tradingsymbol"].startswith(stock):
            try:
                ltp_data = kite.ltp(f"NFO:{inst['tradingsymbol']}")
                data = ltp_data[f"NFO:{inst['tradingsymbol']}"]
                price = data.get("last_price", 0)
                fut_oi = data.get("oi", 0)
                return price, fut_oi
            except:
                return 0, 0
    return 0, 0

def get_option_pcr(stock):
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

# -----------------------------
# FETCH DATA
# -----------------------------
st.info("Fetching F&O data from Kite...")

underlying_stocks = get_underlying_stocks()
results = []

for stock in underlying_stocks:
    price, fut_oi = get_fut_oi_and_price(stock)
    ce_oi, pe_oi, pcr = get_option_pcr(stock)

    results.append({
        "Stock": stock,
        "Price": price,
        "Fut_OI": fut_oi,
        "CE_OI": ce_oi,
        "PE_OI": pe_oi,
        "PCR": round(pcr, 2)
    })

df = pd.DataFrame(results)

# -----------------------------
# DISPLAY TABLES
# -----------------------------
st.subheader("📊 All F&O Underlying Stocks")
st.dataframe(df, use_container_width=True)

# Top 5 Bullish: PCR<1 & high OI
bullish = df[df["PCR"] < 1].sort_values(by="Fut_OI", ascending=False).head(5)
st.subheader("⚡ Top 5 Bullish Stocks")
st.table(bullish[["Stock", "Price", "Fut_OI", "PCR"]])

# Top 5 Bearish: PCR>1 & high OI
bearish = df[df["PCR"] > 1].sort_values(by="Fut_OI", ascending=False).head(5)
st.subheader("⚡ Top 5 Bearish Stocks")
st.table(bearish[["Stock", "Price", "Fut_OI", "PCR"]])
