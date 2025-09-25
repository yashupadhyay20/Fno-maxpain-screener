# screener_app.py
import streamlit as st
import pandas as pd
import numpy as np
from nsepython import *
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import time

st.set_page_config(page_title="F&O Max Pain Screener (nsepython + bhavcopy)", layout="wide")

# -------------------------
# Built-in fallback F&O list (used if API lookup fails)
# Shortened here for readability; expand if you like.
FNO_FALLBACK = [
    "RELIANCE","HDFCBANK","ICICIBANK","INFY","TCS","SBIN","AXISBANK","KOTAKBANK","ITC","HINDUNILVR",
    "HCLTECH","WIPRO","LT","BAJFINANCE","ADANIENT","ADANIPORTS","POWERGRID","ONGC","COALINDIA","BPCL",
    "IOC","HDFCLIFE","ULTRACEMCO","MARUTI","M&M","TITAN","SUNPHARMA","CIPLA","NTPC","TATAMOTORS",
    "TATASTEEL","HEROMOTOCO","JSWSTEEL","SBICARD","BAJAJFINSV","DIVISLAB","DRREDDY","GRASIM","EICHERMOT",
    "HINDALCO","TECHM","TATAPOWER","TORNTPOWER","PIDILITIND","ONGC","BPCL","GODREJCP","ADANIENTERPRISES"
]
# You can replace/extend FNO_FALLBACK with the full list you use.

# -------------------------
# Utility: Try multiple functions for FNO list (fnolist, nse_fno) with fallback
@st.cache_data(ttl=3600, show_spinner=False)
def get_fno_list():
    candidates = []
    # try fnolist()
    try:
        fl = fnolist()
        if fl:
            # fnolist may return a list or dataframe depending on version; normalize
            if isinstance(fl, (list, tuple)):
                candidates = list(fl)
            elif isinstance(fl, pd.DataFrame):
                if "symbol" in fl.columns.str.lower():
                    candidates = list(fl.iloc[:,0].astype(str).tolist())
                else:
                    candidates = list(fl.squeeze().astype(str).tolist())
    except Exception:
        pass

    # try nse_fno()
    if not candidates:
        try:
            df = nse_fno()
            if isinstance(df, pd.DataFrame) and "SYMBOL" in df.columns:
                candidates = list(df["SYMBOL"].dropna().unique())
        except Exception:
            pass

    # fallback to built-in list if still empty
    if not candidates:
        candidates = FNO_FALLBACK.copy()

    # normalize (strings, uppercase)
    candidates = [str(x).strip().upper() for x in candidates if str(x).strip()]
    return sorted(list(dict.fromkeys(candidates)))  # unique preserve order

# -------------------------
# Bhavcopy (EOD) fetch
@st.cache_data(ttl=3600, show_spinner=False)
def get_bhavcopy_for_range(days=90):
    """
    Build a combined bhavcopy-like dataframe for the last `days` trading days
    using nsepython's bhavcopy_equities (which fetches a single day each call).
    This function attempts to collect last `days` days but will skip days that fail.
    Note: Bhavcopy is EOD — this may take time for many days. We limit attempts.
    """
    out = []
    attempts = 0
    day = datetime.today() - timedelta(days=1)
    while len(out) < days and attempts < (days + 10):
        try:
            df = bhavcopy_equities(day)  # returns dataframe for that day
            if isinstance(df, pd.DataFrame) and not df.empty:
                # Keep the symbol, CLOSE, TOTTRDQTY, TIMESTAMP (or create Date)
                df2 = df[["SYMBOL","CLOSE","TOTTRDQTY"]].copy()
                df2["DATE"] = day.strftime("%Y-%m-%d")
                out.append(df2)
        except Exception:
            pass
        attempts += 1
        day = day - timedelta(days=1)

    if not out:
        return pd.DataFrame()   # failed to fetch any bhavcopy
    combined = pd.concat(out, ignore_index=True)
    # Ensure numeric columns
    combined["CLOSE"] = pd.to_numeric(combined["CLOSE"], errors="coerce")
    combined["TOTTRDQTY"] = pd.to_numeric(combined["TOTTRDQTY"], errors="coerce")
    return combined

# -------------------------
# Option chain cache (per symbol)
@st.cache_data(ttl=300, show_spinner=False)
def fetch_option_chain(symbol):
    """
    Fetch option chain via nsepython. Returns dict or raises.
    """
    return nse_optionchain_scrapper(symbol)

def compute_max_pain_from_chain(chain):
    """
    Given the option chain dict from nse_optionchain_scrapper,
    compute true max pain (strike that minimizes total payout).
    Returns (max_pain_strike (float/int), underlying_value (float)) or (None, None).
    """
    try:
        rec = chain.get("records", {})
        data = rec.get("data", []) or []
        underlying = rec.get("underlyingValue", None)
        if not data:
            return None, underlying

        expiry = rec.get("expiryDates", [None])[0]
        ce_oi = {}
        pe_oi = {}
        strikes = set()
        for item in data:
            if expiry and item.get("expiryDate") != expiry:
                continue
            k = item.get("strikePrice")
            if k is None:
                continue
            strikes.add(k)
            ce = 0
            pe = 0
            if item.get("CE"):
                ce = int(item["CE"].get("openInterest") or 0)
            if item.get("PE"):
                pe = int(item["PE"].get("openInterest") or 0)
            ce_oi[k] = ce_oi.get(k, 0) + ce
            pe_oi[k] = pe_oi.get(k, 0) + pe

        strikes = sorted(list(strikes))
        if not strikes:
            return None, underlying

        # For each candidate P compute total payout to option buyers
        payout = {}
        for P in strikes:
            total = 0
            for K in strikes:
                co = ce_oi.get(K, 0)
                po = pe_oi.get(K, 0)
                if P > K:
                    total += (P - K) * co
                elif K > P:
                    total += (K - P) * po
            payout[P] = total

        # pick strike with minimum payout
        max_pain_strike = min(payout, key=payout.get)
        return float(max_pain_strike), underlying
    except Exception:
        return None, None

# -------------------------
# Historical series fetch (try stock_history)
@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(symbol, days=90):
    """
    Try to grab historical OHLC (CLOSE & VOLUME) using nsepython.stock_history.
    Returns pandas DataFrame with DATE index and CLOSE, TOTTRDQTY/VOLUME columns.
    If fails, returns empty DataFrame.
    """
    try:
        to_date = datetime.today()
        from_date = to_date - timedelta(days=days*2)  # request more days to handle non-trading days
        # nsepython.stock_history expects dd-mm-YYYY strings and symbol param
        hist = stock_history(symbol=symbol, from_date=from_date.strftime("%d-%m-%Y"), to_date=to_date.strftime("%d-%m-%Y"))
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            # normalize column names
            cols = [c.upper() for c in hist.columns]
            hist.columns = cols
            # CLOSE might be 'CLOSE' or 'CLOSE' already; volume may be 'TOTTRDQTY' or 'VOLUME'
            # Keep CLOSE and TOTTRDQTY if present
            keep_cols = []
            if "CLOSE" in hist.columns:
                keep_cols.append("CLOSE")
            elif "CLOSE_PRICE" in hist.columns:
                hist["CLOSE"] = hist["CLOSE_PRICE"]
                keep_cols.append("CLOSE")
            if "TOTTRDQTY" in hist.columns:
                keep_cols.append("TOTTRDQTY")
            elif "VOLUME" in hist.columns:
                hist["TOTTRDQTY"] = hist["VOLUME"]
                keep_cols.append("TOTTRDQTY")
            return hist.reset_index(drop=True)
        else:
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# -------------------------
# Analyze one symbol (robust)
def analyze_one(symbol, bhav_combined):
    """
    Analyze a single symbol:
    - compute CMP (from latest bhavcombined date if available; else from history)
    - compute max pain from option chain
    - compute EMA20/50 using history (if available)
    - compute volume strength (today volume / avg vol)
    - return dict or None
    """
    try:
        sym = symbol.strip().upper()
        # Try to get latest price and today's volume from the combined bhavcopy (which has many dates)
        df_sym = bhav_combined[bhav_combined["SYMBOL"] == sym] if not bhav_combined.empty else pd.DataFrame()
        cmp_price = None
        today_vol = None
        # If we have bhav combined, take last date for that symbol
        if not df_sym.empty:
            # sort by DATE
            df_sym_sorted = df_sym.sort_values("DATE")
            cmp_price = float(df_sym_sorted["CLOSE"].iloc[-1])
            today_vol = float(df_sym_sorted["TOTTRDQTY"].iloc[-1])
            # For series, take last 90 days of CLOSE & TOTTRDQTY
            prices_series = df_sym_sorted["CLOSE"].astype(float).tail(90).reset_index(drop=True)
            vol_series = df_sym_sorted["TOTTRDQTY"].astype(float).tail(90).reset_index(drop=True)
        else:
            prices_series = pd.Series(dtype=float)
            vol_series = pd.Series(dtype=float)

        # If bhav-based series is empty, try stock_history
        if prices_series.empty or len(prices_series) < 10:
            hist = fetch_history(sym, days=90)
            if not hist.empty and "CLOSE" in hist.columns:
                prices_series = hist["CLOSE"].astype(float).tail(90).reset_index(drop=True)
                if "TOTTRDQTY" in hist.columns:
                    vol_series = hist["TOTTRDQTY"].astype(float).tail(90).reset_index(drop=True)
                # set cmp_price if missing
                if cmp_price is None and not prices_series.empty:
                    cmp_price = float(prices_series.iloc[-1])

        # If still missing cmp_price, try nse_eq (live price)
        if cmp_price is None:
            try:
                eq = nse_eq(sym)
                cmp_price = float(eq.get("priceInfo", {}).get("lastPrice", np.nan))
                today_vol = float(eq.get("preOpenMarket", {}).get("totalTradedVolume", np.nan) or np.nan)
            except Exception:
                pass

        # compute EMAs (fallback: if not enough history, use cmp repeated to avoid crashes)
        if prices_series.empty:
            prices_series = pd.Series([cmp_price] * 50)
        ema20 = float(prices_series.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(prices_series.ewm(span=50, adjust=False).mean().iloc[-1])

        # compute vol strength
        vol_strength = 1.0
        if not vol_series.empty and len(vol_series) >= 20:
            avg_vol = vol_series.rolling(20).mean().iloc[-1]
            today_v = vol_series.iloc[-1] if today_vol is None else today_vol
            try:
                vol_strength = float(today_v / avg_vol) if avg_vol > 0 else 1.0
            except Exception:
                vol_strength = 1.0
        else:
            vol_strength = 1.0

        # Option chain & Max Pain
        try:
            chain = fetch_option_chain(sym)
            max_pain, underlying = compute_max_pain_from_chain(chain)
        except Exception:
            max_pain, underlying = None, None

        deviation = None
        if max_pain and cmp_price and max_pain != 0:
            deviation = ((cmp_price - max_pain) / max_pain) * 100

        # Trend check: strictly price > ema20 > ema50 for Bullish, reverse for Bearish
        trend = "Neutral"
        try:
            if (cmp_price is not None) and (cmp_price > ema20 > ema50):
                trend = "Bullish"
            elif (cmp_price is not None) and (cmp_price < ema20 < ema50):
                trend = "Bearish"
        except Exception:
            trend = "Neutral"

        return {
            "Symbol": sym,
            "CMP": round(float(cmp_price), 2) if cmp_price is not None and not math.isnan(cmp_price) else None,
            "MaxPain": round(float(max_pain), 2) if max_pain else None,
            "Deviation%": round(float(deviation), 2) if deviation is not None else None,
            "EMA20": round(ema20, 2),
            "EMA50": round(ema50, 2),
            "VolumeStrength": round(vol_strength, 2),
            "Trend": trend
        }

    except Exception:
        return None

# -------------------------
# Top picks selector (robust fallback)
def pick_top(df):
    df_valid = df.dropna(subset=["CMP"]) if not df.empty else df
    # prefer candidates with Deviation and VolumeStrength info
    bullish_candidates = df_valid[df_valid["Deviation%"] > 0].copy()
    bearish_candidates = df_valid[df_valid["Deviation%"] < 0].copy()

    # primary sort: deviation desc + volume desc for bullish, deviation asc + volume desc for bearish
    bull = bullish_candidates.sort_values(by=["Deviation%","VolumeStrength"], ascending=[False,False]).head(5)
    bear = bearish_candidates.sort_values(by=["Deviation%","VolumeStrength"], ascending=[True,False]).head(5)

    # fallback if empty: relax Trend/Volume constraints and pick by absolute deviation
    if bull.empty:
        fallback_b = df_valid[df_valid["Deviation%"].notnull()].sort_values(by="Deviation%", ascending=False).head(5)
        bull = fallback_b
    if bear.empty:
        fallback_br = df_valid[df_valid["Deviation%"].notnull()].sort_values(by="Deviation%", ascending=True).head(5)
        bear = fallback_br

    # final fallback: if still empty, pick top by abs deviation
    if bull.empty and not df_valid.empty:
        bull = df_valid.assign(absdev=df_valid["Deviation%"].abs().fillna(0)).sort_values("absdev", ascending=False).head(5).drop(columns=["absdev"])
    if bear.empty and not df_valid.empty:
        bear = df_valid.assign(absdev=df_valid["Deviation%"].abs().fillna(0)).sort_values("absdev", ascending=False).head(5).drop(columns=["absdev"])

    return bull.reset_index(drop=True), bear.reset_index(drop=True)

# -------------------------
# Streamlit UI & run
st.title("📊 NSE F&O Max Pain Screener — nsepython + Bhavcopy (robust)")

st.markdown("**How it works:** Loads F&O list (via nsepython), builds a bhavcopy series (EOD), fetches option chains, calculates Max Pain (correct payout method), computes EMA20/50 and volume strength, then shows full table + Top 5 bullish/bearish.")

if st.button("Run full screener (may take 2-6 minutes on first run)"):
    start = time.time()
    st.info("Loading F&O list...")
    fno_list = get_fno_list()
    st.write(f"Found {len(fno_list)} F&O symbols (using API/fallback).")

    st.info("Building bhavcopy series (EOD data). This may take up to a couple minutes for many days...")
    bhav_combined = get_bhavcopy_for_range(days=90)
    if bhav_combined.empty:
        st.warning("Could not build bhavcopy history. The app will still try to fetch history per-symbol when possible.")

    # parallel analyze (careful with workers to avoid throttling)
    results = []
    max_workers = st.sidebar.slider("Parallel workers (lower if you see failures)", min_value=2, max_value=12, value=6, step=1)
    progress = st.progress(0)
    total = len(fno_list)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(analyze_one, sym, bhav_combined): sym for sym in fno_list}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                res = fut.result()
                if res:
                    results.append(res)
            except Exception:
                pass
            completed += 1
