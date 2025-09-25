import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# -------- Full NSE F&O Stock List (as of 2025) --------
FNO_TICKERS = [
    "ABB.NS","ACC.NS","ADANIENT.NS","ADANIPORTS.NS","AMBUJACEM.NS","APOLLOHOSP.NS","APOLLOTYRE.NS",
    "ASHOKLEY.NS","ASIANPAINT.NS","AUROPHARMA.NS","AXISBANK.NS","BAJAJ-AUTO.NS","BAJAJFINSV.NS",
    "BAJFINANCE.NS","BALKRISIND.NS","BALRAMCHIN.NS","BANDHANBNK.NS","BANKBARODA.NS","BEL.NS","BERGEPAINT.NS",
    "BHARATFORG.NS","BHARTIARTL.NS","BHEL.NS","BIOCON.NS","BOSCHLTD.NS","BPCL.NS","BRITANNIA.NS","BSOFT.NS",
    "CANBK.NS","CANFINHOME.NS","CHAMBLFERT.NS","CHOLAFIN.NS","CIPLA.NS","COALINDIA.NS","COFORGE.NS",
    "COLPAL.NS","CONCOR.NS","CUMMINSIND.NS","DABUR.NS","DALBHARAT.NS","DEEPAKNTR.NS","DIVISLAB.NS",
    "DIXON.NS","DLF.NS","DRREDDY.NS","EICHERMOT.NS","ESCORTS.NS","FEDERALBNK.NS","GAIL.NS","GLENMARK.NS",
    "GMRINFRA.NS","GNFC.NS","GODREJCP.NS","GRANULES.NS","GRASIM.NS","GSPL.NS","GUJGASLTD.NS",
    "HAL.NS","HAVELLS.NS","HCLTECH.NS","HDFCAMC.NS","HDFCBANK.NS","HDFCLIFE.NS","HEROMOTOCO.NS","HINDALCO.NS",
    "HINDCOPPER.NS","HINDPETRO.NS","HINDUNILVR.NS","ICICIBANK.NS","ICICIGI.NS","ICICIPRULI.NS","IDEA.NS",
    "IDFC.NS","IDFCFIRSTB.NS","IEX.NS","IGL.NS","INDHOTEL.NS","INDIACEM.NS","INDIAMART.NS","INDIGO.NS",
    "INDUSINDBK.NS","INDUSTOWER.NS","INFY.NS","IOC.NS","IPCALAB.NS","IRB.NS","ITC.NS","JINDALSTEL.NS",
    "JKCEMENT.NS","JSWSTEEL.NS","JUBLFOOD.NS","KOTAKBANK.NS","L&TFH.NS","LALPATHLAB.NS","LAURUSLABS.NS",
    "LICHSGFIN.NS","LT.NS","LTIM.NS","LTTS.NS","LUPIN.NS","M&M.NS","M&MFIN.NS","MANAPPURAM.NS","MARICO.NS",
    "MARUTI.NS","MCDOWELL-N.NS","MCX.NS","METROPOLIS.NS","MFSL.NS","MGL.NS","MOTHERSON.NS","MPHASIS.NS",
    "MRF.NS","MUTHOOTFIN.NS","NAM-INDIA.NS","NATIONALUM.NS","NAUKRI.NS","NAVINFLUOR.NS","NESTLEIND.NS",
    "NMDC.NS","NTPC.NS","OBEROIRLTY.NS","OFSS.NS","ONGC.NS","PAGEIND.NS","PEL.NS","PERSISTENT.NS","PETRONET.NS",
    "PFC.NS","PIDILITIND.NS","PIIND.NS","PNB.NS","POLYCAB.NS","POWERGRID.NS","PVRINOX.NS","RAMCOCEM.NS",
    "RBLBANK.NS","RECLTD.NS","RELIANCE.NS","SAIL.NS","SBICARD.NS","SBILIFE.NS","SBIN.NS","SHREECEM.NS",
    "SIEMENS.NS","SRF.NS","SUNPHARMA.NS","SUNTV.NS","SUZLON.NS","SYRMA.NS","TATACHEM.NS","TATACOMM.NS",
    "TATACONSUM.NS","TATAMOTORS.NS","TATAPOWER.NS","TATASTEEL.NS","TCS.NS","TECHM.NS","TIINDIA.NS",
    "TORNTPHARM.NS","TORNTPOWER.NS","TRENT.NS","TVSMOTOR.NS","UBL.NS","ULTRACEMCO.NS","UNIONBANK.NS",
    "UPL.NS","VEDL.NS","VOLTAS.NS","WIPRO.NS","ZEEL.NS","ZYDUSLIFE.NS"
]

# ---------- Utility Functions ----------
def get_max_pain(ticker):
    try:
        opt = yf.Ticker(ticker)
        expiries = opt.options
        if not expiries:
            return None, None
        expiry = expiries[0]
        chain = opt.option_chain(expiry)
        calls = chain.calls[['strike', 'openInterest']].rename(columns={'openInterest': 'callOI'})
        puts = chain.puts[['strike', 'openInterest']].rename(columns={'openInterest': 'putOI'})
        df = pd.merge(calls, puts, on="strike", how="outer").fillna(0)
        df['callPain'] = df['callOI'] * abs(df['strike'] - df['strike'].mean())
        df['putPain'] = df['putOI'] * abs(df['strike'] - df['strike'].mean())
        df['totalPain'] = df['callPain'] + df['putPain']
        max_pain_strike = df.loc[df['totalPain'].idxmin(), 'strike']
        return max_pain_strike, expiry
    except Exception:
        return None, None

def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="3mo")
    if hist.empty:
        return None, None, None, None
    close = hist['Close']
    volume = hist['Volume']
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
    avg_volume = volume.rolling(20).mean().iloc[-1]
    current_volume = volume.iloc[-1]
    vol_strength = current_volume / avg_volume if avg_volume > 0 else 0
    return close.iloc[-1], ema20, ema50, vol_strength

def analyze_stocks(tickers):
    results = []
    for t in tickers:
        price, ema20, ema50, vol_strength = get_stock_data(t)
        if price is None:
            continue
        max_pain, expiry = get_max_pain(t)
        if max_pain is None:
            continue
        deviation_pct = ((price - max_pain) / max_pain) * 100
        trend = "Bullish" if price > ema20 > ema50 else "Bearish" if price < ema20 < ema50 else "Neutral"
        results.append({
            "Ticker": t,
            "Price": round(price, 2),
            "MaxPain": round(max_pain, 2),
            "Deviation%": round(deviation_pct, 2),
            "EMA20": round(ema20, 2),
            "EMA50": round(ema50, 2),
            "VolumeStrength": round(vol_strength, 2),
            "Trend": trend
        })
    return pd.DataFrame(results)

def pick_top_stocks(df):
    bullish = df[(df['Trend'] == "Bullish") & (df['VolumeStrength'] > 1)]
    bearish = df[(df['Trend'] == "Bearish") & (df['VolumeStrength'] > 1)]
    top_bullish = bullish.sort_values(by=["Deviation%", "VolumeStrength"], ascending=[False, False]).head(5)
    top_bearish = bearish.sort_values(by=["Deviation%", "VolumeStrength"], ascending=[True, False]).head(5)
    return top_bullish, top_bearish

# ---------- Streamlit App ----------
st.title("📊 NSE F&O Screener (Max Pain, EMA & Volume)")

if st.button("Run Screener on All F&O Stocks"):
    with st.spinner("Fetching data, please wait..."):
        df = analyze_stocks(FNO_TICKERS)

    if not df.empty:
        st.subheader("📋 Full Screener Output (All F&O Stocks)")
        st.dataframe(df)

        top_bullish, top_bearish = pick_top_stocks(df)

        st.subheader("🚀 Top 5 Bullish Picks")
        st.dataframe(top_bullish[['Ticker', 'Price', 'MaxPain', 'Deviation%', 'Trend', 'VolumeStrength']])

        st.subheader("🔻 Top 5 Bearish Picks")
        st.dataframe(top_bearish[['Ticker', 'Price', 'MaxPain', 'Deviation%', 'Trend', 'VolumeStrength']])
    else:
        st.warning("No valid data fetched.")
