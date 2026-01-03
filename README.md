# StockerPro: Deep Financial Analytics Platform

StockerPro is a comprehensive personal stock analytics tool built with Next.js 15, FastAPI, and Supabase. It is designed to automatically build a local financial database for stocks you track, enabling deep fundamental analysis.

## 🚀 Key Features

*   **Deep Financial Sync:** Adding a stock triggers an automated background ingestion process. The system fetches the last 4+ years of Income Statements, Balance Sheets, and Cash Flow statements.
*   **Comprehensive Statistics:** Automatically captures TTM (Trailing Twelve Months) metrics, including P/E ratios, Margins, Return on Assets (ROA), Return on Equity (ROE), and Liquidity ratios.
*   **Dividend & Earnings Tracking:** Maintains a full historical record of dividend payments and earnings surprise data for tracked companies.
*   **Secure API Bridge:** Utilizes a Next.js API Bridge to facilitate secure, authenticated communication between the frontend and the Python backend.
*   **Scalable Architecture:** Implements a "Fast Add, Deep Sync" pattern, where the UI responds immediately while heavy data fetching occurs in the background.

---

## 🛠️ Getting Started

### 1. Frontend Setup
The Next.js frontend is managed automatically by the environment.
*   **Port:** 9002
*   **Command:** `npm run dev`

### 2. Backend Setup (Python)
The backend requires a dedicated virtual environment and specific path configurations to handle its service-oriented architecture.

**Automatic Startup (Recommended):**
```bash
bash start-backend.sh
```

**Manual Startup (For Debugging):**
```bash
# 1. Activate Environment (from project root)
source backend/.venv/bin/activate

# 2. Install Dependencies
pip install -r backend/requirements.txt

# 3. Start the Server (Use port 8001 to match the Next.js API Bridge)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```

> [!IMPORTANT]
> The Next.js frontend communicates with the Python backend via a proxy bridge on **port 8001**. If you start the backend on port 8000, you will see `502 Bad Gateway` errors in the browser.

---

## 🧪 Testing

The project includes functional test cases to verify the data ingestion pipeline independently of the UI.

1.  Ensure the backend server is running on port 8001.
2.  Follow the detailed instructions in the **[Functional Testing Guide](docs/test_deep_sync_guide.md)** to execute the `test_deep_sync.py` suite.

---

## 📂 Project Structure

*   `src/app/`: Next.js App Router (Dashboard, Auth, Landing).
*   `src/app/api/proxy/`: The Secure API Bridge implementation.
*   `backend/api/`: FastAPI feature routers (Watchlists, Users, Items).
*   `backend/services/`: Core synchronization and data transformation services.
*   `backend/providers/`: External data source abstractions (yfinance).
*   `docs/`: Detailed technical specifications and manuals.

---

## 🔗 Documentation

*   **[Full Architecture Guide](ARCHITECTURE.md):** Deep dive into the data flow, trust models, and schemas.
*   **[Testing Guide](docs/test_deep_sync_guide.md):** Steps for independent backend verification.
