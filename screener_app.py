import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ---------- Utility Functions ----------
def get_max_pain(ticker):
    try:
        opt = yf.Ticker(ticker)
        expiries = opt.options
        if not expiries:
            return None, None

        expiry = expiries[0]  # nearest expiry
        chain = opt.option_chain(expiry)
        calls = chain.calls[['strike', 'openInterest']].rename(columns={'openInterest': 'callOI'})
        puts = chain.puts[['strike', 'openInterest']].rename(columns={'openInterest': 'putOI'})
        df = pd.merge(calls, puts, on="strike", how="outer").fillna(0)

        # Calculate total pain for each strike
        df['callPain'] = (df['callOI'] * abs(df['strike'] - df['strike'].mean()))
        df['putPain'] = (df['putOI'] * abs(df['strike'] - df['strike'].mean()))
        df['totalPain'] = df['callPain'] + df['putPain']

        max_pain_strike = df.loc[df['totalPain'].idxmin(), 'strike']
        return max_pain_strike, expiry
    except Exception as e:
        print(f"Error fetching option chain for {ticker}: {e}")
        return None, None


def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="3mo")
    if hist.empty:
        return None, None, None

    close = hist['Close']
    volume = hist['Volume']
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

    avg_volume = volume.rolling(20).mean().iloc[-1]
    current_volume = volume.iloc[-1]
    vol_strength = current_volume / avg_volume if avg_volume > 0 else 0

    return close.iloc[-1], ema20, ema50, vol_strength


# ---------- Screener Logic ----------
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

        # Trend check
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


# ---------- Main Run ----------
if __name__ == "__main__":
    tickers = ["PNBHOUSING.NS", "RELIANCE.NS", "HDFCBANK.NS", "TCS.NS", "INFY.NS", "SBIN.NS"]

    df = analyze_stocks(tickers)
    if not df.empty:
        top_bullish, top_bearish = pick_top_stocks(df)

        print("\n=== Full Screener Output ===")
        print(df)

        print("\n=== Top 5 Bullish ===")
        print(top_bullish[['Ticker', 'Price', 'MaxPain', 'Deviation%', 'Trend', 'VolumeStrength']])

        print("\n=== Top 5 Bearish ===")
        print(top_bearish[['Ticker', 'Price', 'MaxPain', 'Deviation%', 'Trend', 'VolumeStrength']])
    else:
        print("No valid data fetched.")
