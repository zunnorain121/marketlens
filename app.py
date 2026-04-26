import os
import sqlite3
import json
import os
import traceback
from google import genai
from google.genai import types

from dotenv import load_dotenv
load_dotenv()

from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
import yfinance as yf
import pandas as pd
import numpy as np
from werkzeug.security import check_password_hash, generate_password_hash
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("MARKETLENS_SECRET_KEY", "dev-marketlens-secret-key")
app.config["DATABASE"] = os.path.join(app.root_path, "marketlens.db")
app.config["DB_INITIALIZED"] = False
app.config["OPENAI_MODEL"] = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

CATALOG = [
    {"ticker": "AAPL", "name": "Apple Inc."},
    {"ticker": "TSLA", "name": "Tesla, Inc."},
    {"ticker": "MSFT", "name": "Microsoft Corporation"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation"},
    {"ticker": "AMZN", "name": "Amazon.com, Inc."},
    {"ticker": "META", "name": "Meta Platforms, Inc."},
    {"ticker": "HBL.KA", "name": "Habib Bank Limited"},
    {"ticker": "OGDC.KA", "name": "Oil & Gas Development Company"},
    {"ticker": "PSO.KA", "name": "Pakistan State Oil Company"},
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            UNIQUE(user_id, ticker),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.commit()


@app.before_request
def ensure_db():
    if not app.config["DB_INITIALIZED"]:
        init_db()
        app.config["DB_INITIALIZED"] = True


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    return db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Authentication required."}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper

# ─── EDA & Signal Logic ───────────────────────────────────────────────────────

def fetch_stock_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    df = stock.history(period=period)
    if df.empty:
        raise ValueError(f"No data found for ticker: {ticker}")
    df.index = df.index.tz_localize(None)
    return df


def get_latest_price(ticker: str) -> float:
    stock = yf.Ticker(ticker)
    df = stock.history(period="5d")
    if df.empty:
        raise ValueError(f"No latest price data for ticker: {ticker}")
    return round(float(df["Close"].iloc[-1]), 2)


def compute_eda(df: pd.DataFrame) -> dict:
    close = df["Close"]

    # Basic stats
    mean_price   = round(float(close.mean()), 2)
    median_price = round(float(close.median()), 2)
    std_price    = round(float(close.std()), 2)
    min_price    = round(float(close.min()), 2)
    max_price    = round(float(close.max()), 2)

    # Daily returns
    daily_returns = close.pct_change().dropna()
    avg_return    = round(float(daily_returns.mean()) * 100, 4)
    volatility    = round(float(daily_returns.std()) * 100, 4)

    # Moving averages
    df["MA20"]  = close.rolling(window=20).mean()
    df["MA50"]  = close.rolling(window=50).mean()

    # RSI (14-period)
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # Risk classification
    if volatility < 1.5:
        risk = "Low"
    elif volatility < 3.0:
        risk = "Medium"
    else:
        risk = "High"

    return df, {
        "mean":        mean_price,
        "median":      median_price,
        "std":         std_price,
        "min":         min_price,
        "max":         max_price,
        "avg_return":  avg_return,
        "volatility":  volatility,
        "risk":        risk,
    }


def generate_signal(df: pd.DataFrame) -> dict:
    latest = df.dropna(subset=["MA20", "MA50"]).iloc[-1]
    ma20 = latest["MA20"]
    ma50 = latest["MA50"]
    rsi  = latest["RSI"]
    close = latest["Close"]

    # Rule-based decision
    if ma20 > ma50 and rsi < 70:
        signal = "BUY"
        reason = "Short-term MA is above long-term MA and RSI is not overbought."
    elif ma20 < ma50 and rsi > 30:
        signal = "SELL"
        reason = "Short-term MA is below long-term MA — downward trend detected."
    else:
        signal = "HOLD"
        reason = "Market is relatively stable. No strong directional signal."

    return {
        "signal": signal,
        "reason": reason,
        "ma20":   round(float(ma20), 2),
        "ma50":   round(float(ma50), 2),
        "rsi":    round(float(rsi), 2),
        "close":  round(float(close), 2),
    }


def local_chatbot_fallback(message: str, page: str, data: dict | None = None) -> str:
    msg = (message or "").strip().lower()
    data = data or {}
    ticker = str(data.get("ticker", "")).upper()
    signal = str(data.get("signal", "")).upper()
    rsi = data.get("rsi", "")
    ma20 = data.get("ma20", "")
    ma50 = data.get("ma50", "")

    stock_context = ""
    if ticker:
        stock_context = f" For {ticker}" + (f", the current signal is {signal}." if signal else ".")

    if any(w in msg for w in ["hi", "hello", "hey", "howdy"]):
        return f"Hello! I am MarketLens Assistant. Ask me about RSI, moving averages, BUY/SELL/HOLD signals, or any stock on your dashboard."

    if any(w in msg for w in ["rsi", "relative strength"]):
        base = "RSI (Relative Strength Index) is a momentum indicator from 0 to 100. Above 70 means the stock may be overbought (possible sell zone). Below 30 means it may be oversold (possible buy zone). Between 30 and 70 is neutral."
        if rsi:
            base += f" Currently{' for ' + ticker if ticker else ''}, RSI is {rsi}."
        return base

    if any(w in msg for w in ["ma20", "ma 20", "20 day", "short term average"]):
        base = "MA20 is the 20-day moving average. It reflects the short-term price trend. When price is above MA20, the stock is in a short-term uptrend."
        if ma20:
            base += f" Current MA20{' for ' + ticker if ticker else ''} is {ma20}."
        return base

    if any(w in msg for w in ["ma50", "ma 50", "50 day", "long term average"]):
        base = "MA50 is the 50-day moving average. It reflects the longer-term price trend. When MA20 crosses above MA50, it is considered a bullish crossover signal."
        if ma50:
            base += f" Current MA50{' for ' + ticker if ticker else ''} is {ma50}."
        return base

    if any(w in msg for w in ["moving average", "mas20", "mas50"]):
        return "Moving averages smooth out price data. MA20 tracks short-term trend, MA50 tracks long-term trend. When MA20 is above MA50 it is bullish. When MA20 is below MA50 it is bearish."

    if "buy" in msg:
        return "A BUY signal appears when MA20 is above MA50 (uptrend) and RSI is below 70 (not overbought). This suggests potential upward momentum." + stock_context

    if "sell" in msg:
        return "A SELL signal appears when MA20 is below MA50 (downtrend) and RSI is above 30. This suggests the stock may be losing momentum." + stock_context

    if "hold" in msg:
        return "A HOLD signal means there is no strong trend in either direction. The moving averages are close together and RSI is in neutral territory." + stock_context

    if any(w in msg for w in ["signal", "recommendation"]):
        if signal and ticker:
            return f"The current signal for {ticker} is {signal}.{stock_context} This is based on MA20/MA50 crossover and RSI analysis."
        return "Signals are generated using MA20/MA50 crossover and RSI. BUY when MA20 > MA50 and RSI < 70. SELL when MA20 < MA50 and RSI > 30. Otherwise HOLD."

    if any(w in msg for w in ["volatility", "volatile", "risk"]):
        return "Volatility measures how much a stock price fluctuates. Low volatility (under 1.5%) is safer. Medium is 1.5-3%. High volatility (above 3%) means bigger swings and higher risk."

    if any(w in msg for w in ["watchlist", "watch list"]):
        return "Your watchlist shows all stocks you are tracking. You can add stocks from the Market page and view their signals, RSI, and price changes here on the Dashboard."

    if any(w in msg for w in ["chart", "graph", "trend", "price"]):
        return "The price chart shows closing price, MA20 (blue line), and MA50 (orange line). When the price is above both moving averages, the trend is bullish. The RSI chart below shows momentum."

    if any(w in msg for w in ["dashboard", "dashboads"]):
        return f"The Dashboard shows your watchlist stocks with live prices, signals, RSI values, and moving averages. Click any stock to see its full chart and analysis."

    if any(w in msg for w in ["market", "catalog", "stock list"]):
        return "The Market page shows all available stocks with their latest prices and signals. You can search by name or ticker and add any stock to your watchlist."

    if ticker:
        return f"You are currently viewing {ticker}.{stock_context} Ask me about its RSI, moving averages, signal, or volatility."

    return "I can help you understand RSI, MA20/MA50 moving averages, BUY/SELL/HOLD signals, volatility, and how to use your watchlist. What would you like to know?"


def build_chat_messages(user_message: str, page: str, data: dict, history: list[dict]) -> list[dict]:
    system_prompt = (
        "You are MarketLens AI, a concise financial education assistant. "
        "Help users understand stocks, RSI, moving averages (MA20/MA50), volatility, risk, and BUY/SELL/HOLD signals. "
        "Do not provide guaranteed investment advice. Explain in simple words and reference provided page/data when available."
    )
    page_hint = f"Current page: {page or 'unknown'}."
    data_hint = f"Current page data: {json.dumps(data, ensure_ascii=True)}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": page_hint},
        {"role": "system", "content": data_hint},
    ]

    for item in (history or [])[-10:]:
        role = item.get("role", "")
        content = str(item.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})
    return messages


def call_openai_chat(messages: list[dict]) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env file")

    client = genai.Client(api_key=api_key)

    system_parts = []
    user_message = ""

    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            user_message = content

    full_prompt = ""
    if system_parts:
        full_prompt = "\n".join(system_parts) + "\n\n"
    full_prompt += user_message

    if not full_prompt.strip():
        raise RuntimeError("No message content to send to Gemini")

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt,
        )
        return response.text.strip()
    except Exception as e:
        print("GEMINI FULL ERROR:", traceback.format_exc())
        raise RuntimeError(f"Gemini API Error: {str(e)}")

def build_chart_data(df: pd.DataFrame) -> dict:
    df = df.tail(120)  # last ~4 months for chart clarity
    dates = df.index.strftime("%Y-%m-%d").tolist()

    def clean(series):
        return [round(float(v), 2) if not np.isnan(v) else None for v in series]

    return {
        "dates":   dates,
        "close":   clean(df["Close"]),
        "ma20":    clean(df["MA20"]),
        "ma50":    clean(df["MA50"]),
        "volume":  [int(v) for v in df["Volume"]],
        "rsi":     clean(df["RSI"]),
    }


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return redirect(url_for("home"))


@app.route("/home")
def home():
    return render_template("home.html", user=current_user())


@app.route("/market")
@login_required
def market():
    return render_template("market.html", user=current_user())


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user())


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT id, username, password FROM users WHERE username = ?", (username,)).fetchone()

        if not user or not check_password_hash(user["password"], password):
            error = "Invalid username or password."
        else:
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

    return render_template("login.html", error=error, user=current_user())


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(username) < 3:
            error = "Username must be at least 3 characters."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                error = "Username already exists."

    return render_template("register.html", error=error, user=current_user())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/api/stock")
def get_stock():
    ticker = request.args.get("ticker", "AAPL").upper().strip()
    period = request.args.get("period", "6mo")

    try:
        df = fetch_stock_data(ticker, period)
        df, stats = compute_eda(df)
        signal     = generate_signal(df)
        chart      = build_chart_data(df)

        # Company info
        info = yf.Ticker(ticker).info
        name = info.get("longName") or info.get("shortName") or ticker

        return jsonify({
            "success": True,
            "ticker":  ticker,
            "name":    name,
            "stats":   stats,
            "signal":  signal,
            "chart":   chart,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/catalog")
@login_required
def catalog_data():
    query = request.args.get("q", "").strip().lower()
    filtered = []

    for stock in CATALOG:
        if query and query not in stock["ticker"].lower() and query not in stock["name"].lower():
            continue
        try:
            latest_price = get_latest_price(stock["ticker"])
            hist = fetch_stock_data(stock["ticker"], "6mo")
            hist, _stats = compute_eda(hist)
            signal = generate_signal(hist)["signal"]
        except Exception:
            latest_price = None
            signal = "N/A"

        filtered.append(
            {
                "ticker": stock["ticker"],
                "name": stock["name"],
                "price": latest_price,
                "signal": signal,
            }
        )

    return jsonify({"success": True, "stocks": filtered})


@app.route("/api/compare")
def compare_stocks():
    tickers_raw = request.args.get("tickers", "AAPL,MSFT,GOOGL")
    period      = request.args.get("period", "6mo")
    tickers     = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]

    results = []
    for ticker in tickers[:5]:  # max 5
        try:
            df = fetch_stock_data(ticker, period)
            df, stats = compute_eda(df)
            signal     = generate_signal(df)
            close      = df["Close"]
            pct_change = round(float((close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100), 2)

            results.append({
                "ticker":     ticker,
                "pct_change": pct_change,
                "signal":     signal["signal"],
                "volatility": stats["volatility"],
                "risk":       stats["risk"],
                "close":      signal["close"],
            })
        except Exception:
            continue

    return jsonify({"success": True, "comparison": results})


@app.route("/api/watchlist", methods=["GET", "POST", "DELETE"])
@login_required
def watchlist():
    user = current_user()
    db = get_db()

    if request.method == "GET":
        rows = db.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY ticker ASC", (user["id"],)
        ).fetchall()
        return jsonify({"success": True, "watchlist": [row["ticker"] for row in rows]})

    data = request.get_json(silent=True) or {}
    ticker = (data.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify({"success": False, "error": "Ticker is required."}), 400

    if request.method == "POST":
        try:
            db.execute("INSERT INTO watchlist (user_id, ticker) VALUES (?, ?)", (user["id"], ticker))
            db.commit()
        except sqlite3.IntegrityError:
            pass
        return jsonify({"success": True})

    db.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user["id"], ticker))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/watchlist/stocks")
@login_required
def watchlist_stocks():
    user = current_user()
    db = get_db()
    rows = db.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY ticker ASC", (user["id"],)
    ).fetchall()
    tickers = [r["ticker"] for r in rows]
    stocks = []

    for ticker in tickers:
        try:
            latest_price = get_latest_price(ticker)
            df = fetch_stock_data(ticker, "6mo")
            df, stats = compute_eda(df)
            signal = generate_signal(df)
            stocks.append(
                {
                    "ticker": ticker,
                    "price": latest_price,
                    "signal": signal["signal"],
                    "volatility": stats["volatility"],
                    "risk": stats["risk"],
                }
            )
        except Exception:
            stocks.append({"ticker": ticker, "price": None, "signal": "N/A", "volatility": None, "risk": "N/A"})

    return jsonify({"success": True, "stocks": stocks})


@app.route("/api/chatbot", methods=["POST"])
def api_chatbot():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    page = str(data.get("page", request.path)).strip()
    context_data = data.get("data", data.get("context", {})) or {}
    history = data.get("history", []) or []

    if not message:
        return jsonify({"reply": "Please type your question first."})

    try:
        messages = build_chat_messages(message, page, context_data, history)
        reply = call_openai_chat(messages)
        if not reply:
            raise RuntimeError("Empty reply from Gemini")
        return jsonify({"reply": reply})

    except Exception as e:
        print("CHATBOT ERROR:", traceback.format_exc())
        # Use smart local fallback if Gemini fails
        fallback = local_chatbot_fallback(message, page, context_data)
        return jsonify({"reply": fallback})


@app.route("/api/chatbot-test")
def chatbot_test():
    try:
        result = call_openai_chat([
            {"role": "user", "content": "Say exactly this: Gemini connection successful"}
        ])
        return jsonify({"status": "ok", "reply": result})
    except Exception as e:
        return jsonify({"status": "error", "error": traceback.format_exc()})

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True, port=5000)
