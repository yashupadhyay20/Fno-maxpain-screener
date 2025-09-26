# fast_fno_screener_fixed.py
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
    return match.group(0) if match else fut_symbol

@st.cache_data(show_spinner=False)
def get_underlying_stocks():
    instruments = kite.instruments("NFO")
    underlyings = sorted(set([
        extract_underlying(inst["tradingsymbol"])
        for inst in instruments if inst["segment"] == "NFO-FUT"
    ]))
    return underlyings

def get_fut_price_oi(stock):
    """Fetch price & OI of nearest future contract"""
    instruments = kite.instruments("NFO")
    for inst in instruments:
        if inst["segment"] == "NFO-FUT" and inst["tradingsymbol"].startswith(stock):
            try:
                q = kite.quote(f"NFO:{inst['tradingsymbol']}")
                data = q[f"NFO:{inst['tradingsymbol']}"]
                return data["last_price"], data.get("oi", 0)
            except:
                return 0, 0
    return 0, 0

def get_option_pcr(stock):
    """Fetch CE & PE OI of nearest expiry ATM strikes"""
    try:
        ce_symbol = f"NFO:{stock}25OCTCE"  # ⚠️ hardcoding expiry-strike will fail, needs proper option chain logic
        pe_symbol = f"NFO:{stock}25OCTPE"
        q = kite.quote([ce_symbol, pe_symbol])
        ce_oi = q.get(ce_symbol, {}).get("oi", 0)
        pe_oi = q.get(pe_symbol, {}).get("oi", 0)
        pcr = pe_oi / ce_oi if ce_oi else 0
        return ce_oi, pe_oi, pcr
    except:
        return 0, 0, 0

# -----------------------------
# MAIN
# -----------------------------
st.info("Fetching F&O data from Kite...")

underlying_stocks = get_underlying_stocks()
results = []

for stock in underlying_stocks[:50]:   # limit to 50 for speed
    price, fut_oi = get_fut_price_oi(stock)
    ce_oi, pe_oi, pcr = 0, 0, 0  # Option chain part can be expanded later
    results.append({
        "Stock": stock,
        "Price": price,
        "Fut_OI": fut_oi,
        "PCR": round(pcr, 2)
    })

df = pd.DataFrame(results)
df = df[df["Price"] > 0]   # filter out blanks

if df.empty:
    st.error("No data fetched. Check if your Kite API has access to OI/Quote API.")
else:
    # -----------------------------
    # DISPLAY TABLES
    # -----------------------------
    st.subheader("📊 All F&O Underlying Stocks")
    st.dataframe(df, use_container_width=True)

    bullish = df.sort_values(by="Fut_OI", ascending=False).head(5)
    st.subheader("⚡ Top 5 Bullish Stocks (Highest OI)")
    st.table(bullish[["Stock", "Price", "Fut_OI"]])

    bearish = df.sort_values(by="Fut_OI", ascending=True).head(5)
    st.subheader("⚡ Top 5 Bearish Stocks (Lowest OI)")
    st.table(bearish[["Stock", "Price", "Fut_OI"]])
