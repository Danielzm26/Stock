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
@st.cache_data(ttl=600, show_spinner=False)
def download_all(stocks):
    try:
        end = datetime.now()
        start = end - timedelta(days=365 * 3)

        request = StockBarsRequest(
            symbol_or_symbols=stocks,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed="iex"
        )

        bars = client.get_stock_bars(request).df

        if bars is None or bars.empty:
            return {}

        data = {}

        for symbol in stocks:
            try:
                # ✅ Manejo robusto del index
                if isinstance(bars.index, pd.MultiIndex):
                    if symbol not in bars.index.get_level_values(0):
                        continue
                    df = bars.xs(symbol, level=0).copy()
                else:
                    df = bars[bars["symbol"] == symbol].copy()

                # ✅ Columnas seguras
                df = df.rename(columns=str.title)
                needed = ["Open","High","Low","Close","Volume"]
                df = df[[c for c in needed if c in df.columns]]

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
def daily_change_table(all_data):
    rows = []

    for ticker, df in all_data.items():
        try:
            if len(df) < 2:
                continue

            df = df.sort_index()
            last = df.iloc[-1]
            prev = df.iloc[-2]

            change_pct = (last["Close"] - prev["Close"]) / prev["Close"] * 100

            rows.append({
                "Ticker": ticker,
                "Close Today": round(last["Close"], 2),
                "Close Prev": round(prev["Close"], 2),
                "% Change": round(change_pct, 2),
                "Type": "📈 Plusvalía" if change_pct > 0 else "📉 Minusvalía"
            })

        except Exception:
            continue

    df_changes = pd.DataFrame(rows)

    if not df_changes.empty:
        df_changes = df_changes.sort_values("% Change", ascending=False)

    return df_changes
def daily_change_table(all_data):
    rows = []

    for ticker, df in all_data.items():
        try:
            if len(df) < 2:
                continue

            df = df.sort_index()
            last = df.iloc[-1]
            prev = df.iloc[-2]

            change_pct = (last["Close"] - prev["Close"]) / prev["Close"] * 100

            rows.append({
                "Ticker": ticker,
                "Close Today": round(last["Close"], 2),
                "Close Prev": round(prev["Close"], 2),
                "% Change": round(change_pct, 2),
                "Type": "📈 Plusvalía" if change_pct > 0 else "📉 Minusvalía"
            })

        except Exception:
            continue

    df_changes = pd.DataFrame(rows)

    if not df_changes.empty:
        df_changes = df_changes.sort_values("% Change", ascending=False)

    return df_changes
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
def daily_change_table(all_data):
    rows = []

    for ticker, df in all_data.items():
        try:
            if len(df) < 2:
                continue

            df = df.sort_index()
            last = df.iloc[-1]
            prev = df.iloc[-2]

            change_pct = (last["Close"] - prev["Close"]) / prev["Close"] * 100

            rows.append({
                "Ticker": ticker,
                "Close Today": round(last["Close"], 2),
                "Close Prev": round(prev["Close"], 2),
                "% Change": round(change_pct, 2),
                "Type": "📈 Plusvalía" if change_pct > 0 else "📉 Minusvalía"
            })

        except Exception:
            continue

    df_changes = pd.DataFrame(rows)

    if not df_changes.empty:
        df_changes = df_changes.sort_values("% Change", ascending=False)

    return df_changes
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
st.sidebar.header("⚙️ Risk Management")

account_size = st.sidebar.number_input("💰 Capital ($)", value=10000)
risk_pct = st.sidebar.slider("⚠️ Riesgo por trade (%)", 0.5, 5.0, 1.0) / 100
# ========================= UI =========================
st.title("🔥 Quant Screener PRO — INTERACTIVE")

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
# ========================= 📊 DAILY CHANGE =========================
st.subheader("📊 Cambio Diario (Plusvalía / Minusvalía)")

df_changes = daily_change_table(data)

if not df_changes.empty:
    def highlight_row(row):
        if row["% Change"] > 0:
            return ["background-color: rgba(0,255,0,0.15)"] * len(row)
        elif row["% Change"] < 0:
            return ["background-color: rgba(255,0,0,0.15)"] * len(row)
        return [""] * len(row)


    def color_pct(val):
        if isinstance(val, (int, float)):
            return "color: lime; font-weight: bold" if val > 0 else "color: red; font-weight: bold"
        return ""


    def color_type(val):
        return "color: lime; font-weight: bold" if "Plusvalía" in val else "color: red; font-weight: bold"


    styled_df = (
        df_changes.style
            .apply(highlight_row, axis=1)
            .map(color_pct, subset=["% Change"])
            .map(color_type, subset=["Type"])
            .format({"% Change": "{:.2f}%"})
    )

    st.dataframe(styled_df, use_container_width=True)
else:
    st.warning("No hay datos suficientes")
if pro_table:
    st.dataframe(pd.DataFrame(pro_table).sort_values("Score", ascending=False))
else:
    st.warning("Sin setups")
# ========================= 📊 GRAFICA PRO+ (SEÑALES) =========================
# ========================= 📊 HEDGE FUND MODE =========================
if data_map:
    selected = st.selectbox("Ticker", list(data_map.keys()))
    df_chart = data_map[selected].copy()

    # ================= INDICADORES =================
    df_chart["SMA50"] = df_chart["Close"].rolling(50).mean()
    df_chart["SMA200"] = df_chart["Close"].rolling(200).mean()

    # RSI
    delta = df_chart["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df_chart["RSI"] = 100 - (100 / (1 + rs))

    # ATR
    tr = pd.concat([
        df_chart["High"] - df_chart["Low"],
        (df_chart["High"] - df_chart["Close"].shift()).abs(),
        (df_chart["Low"] - df_chart["Close"].shift()).abs()
    ], axis=1).max(axis=1)
    df_chart["ATR"] = tr.rolling(14).mean()

    # Momentum
    df_chart["Momentum"] = df_chart["Close"].pct_change(5)

    # ================= SEÑALES FILTRADAS =================
    df_chart["BUY"] = (
        (df_chart["SMA50"] > df_chart["SMA200"]) &
        (df_chart["RSI"] > 40) &
        (df_chart["Momentum"] > 0)
    )

    df_chart["SELL"] = (
        (df_chart["SMA50"] < df_chart["SMA200"]) &
        (df_chart["RSI"] < 60) &
        (df_chart["Momentum"] < 0)
    )

    # ================= BACKTEST VISUAL =================
    trades = []
    in_trade = False

    for i in range(len(df_chart)):
        row = df_chart.iloc[i]

        if not in_trade and row["BUY"]:
            entry = row["Close"]
            sl = entry - row["ATR"] * 1.5
            tp1 = entry + row["ATR"] * 1.5
            tp2 = entry + row["ATR"] * 3

            # ================= POSITION SIZING =================
            risk_per_share = abs(entry - sl)

            if risk_per_share > 0:
                position_size = (account_size * risk_pct) / risk_per_share
                shares = int(position_size)

                dollar_position = shares * entry
            else:
                shares = 0
                dollar_position = 0

            trades.append({
                "entry_idx": i,
                "entry_price": entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "exit_idx": None,
                "exit_price": None,
                "shares": shares,
                "position_value": dollar_position,
                "risk_per_share": risk_per_share
            })
            in_trade = True

        elif in_trade:
            current_trade = trades[-1]

            if row["Low"] <= current_trade["sl"]:
                current_trade["exit_idx"] = i
                current_trade["exit_price"] = current_trade["sl"]
                in_trade = False

            elif row["High"] >= current_trade["tp2"]:
                current_trade["exit_idx"] = i
                current_trade["exit_price"] = current_trade["tp2"]
                in_trade = False

    # ================= FIGURA =================
    from plotly.subplots import make_subplots
    import numpy as np

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.2, 0.2],
        vertical_spacing=0.03
    )

    colors = np.where(df_chart["Close"] >= df_chart["Open"], "green", "red")

    # PRICE
    fig.add_trace(go.Candlestick(
        x=df_chart.index,
        open=df_chart["Open"],
        high=df_chart["High"],
        low=df_chart["Low"],
        close=df_chart["Close"],
        name="Price"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["SMA50"], name="SMA50"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["SMA200"], name="SMA200"), row=1, col=1)

    # ================= DIBUJAR TRADES =================
    for t in trades:
        if t["exit_idx"] is None:
            continue

        x0 = df_chart.index[t["entry_idx"]]
        x1 = df_chart.index[t["exit_idx"]]

        # Línea entrada
        fig.add_shape(type="line",
            x0=x0, x1=x1,
            y0=t["entry_price"], y1=t["entry_price"],
            line=dict(color="blue", width=2)
        )
        fig.add_annotation(
            x=x0,
            y=t["entry_price"],
            text=f"{t['shares']} shares<br>${int(t['position_value'])}",
            showarrow=True,
            arrowhead=1,
            font=dict(size=10, color="white"),
            bgcolor="black"
        )
        # SL
        fig.add_shape(type="line",
            x0=x0, x1=x1,
            y0=t["sl"], y1=t["sl"],
            line=dict(color="red", dash="dot")
        )

        # TP
        fig.add_shape(type="line",
            x0=x0, x1=x1,
            y0=t["tp2"], y1=t["tp2"],
            line=dict(color="green", dash="dot")
        )

    # VOLUME
    fig.add_trace(go.Bar(
        x=df_chart.index,
        y=df_chart["Volume"],
        marker_color=colors,
        opacity=0.5
    ), row=2, col=1)

    # RSI
    fig.add_trace(go.Scatter(
        x=df_chart.index,
        y=df_chart["RSI"],
        name="RSI"
    ), row=3, col=1)

    fig.add_hline(y=70, row=3, col=1)
    fig.add_hline(y=30, row=3, col=1)

    fig.update_layout(
        title=f"{selected} — HEDGE FUND MODE",
        template="plotly_dark",
        height=900,
        hovermode="x unified"
    )
    # ================= LAYOUT =================
    fig.update_layout(
        title=f"{selected} — PRO+ Signals",
        template="plotly_dark",
        height=850,
        hovermode="x unified",

        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(step="all")
                ])
            ),
            rangeslider=dict(visible=False),
            type="date"
        )
    )
    st.plotly_chart(fig, use_container_width=True)
