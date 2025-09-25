import streamlit as st
import pandas as pd
import time
from alpha_vantage.techindicators import TechIndicators
from nsepython import nse_optionchain_scrapper, fnolist
from datetime import date

# Alpha Vantage setup
ti = TechIndicators(key="ZTUYB9NTAZY2M9PC", output_format="pandas")

st.set_page_config(page_title="FnO Screener: Alpha Vantage EMA + Max Pain", layout="wide")
st.title("📊 FnO Screener: Price vs EMA vs Max Pain (Alpha Vantage)")

# Sidebar filters
min_dev = st.sidebar.slider("Minimum deviation % from Max Pain:", 0.0, 10.0, 2.0, 0.5)
search_symbol = st.sidebar.text_input("Search stock symbol:", "").upper()
use_ema_filter = st.sidebar.checkbox("Filter only stocks with valid EMA data", value=False)
debug_single = st.sidebar.checkbox("Show debug payouts", value=False)

@st.cache_data(ttl=60)
def fetch_option_chain(symbol):
    return nse_optionchain_scrapper(symbol)

def fetch_alpha_emas(symbol):
    try:
        av_symbol = f"{symbol}.NS"
        ema20_df, _ = ti.get_ema(symbol=av_symbol, interval='daily', time_period=20, series_type='close')
        time.sleep(12)  # Respect Alpha Vantage rate limits
        ema50_df, _ = ti.get_ema(symbol=av_symbol, interval='daily', time_period=50, series_type='close')
        time.sleep(12)

        latest_ema20 = round(ema20_df.iloc[-1]['EMA'], 2)
        latest_ema50 = round(ema50_df.iloc[-1]['EMA'], 2)

        return latest_ema20, latest_ema50
    except Exception as e:
        print(f"Alpha Vantage error for {symbol}: {e}")
        return None, None

def calculate_max_pain(symbol):
    try:
        chain = fetch_option_chain(symbol)
        records = chain.get('records', {})
        ltp = float(records.get('underlyingValue', 0.0))
        expiry = records.get('expiryDates', [])[0]
        data = records.get('data', [])
        ce_oi, pe_oi, strikes = {}, {}, []

        for item in data:
            if item.get('expiryDate') != expiry: continue
            k = item.get('strikePrice')
            if k is None: continue
            strikes.append(k)
            ce = int(item.get('CE', {}).get('openInterest', 0))
            pe = int(item.get('PE', {}).get('openInterest', 0))
            ce_oi[k] = ce_oi.get(k, 0) + ce
            pe_oi[k] = pe_oi.get(k, 0) + pe

        payouts = {}
        for P in sorted(set(strikes)):
            total = sum((P - K) * ce_oi.get(K, 0) if P > K else (K - P) * pe_oi.get(K, 0) for K in strikes)
            payouts[P] = total

        max_pain = min(payouts, key=payouts.get)
        diff_pct = ((ltp - max_pain) / max_pain) * 100 if max_pain else 0.0
        ema20, ema50 = fetch_alpha_emas(symbol)

        return {
            "Symbol": symbol,
            "LTP": round(ltp, 2),
            "Max Pain": int(max_pain),
            "Diff %": round(diff_pct, 2),
            "20 EMA": ema20,
            "50 EMA": ema50,
            "CandidatePayouts": payouts
        }
    except Exception as e:
        return {"Symbol": symbol, "Error": str(e)}

# Run Screener
if st.button("Run Screener"):
    fno_list = fnolist()
    results = []
    skipped = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, sym in enumerate(fno_list, start=1):
        status_text.text(f"Processing {sym} ({idx}/{len(fno_list)})...")
        res = calculate_max_pain(sym)
        if res and res.get("Error") is None:
            results.append(res)
            if not res["20 EMA"] or not res["50 EMA"]:
                skipped.append(sym)
        else:
            skipped.append(sym)
        progress_bar.progress(int(100 * idx / len(fno_list)))

    progress_bar.empty()
    status_text.empty()

    if not results:
        st.warning("No valid results found.")
    else:
        df = pd.DataFrame(results)
        df = df[df["Diff %"].notnull()]
        df = df[df["Diff %"].abs() >= min_dev]
        if search_symbol:
            df = df[df["Symbol"].str.contains(search_symbol, case=False)]

        df["20 EMA"] = pd.to_numeric(df["20 EMA"], errors='coerce')
        df["50 EMA"] = pd.to_numeric(df["50 EMA"], errors='coerce')

        df_valid = df.dropna(subset=["LTP", "20 EMA", "50 EMA"]) if use_ema_filter else df.copy()

        df_valid["Bullish"] = (df_valid["LTP"] > df_valid["20 EMA"]) & (df_valid["20 EMA"] > df_valid["50 EMA"])
        df_valid["Bearish"] = (df_valid["LTP"] < df_valid["20 EMA"]) & (df_valid["20 EMA"] < df_valid["50 EMA"])

        top_bullish = df_valid[df_valid["Bullish"]].sort_values("Diff %", ascending=False).head(5)
        top_bearish = df_valid[df_valid["Bearish"]].sort_values("Diff %").head(5)

        st.subheader("📈 Top 5 Bullish Stocks")
        st.dataframe(top_bullish)

        st.subheader("📉 Top 5 Bearish Stocks")
        st.dataframe(top_bearish)

        st.subheader("📋 Full Screener Results")
        st.dataframe(df_valid)

        csv = df_valid.to_csv(index=False).encode('utf-8')
        st.download_button("Download Screener CSV", data=csv, file_name="fno_screener.csv", mime="text/csv")

        if skipped:
            st.info(f"Skipped {len(skipped)} symbols due to missing EMA or errors.")
            st.write(skipped)

        if debug_single and search_symbol:
            debug_res = calculate_max_pain(search_symbol)
            if debug_res and "CandidatePayouts" in debug_res:
                df_dbg = pd.DataFrame(sorted(debug_res["CandidatePayouts"].items(), key=lambda x: x[1])[:10],
                                      columns=["Strike", "Total Payout"])
                st.subheader(f"Debug Payouts for {search_symbol}")
                st.dataframe(df_dbg)
