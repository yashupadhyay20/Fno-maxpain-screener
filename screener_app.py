# FnO Screener Dashboard: Current Price vs Max Pain
# Run with: streamlit run screener_app.py

import streamlit as st
import pandas as pd
from nsepython import *

def calculate_max_pain(symbol, expiry=None):
    try:
        option_chain = nse_optionchain_scrapper(symbol)
        ltp = float(option_chain['records']['underlyingValue'])
        if not expiry:
            expiry = option_chain['records']['expiryDates'][0]

        data = option_chain['records']['data']
        strikes, oi_sum = [], []

        for item in data:
            if item['expiryDate'] == expiry and 'CE' in item and 'PE' in item:
                strike = item['strikePrice']
                ce_oi = item['CE']['openInterest']
                pe_oi = item['PE']['openInterest']
                strikes.append(strike)
                oi_sum.append(ce_oi + pe_oi)

        if not strikes:
            return None

        df = pd.DataFrame({'Strike': strikes, 'Total_OI': oi_sum})
        max_pain = df.loc[df['Total_OI'].idxmin(), 'Strike']
        diff_pct = ((ltp - max_pain) / max_pain) * 100

        return [symbol, round(ltp, 2), max_pain, round(diff_pct, 2)]
    except:
        return None

# --------------------------
# Streamlit UI
# --------------------------

st.set_page_config(page_title="FnO Max Pain Screener", layout="wide")
st.title("📊 FnO Screener: Current Price vs Max Pain")

# Sidebar: Filters
min_dev = st.sidebar.slider("Show only stocks with deviation % greater than:", 
                            min_value=0.0, max_value=10.0, value=2.0, step=0.5)

search_symbol = st.sidebar.text_input("Search by stock symbol (e.g. INFY, RELIANCE):", "").upper()

if st.button("Run Screener"):
    fno_list = fnolist()
    results = []

    with st.spinner("Fetching data..."):
        for sym in fno_list:
            result = calculate_max_pain(sym)
            if result:
                results.append(result)

    df_results = pd.DataFrame(results, columns=["Symbol", "LTP", "Max Pain", "Diff %"])
    
    # Apply deviation filter
    df_filtered = df_results[df_results["Diff %"].abs() >= min_dev]

    # Apply search filter if given
    if search_symbol:
        df_filtered = df_filtered[df_filtered["Symbol"].str.contains(search_symbol, case=False, na=False)]

    # Sort by absolute deviation
    df_sorted = df_filtered.sort_values(by="Diff %", key=abs, ascending=False)

    st.subheader(f"Results (Deviation ≥ {min_dev}%)")
    st.dataframe(df_sorted, use_container_width=True)

    # Option to download
    csv = df_sorted.to_csv(index=False).encode('utf-8')
    st.download_button("Download Filtered CSV", data=csv, file_name="screener_results.csv", mime="text/csv")
