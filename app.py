import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# ========================= CONFIG =========================
st.set_page_config(layout="wide")
load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    st.error("❌ API Keys no configuradas")
    st.stop()

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

stocks = ["MU","MSFT","CIEN","VST","NVDA","TSLA","PLTR","AMD","AMZN","AAPL","NFLX",
          "CRWD","NOW","NBIS","BE","ALAB","COIN","SOFI","HIMS","INTC","SNDK","HOOD",
          "CRM","TSM","ASTS","HPE","NU","DUOL","SOUN","UPST","FSLR","RGTI","DELL",
          "OXY","MSTR","ORCL","ARM","OSCR","CIFR","AAL","MRNA","WULF","RIOT","MARA",
          "SMCI","SNOW"]

# ========================= DATA =========================
@st.cache_data(ttl=600)
def download_all(stocks):
    try:
        end = datetime.now()
        start = end - timedelta(days=365 * 3)

request = StockBarsRequest(
    symbol_or_symbols=stocks,
    timeframe=TimeFrame.Day,
    start=start,
    end=end,
    feed="iex"   # 👈 ESTA LÍNEA ES LA CLAVE
)

        bars = client.get_stock_bars(request).df

        if bars is None or bars.empty:
            return {}

        data = {}

        for symbol in stocks:
            try:
                if symbol not in bars.index.get_level_values(0):
                    continue

                df = bars.xs(symbol, level=0).copy()

                df.columns = ["Open","High","Low","Close","Volume","Trades","VWAP"]

                df = df[["Open","High","Low","Close","Volume"]]

                df.index = pd.to_datetime(df.index)
                df = df.sort_index().dropna()

                if len(df) > 100:
                    data[symbol] = df

            except Exception:
                continue

        return data

    except Exception as e:
        st.error(f"Error descargando datos: {e}")
        return {}

# ========================= MARKET =========================
@st.cache_data(ttl=600)
def market_condition():
    data = download_all(["SPY"])
    df = data.get("SPY")

    if df is None or len(df) < 200:
        return "UNKNOWN"

    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    df = df.dropna()
    if df.empty:
        return "UNKNOWN"

    last = df.iloc[-1]

    if last["SMA50"] > last["SMA200"]:
        return "BULL"
    elif last["SMA50"] < last["SMA200"]:
        return "BEAR"
    return "SIDEWAYS"

# ========================= FACTORS =========================
def compute_factors(df):
    df = df.copy()

    df["Return_20d"] = df["Close"].pct_change(20)
    df["Volatility"] = df["Close"].pct_change().rolling(20).std()

    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))

    df["AvgVol"] = df["Volume"].rolling(20).mean()

    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"] - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)

    df["ATR"] = tr.rolling(14).mean()

    return df.dropna()

# ========================= SCORING =========================
def probability(score):
    return np.clip(score**1.4, 0.01, 0.99)

def rating(prob):
    if prob > 0.80:
        return "🚀 Strong Buy"
    elif prob > 0.65:
        return "🟢 Buy"
    elif prob > 0.50:
        return "🟡 Neutral"
    elif prob > 0.35:
        return "⚠️ Weak"
    return "🔴 Sell"

# ========================= CROSS SECTION =========================
def build_cross_section(all_data):
    rows = []

    for s, df in all_data.items():
        try:
            df = compute_factors(df)
            if df.empty:
                continue

            last = df.iloc[-1]

            rows.append({
                "Ticker": s,
                "momentum": df["Return_20d"].iloc[-1],
                "trend": last["Close"] / (last["SMA200"] + 1e-9),
                "rsi": last["RSI"],
                "volume": last["Volume"] / (last["AvgVol"] + 1e-9),
                "volatility": last["Volatility"]
            })

        except Exception:
            continue

    cs = pd.DataFrame(rows)

    if cs.empty:
        return cs

    cs = cs.replace([np.inf, -np.inf], np.nan).dropna()

    for col in ["momentum","trend","volume","rsi","volatility"]:
        cs[col] = cs[col].rank(pct=True)

    return cs

# ========================= ANALYSIS =========================
def analyze(stock, cs, all_data, market):
    if stock not in all_data:
        return None

    df = compute_factors(all_data[stock])
    if df.empty:
        return None

    last = df.iloc[-1]
    row = cs[cs["Ticker"] == stock]

    if row.empty:
        return None

    row = row.iloc[0]

    market_factor = 1.05 if market == "BULL" else 0.95 if market == "BEAR" else 1

    score = (
        row["momentum"] * 0.35 +
        row["trend"] * 0.30 +
        row["volume"] * 0.20 +
        row["rsi"] * 0.10 +
        (1 - row["volatility"]) * 0.05
    )

    score = np.clip(score * market_factor, 0, 1)
    prob = probability(score)

    return {
        "Ticker": stock,
        "Price": round(last["Close"], 2),
        "Score": round(score, 3),
        "Probability": f"{int(prob*100)}%",
        "Rating": rating(prob),
        "BuyZone": round(last["Close"] - last["ATR"], 2),
        "SellZone": round(last["Close"] + last["ATR"] * 2.2, 2),
        "Data": df
    }

# ========================= UI =========================
st.title("🔥 Quant Screener PRO — FIXED")

market = market_condition()
st.metric("Market Regime", market)

data = download_all(stocks)
cs = build_cross_section(data)

results = []
pro_table = []
data_map = {}

for s in stocks:
    r = analyze(s, cs, data, market)
    if r:
        results.append({
            "Ticker": r["Ticker"],
            "Price": r["Price"],
            "Score": r["Score"]
        })

        pro_table.append({
            "Ticker": r["Ticker"],
            "Price": r["Price"],
            "Buy": r["BuyZone"],
            "Sell": r["SellZone"],
            "Score": r["Score"],
            "Prob": r["Probability"],
            "Signal": r["Rating"]
        })

        data_map[s] = r["Data"]

df = pd.DataFrame(results)

st.subheader("📊 Ranking")
if not df.empty:
    st.dataframe(df.sort_values("Score", ascending=False))
else:
    st.warning("Sin datos suficientes")

st.subheader("🚀 Trade Setup")
if pro_table:
    st.dataframe(pd.DataFrame(pro_table).sort_values("Score", ascending=False))
else:
    st.warning("Sin setups")

if data_map:
    selected = st.selectbox("Ticker", list(data_map.keys()))
    st.line_chart(data_map[selected]["Close"])
