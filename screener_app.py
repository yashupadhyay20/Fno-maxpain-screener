# FnO Screener Dashboard: Current Price vs Max Pain (corrected)
# Run with: streamlit run screener_app.py

import streamlit as st
import pandas as pd
from nsepython import nse_optionchain_scrapper, fnolist

st.set_page_config(page_title="FnO Max Pain Screener (Fixed)", layout="wide")
st.title("📊 FnO Screener: Current Price vs Max Pain — (corrected)")

# Sidebar: Filters
min_dev = st.sidebar.slider(
    "Show only stocks with deviation % greater than:", 
    min_value=0.0, max_value=10.0, value=2.0, step=0.5
)

search_symbol = st.sidebar.text_input("Search by stock symbol (e.g. INFY, RELIANCE):", "").upper()
debug_single = st.sidebar.checkbox("Show debug (candidate payouts) for searched symbol", value=False)

# Cache option chain fetch for short period to avoid re-fetching same symbol repeatedly
@st.cache_data(ttl=60)  # cache for 60 seconds
def fetch_option_chain(symbol):
    return nse_optionchain_scrapper(symbol)

def calculate_max_pain_for_symbol(symbol):
    """
    Returns dict with Symbol, LTP, Max Pain (strike), Diff% OR raises/returns None on error.
    Uses the classical max-pain calculation (minimizes total payout to option buyers).
    """
    try:
        option_chain = fetch_option_chain(symbol)
        records = option_chain.get('records', {})
        ltp = float(records.get('underlyingValue', 0.0))

        expiry_dates = records.get('expiryDates', [])
        if not expiry_dates:
            return None

        expiry = expiry_dates[0]  # nearest by default

        data = records.get('data', [])
        # Build strike -> CE_OI and PE_OI (missing CE/PE treated as 0)
        strikes = []
        ce_oi_map = {}
        pe_oi_map = {}
        for item in data:
            if item.get('expiryDate') != expiry:
                continue
            k = item.get('strikePrice')
            if k is None:
                continue
            strikes.append(k)
            ce = 0
            pe = 0
            if item.get('CE'):
                ce = int(item['CE'].get('openInterest') or 0)
            if item.get('PE'):
                pe = int(item['PE'].get('openInterest') or 0)
            ce_oi_map[k] = ce_oi_map.get(k, 0) + ce
            pe_oi_map[k] = pe_oi_map.get(k, 0) + pe

        strikes = sorted(set(strikes))
        if not strikes:
            return None

        # For each candidate settlement price P (use the available strikes),
        # compute total payout to option buyers:
        # total(P) = sum_over_K [ CE_OI(K) * max(0, P - K) + PE_OI(K) * max(0, K - P) ]
        total_payout_by_P = {}
        for P in strikes:
            total = 0
            # simple loop (small number of strikes so this is fast)
            for K in strikes:
                co = ce_oi_map.get(K, 0)
                po = pe_oi_map.get(K, 0)
                if P > K:
                    total += (P - K) * co
                elif K > P:
                    total += (K - P) * po
                # if P == K, contribution is 0 for that strike
            total_payout_by_P[P] = total

        # Max pain = strike P with minimal total payout
        max_pain_strike = min(total_payout_by_P, key=total_payout_by_P.get)

        diff_pct = ((ltp - max_pain_strike) / max_pain_strike) * 100 if max_pain_strike != 0 else 0.0

        return {
            "Symbol": symbol,
            "LTP": round(ltp, 2),
            "Max Pain": int(max_pain_strike),
            "Diff %": round(diff_pct, 2),
            "CandidatePayouts": total_payout_by_P  # for debug only
        }

    except Exception as e:
        return {"Symbol": symbol, "Error": str(e)}

# Run screener
if st.button("Run Screener"):
    fno_list = fnolist()
    results = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, sym in enumerate(fno_list, start=1):
        status_text.text(f"Processing {sym} ({idx}/{len(fno_list)})...")
        res = calculate_max_pain_for_symbol(sym)
        if res and res.get("Error") is None:
            results.append({
                "Symbol": res["Symbol"],
                "LTP": res["LTP"],
                "Max Pain": res["Max Pain"],
                "Diff %": res["Diff %"],
            })
        else:
            # skip errors but you can log them if needed
            pass

        progress_bar.progress(int(100 * idx / len(fno_list)))

    progress_bar.empty()
    status_text.empty()

    if not results:
        st.warning("No results — check that nsepython is working and FnO list is available.")
    else:
        df_results = pd.DataFrame(results)
        # Apply deviation filter
        df_filtered = df_results[df_results["Diff %"].abs() >= min_dev]

        # Apply search filter if given
        if search_symbol:
            df_filtered = df_filtered[df_filtered["Symbol"].str.contains(search_symbol, case=False, na=False)]

        # Sort by absolute deviation (largest first)
        df_filtered = df_filtered.assign(absdev=df_filtered["Diff %"].abs())
        df_sorted = df_filtered.sort_values("absdev", ascending=False).drop(columns=["absdev"])

        st.subheader(f"Results (Deviation ≥ {min_dev}%)")
        st.dataframe(df_sorted, use_container_width=True)

        # Download button
        csv = df_sorted.to_csv(index=False).encode('utf-8')
        st.download_button("Download Filtered CSV", data=csv, file_name="screener_results.csv", mime="text/csv")

# --- Top 5 Bullish & Bearish Picks ---
if not df_sorted.empty:
    # Bullish = LTP > Max Pain, sorted by largest positive deviation
    top5_bullish = (
        df_sorted[df_sorted['Diff %'] > 0]
        .sort_values("Diff %", ascending=False)
        .head(5)
    )

    # Bearish = LTP < Max Pain, sorted by most negative deviation
    top5_bearish = (
        df_sorted[df_sorted['Diff %'] < 0]
        .sort_values("Diff %")
        .head(5)
    )

    if not top5_bullish.empty:
        st.subheader("🚀 Top 5 Bullish (LTP > Max Pain)")
        st.dataframe(top5_bullish, use_container_width=True)

    if not top5_bearish.empty:
        st.subheader("📉 Top 5 Bearish (LTP < Max Pain)")
        st.dataframe(top5_bearish, use_container_width=True)

        
        # If user asked for debug and searched specific symbol, show candidate payouts
        if debug_single and search_symbol:
            # try fetch the single symbol to show candidate payouts
            debug_sym = search_symbol
            debug_res = calculate_max_pain_for_symbol(debug_sym)
            if debug_res and "CandidatePayouts" in debug_res:
                payouts = debug_res["CandidatePayouts"]
                # show top 10 lowest payouts (likely near max pain)
                df_dbg = pd.DataFrame(
                    sorted(payouts.items(), key=lambda x: x[1])[:10],
                    columns=["CandidateStrike", "TotalPayout"]
                )
                st.subheader(f"Debug: Candidate payouts for {debug_sym} (lowest first)")
                st.dataframe(df_dbg)
            else:
                st.info("No debug data available for that symbol (maybe it's not FnO or fetch failed).")
