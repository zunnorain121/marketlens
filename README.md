# 📈 MarketLens — Multi-Market Stock Analysis Dashboard

A web-based stock market dashboard built with **Python Flask + yfinance** for the backend
and **HTML/CSS/JS + Chart.js** for the frontend.

---

## 🗂 Project Structure

```
stock_dashboard/
├── app.py               ← Flask backend (EDA, signals, API routes)
├── requirements.txt     ← Python dependencies
├── templates/
│   └── index.html       ← Frontend dashboard
└── static/              ← (optional: extra CSS/JS files)
```

---

## ⚙️ Setup & Run

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Flask server
```bash
python app.py
```

### 3. Open in browser
```
http://localhost:5000
```

---

## 🔌 API Endpoints

### GET `/api/stock`
Fetch EDA + signal for a single stock.

| Param    | Example   | Description              |
|----------|-----------|--------------------------|
| `ticker` | `AAPL`    | Stock ticker symbol      |
| `period` | `6mo`     | `1mo`, `3mo`, `6mo`, `1y`, `2y` |

**Example:** `http://localhost:5000/api/stock?ticker=AAPL&period=6mo`

---

### GET `/api/compare`
Compare multiple stocks side by side.

| Param     | Example              | Description               |
|-----------|----------------------|---------------------------|
| `tickers` | `AAPL,MSFT,GOOGL`   | Comma-separated tickers   |
| `period`  | `6mo`                | Time period               |

**Example:** `http://localhost:5000/api/compare?tickers=AAPL,MSFT,TSLA`

---

## 📊 Features

- ✅ Real stock data via Yahoo Finance (yfinance)
- ✅ EDA: Mean, Median, Std Dev, Min/Max, Daily Returns
- ✅ Moving Averages (MA20, MA50) with Chart.js visualization
- ✅ RSI (14-period) chart
- ✅ Volume bar chart
- ✅ BUY / HOLD / SELL signal with reasoning
- ✅ Volatility measurement + Risk classification (Low/Medium/High)
- ✅ Multi-stock comparison table
- ✅ Dark-themed, responsive UI

---

## 🇵🇰 Pakistan Stock Exchange Extension

To add PSX stocks in the future, you can use tickers like:
- `HBL.KA` — Habib Bank Limited
- `OGDC.KA` — Oil & Gas Development Company
- `PSO.KA` — Pakistan State Oil

These follow Yahoo Finance's `.KA` suffix for Karachi Stock Exchange.

---

## ⚠️ Disclaimer
This project is for **educational purposes only**. It is not financial advice.
