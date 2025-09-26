# screener_app.py
import streamlit as st
import pandas as pd
import re
from kiteconnect import KiteConnect

# -----------------------------
# ZERODHA CREDENTIALS
# -----------------------------
API_KEY = "j26mm94rwatmzarj"
ACCESS_TOKEN = "DjipZGLO8lOOLPrNy9MBw6S65MGaMVQI"

# -----------------------------
# KITE SESSION
# -----------------------------
kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

# -----------------------------
# STREAMLIT PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="F&O Screener", layout="wide")
st.title("📈 F&O Screener - Underlying Stocks")

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def extract_underlying(symbol):
    """Remove expiry part from F&O symbol"""
    match = re.match(r"[A-Z0-9]+", symbol)
    return match.group(0) if match else symbol

@st.cache_data(show_spinner=False)
def get_underlying_stocks():
    """Fetch unique underlying stocks from NFO Futures"""
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
                price = data.get("last_price", 0)
                fut_oi = data.get("oi", 0)
                return price, fut_oi
            except Exception as e:
                return 0, 0
    return 0, 0

# -----------------------------
# MAIN
# -----------------------------
st.info("Fetching F&O data from Kite...")

underlying_stocks = get_underlying_stocks()
results = []

for stock in underlying_stocks[:50]:   # limit to first 50 for speed
    price, fut_oi = get_fut_price_oi(stock)
    results.append({
        "Stock": stock,
        "Price": price,
        "Fut_OI": fut_oi
    })

df = pd.DataFrame(results)
df = df[df["Price"] > 0]   # filter blanks

if df.empty:
    st.error("⚠️ No data fetched. Check if your API plan includes OI (Market Data).")
else:
    # -----------------------------
    # DISPLAY TABLES
    # -----------------------------
    st.subheader("📊 All F&O Underlying Stocks")
    st.dataframe(df, use_container_width=True)

    bullish = df.sort_values(by="Fut_OI", ascending=False).head(5)
    st.subheader("🚀 Top 5 Bullish Stocks (Highest OI)")
    st.table(bullish[["Stock", "Price", "Fut_OI"]])

    bearish = df.sort_values(by="Fut_OI", ascending=True).head(5)
    st.subheader("🐻 Top 5 Bearish Stocks (Lowest OI)")
    st.table(bearish[["Stock", "Price", "Fut_OI"]])
