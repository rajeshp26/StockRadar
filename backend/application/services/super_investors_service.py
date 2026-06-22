# -*- coding: utf-8 -*-
"""
Super Investors Service — 13F Holdings Tracking

Fetches institutional ownership data from SEC 13F filings using edgartools.
Tracks notable value investors ("super investors") and their holdings.

13F filings are filed quarterly by institutional investment managers with $100M+ AUM.
They disclose long equity positions (stocks, not derivatives or shorts).

Key metrics:
  - Current holdings (shares, value, portfolio %)
  - Quarter-over-quarter changes (buys, sells, holds, new positions)
  - Portfolio overlap (how many super investors hold the same stock)
  - Conviction level (position size relative to total portfolio)
"""
from __future__ import annotations

import logging
from shared.time_utils import now_utc
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Notable "Super Investors" — CIK numbers for tracking
# ─────────────────────────────────────────────────────────────────────────────
# 24 super investors - CIKs verified May 2026 (13F-HR only)
# quarters: 4 for high-holding funds (Fundsmith, ARK), 20 for others
# category: lt_compounder, value, growth, activist, sector
SUPER_INVESTORS: Dict[str, Dict[str, str]] = {
    # 🟢 Long-Term Compounders (4)
    "0001067983": {
        "name": "Warren Buffett",
        "firm": "BERKSHIRE HATHAWAY INC",
        "tag": "BUFFETT",
        "style": "Long-Term Compounder",
        "category": "lt_compounder",
        "quarters": 20,
    },
    "0001569205": {
        "name": "Terry Smith",
        "firm": "Fundsmith LLP",
        "tag": "FUNDSMITH",
        "style": "Long-Term Compounder",
        "category": "lt_compounder",
        "quarters": 4,  # High holding count (1500+ ETFs)
    },
    "0001112520": {
        "name": "Chuck Akre",
        "firm": "AKRE CAPITAL MANAGEMENT LLC",
        "tag": "AKRE",
        "style": "Long-Term Compounder",
        "category": "lt_compounder",
        "quarters": 20,
    },
    "0001647251": {
        "name": "Chris H. Zook",
        "firm": "TCI Fund Management Ltd",
        "tag": "TCI",
        "style": "Long-Term Compounder",
        "category": "lt_compounder",
        "quarters": 20,
    },
    # 🔵 Fundamental Value (5)
    "0001061768": {
        "name": "Seth Klarman",
        "firm": "BAUPOST GROUP LLC/MA",
        "tag": "KLARMAN",
        "style": "Value",
        "category": "value",
        "quarters": 20,
    },
    "0001549575": {
        "name": "Mohnish Pabrai",
        "firm": "DALAL STREET LLC",
        "tag": "PABRAI",
        "style": "Value",
        "category": "value",
        "quarters": 20,
    },
    "0001079114": {
        "name": "David Einhorn",
        "firm": "GREENLIGHT CAPITAL INC",
        "tag": "EINHORN",
        "style": "Value",
        "category": "value",
        "quarters": 20,
    },
    "0001510387": {
        "name": "Joel Greenblatt",
        "firm": "Gotham Asset Management, LLC",
        "tag": "GOTHAM",
        "style": "Value",
        "category": "value",
        "quarters": 20,
    },
    "0000949509": {
        "name": "Howard Marks",
        "firm": "OAKTREE CAPITAL MANAGEMENT LP",
        "tag": "OAKTREE",
        "style": "Value",
        "category": "value",
        "quarters": 20,
    },
    # 🔴 Growth / Quality (5)
    "0001167483": {
        "name": "Chase Fisher",
        "firm": "TIGER GLOBAL MANAGEMENT LLC",
        "tag": "TIGER",
        "style": "Growth",
        "category": "growth",
        "quarters": 20,
    },
    "0001135730": {
        "name": "Dan Nguyen",
        "firm": "COATUE MANAGEMENT LLC",
        "tag": "COATUE",
        "style": "Growth",
        "category": "growth",
        "quarters": 20,
    },
    "0001061165": {
        "name": "Stephen Mandel",
        "firm": "LONE PINE CAPITAL LLC",
        "tag": "LONE PINE",
        "style": "Growth",
        "category": "growth",
        "quarters": 20,
    },
    "0001103804": {
        "name": "Andreas Halvorsen",
        "firm": "VIKING GLOBAL INVESTORS LP",
        "tag": "VIKING",
        "style": "Growth",
        "category": "growth",
        "quarters": 20,
    },
    "0001697748": {
        "name": "Cathie Wood",
        "firm": "ARK Investment Management LLC",
        "tag": "ARK",
        "style": "Growth",
        "category": "growth",
        "quarters": 4,  # High holding count
    },
    # 🟣 Activist / Event-Driven (5)
    "0001336528": {
        "name": "Bill Ackman",
        "firm": "Pershing Square Capital Management, L.P.",
        "tag": "ACKMAN",
        "style": "Activist",
        "category": "activist",
        "quarters": 20,
    },
    "0000921669": {
        "name": "Carl Icahn",
        "firm": "ICAHN CARL C",
        "tag": "ICAHN",
        "style": "Activist",
        "category": "activist",
        "quarters": 20,
    },
    "0001040273": {
        "name": "Dan Loeb",
        "firm": "Third Point LLC",
        "tag": "LOEB",
        "style": "Activist",
        "category": "activist",
        "quarters": 20,
    },
    "0001791786": {
        "name": "Paul Singer",
        "firm": "Elliott Investment Management L.P.",
        "tag": "ELLIOTT",
        "style": "Activist",
        "category": "activist",
        "quarters": 20,
    },
    "0001418814": {
        "name": "Mason Morfit / ValueAct",
        "firm": "VALUEACT HOLDINGS, L.P.",
        "tag": "VALUEACT",
        "style": "Activist",
        "category": "activist",
        "quarters": 20,
    },
    # 🟠 Sector Specialists (5)
    "0000934639": {
        "name": "Lee Freeman",
        "firm": "MAVERICK CAPITAL LTD",
        "tag": "MAVERICK",
        "style": "Sector",
        "category": "sector",
        "quarters": 20,
    },
    "0001263508": {
        "name": "Luke Byrne",
        "firm": "BAKER BROS. ADVISORS LP",
        "tag": "BAKER BROS",
        "style": "Sector",
        "category": "sector",
        "quarters": 20,
    },
    "0001656456": {
        "name": "David Tepper",
        "firm": "Appaloosa LP",
        "tag": "TEPPER",
        "style": "Sector",
        "category": "sector",
        "quarters": 20,
    },
    "0001553733": {
        "name": "Paul B. Kaplan",
        "firm": "Brave Warrior Advisors LLC",
        "tag": "BRAVE WARRIOR",
        "style": "Sector",
        "category": "sector",
        "quarters": 20,
    },
    "0000813917": {
        "name": "Bill Nygren",
        "firm": "HARRIS ASSOCIATES LP",
        "tag": "HARRIS",
        "style": "Sector",
        "category": "sector",
        "quarters": 20,
    },
}


class SuperInvestorsService:
    """
    Fetches and analyzes institutional holdings from 13F filings.

    Uses edgartools to:
      1. Get latest 13F-HR filings for tracked investors
      2. Parse holdings (ticker, shares, value, portfolio %)
      3. Compare quarter-over-quarter to detect buys/sells
      4. Aggregate by stock to show who owns what
    """

    def __init__(self):
        from database import supabase
        self.supabase = supabase
        self._ensure_edgar_identity()

    @staticmethod
    def _ensure_edgar_identity() -> None:
        """Set SEC identity if not already configured."""
        try:
            from edgar import set_identity  # noqa: PLC0415
            from config import settings  # noqa: PLC0415

            identity = getattr(settings, "EDGAR_IDENTITY", "stockerpro@example.com")
            set_identity(identity)
        except ImportError:
            logger.warning(
                "edgartools not installed — super investors feature unavailable"
            )
        except Exception as e:
            logger.debug("set_identity warning (non-fatal): %s", e)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def get_super_investor_holdings(
        self, ticker_symbol: str, limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get super investor holdings for a stock.

        Returns:
            {
                "ticker": "NOW",
                "holders": [
                    {
                        "investor_name": "Warren Buffett",
                        "firm": "Berkshire Hathaway Inc.",
                        "tag": "BUFFETT",
                        "style": "Value / Quality",
                        "shares": 1234567,
                        "value": 127000000,
                        "portfolio_weight": 0.023,  # 2.3% of their portfolio
                        "change_pct": 15.2,  # +15.2% from last quarter
                        "change_type": "increased",  # new | increased | decreased | held | sold
                        "quarter_date": "2024-12-31",
                    },
                    ...
                ],
                "overlap_count": 3,  # 3 super investors hold this stock
                "avg_portfolio_weight": 0.018,  # 1.8% average weight
                "conviction_level": "moderate",  # low | moderate | high | very_high
                "recent_activity": {
                    "buyers": [...],
                    "sellers": [...],
                },
            }
        """
        try:
            from edgar import get_filings  # noqa: PLC0415

            ticker = ticker_symbol.upper()
            holders: List[Dict[str, Any]] = []

            # Fetch latest 13F for each super investor
            for cik, investor_info in SUPER_INVESTORS.items():
                try:
                    logger.info(f"[DEBUG] {investor_info['name']}: Fetching 13F filings for CIK {cik}")
                    filings = get_filings(form="13F-HR").filter(cik=cik)
                    if not filings or len(filings) == 0:
                        logger.warning(f"[DEBUG] {investor_info['name']}: No 13F filings found")
                        continue

                    logger.info(f"[DEBUG] {investor_info['name']}: Found {len(filings)} filings")

                    current_filing = filings[0].obj()
                    current_holdings = current_filing.holdings

                    # Raw data logging for debugging SEC response
                    logger.info(f"[DEBUG] {investor_info['name']}: Raw filings count: {len(filings)}")
                    logger.info(f"[DEBUG] {investor_info['name']}: Holdings DataFrame shape: {current_holdings.shape}")
                    logger.info(f"[DEBUG] {investor_info['name']}: Holdings columns: {list(current_holdings.columns)}")

                    # Sample of holdings data (first 3 rows - limited to avoid huge logs)
                    if not current_holdings.empty:
                        sample = current_holdings.head(3)
                        for idx, row in sample.iterrows():
                            logger.info(f"[DEBUG] {investor_info['name']}: Sample row - Cusip: {row.get('Cusip', 'N/A')}, Issuer: {row.get('Issuer', 'N/A')}, Class: {row.get('Class', 'N/A')}, Value: {row.get('Value', 'N/A')}")

                    logger.info(f"[DEBUG] {investor_info['name']}: Filing period: {current_filing.report_period}")

                    # Find this stock in their holdings
                    stock_holding = self._find_holding(current_holdings, ticker)
                    if not stock_holding:
                        logger.warning(f"[DEBUG] {investor_info['name']}: Stock {ticker} NOT found in holdings")
                        continue

                    logger.info(f"[DEBUG] {investor_info['name']}: Stock {ticker} FOUND - shares: {stock_holding.get('shares')}")

                    # Get previous quarter for comparison
                    prev_holding = None
                    if len(filings) > 1:
                        prev_filing = filings[1].obj()
                        prev_holding = self._find_holding(prev_filing.holdings, ticker)

                    # Calculate changes
                    change_pct, change_type = self._calculate_change(
                        stock_holding, prev_holding
                    )

                    holders.append({
                        "investor_name": investor_info["name"],
                        "firm": investor_info["firm"],
                        "tag": investor_info["tag"],
                        "style": investor_info["style"],
                        "shares": int(stock_holding.get("shares", 0)),
                        "value": float(stock_holding.get("value", 0)),
                        "portfolio_weight": float(
                            stock_holding.get("portfolio_weight", 0)
                        ),
                        "change_pct": change_pct,
                        "change_type": change_type,
                        "quarter_date": str(current_filing.report_period),
                    })

                except Exception as e:
                    logger.error(
                        "Failed to fetch 13F for %s (%s): %s",
                        investor_info["name"],
                        cik,
                        e,
                    )

            # Sort by portfolio weight descending (conviction)
            holders.sort(key=lambda x: x["portfolio_weight"], reverse=True)
            holders = holders[:limit]

            # Aggregate metrics
            overlap_count = len(holders)
            avg_weight = (
                sum(h["portfolio_weight"] for h in holders) / overlap_count
                if overlap_count > 0
                else 0
            )
            conviction = self._classify_conviction(avg_weight)

            # Split into buyers/sellers
            buyers = [h for h in holders if h["change_type"] in ("new", "increased")]
            sellers = [h for h in holders if h["change_type"] in ("decreased", "sold")]

            # Save to database
            if overlap_count > 0 and holders:
                quarter_date = holders[0].get("quarter_date", "")
                filing_date = str(now_utc().date())
                self._save_holdings_to_db(ticker, holders, quarter_date, filing_date)

            return {
                "ticker": ticker,
                "holders": holders,
                "overlap_count": overlap_count,
                "avg_portfolio_weight": round(avg_weight, 4),
                "conviction_level": conviction,
                "recent_activity": {
                    "buyers": buyers[:5],  # Top 5 buyers
                    "sellers": sellers[:5],  # Top 5 sellers
                },
            }

        except ImportError:
            logger.error("edgartools not installed — cannot fetch 13F data")
            return self._empty_response(ticker_symbol)
        except Exception as e:
            logger.error("Failed to fetch super investor data for %s: %s", ticker_symbol, e)
            return self._empty_response(ticker_symbol)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_holding(holdings_df: pd.DataFrame, ticker: str) -> Optional[Dict[str, Any]]:
        """Find a stock in a 13F holdings DataFrame."""
        if holdings_df is None or holdings_df.empty:
            return None

        # edgartools 13F holdings columns: Issuer, Class, Cusip, Ticker, SharesPrnAmount, Value
        # Filter by ticker (matching Ticker column or Class contains ticker)
        logger.info(f"[DEBUG] _find_holding: Checking columns: {list(holdings_df.columns)}")

        match = holdings_df[
            (holdings_df["Ticker"].str.upper() == ticker.upper())
            | (holdings_df["Class"].str.contains(ticker, case=False, na=False))
            | (holdings_df["Issuer"].str.contains(ticker, case=False, na=False))
        ]

        if match.empty:
            logger.warning(f"[DEBUG] _find_holding: No match for '{ticker}' in holdings")
            return None

        logger.info(f"[DEBUG] _find_holding: MATCH FOUND for '{ticker}' - {len(match)} row(s)")

        row = match.iloc[0]
        
        # Get total portfolio value to calculate weight
        total_value = holdings_df["Value"].sum()
        holding_value = float(row.get("Value", 0))
        portfolio_weight = (holding_value / total_value) if total_value > 0 else 0.0
        
        return {
            "shares": int(row.get("SharesPrnAmount", 0)),
            "value": float(row.get("Value", 0)),  
            "portfolio_weight": portfolio_weight,
        }

    @staticmethod
    def _calculate_change(
        current: Optional[Dict], previous: Optional[Dict]
    ) -> tuple[float, str]:
        """
        Calculate quarter-over-quarter change.

        Returns: (change_pct, change_type)
          change_type: "new" | "increased" | "decreased" | "held" | "sold"
        """
        if current is None:
            return (0.0, "none")

        if previous is None:
            return (0.0, "new")

        curr_shares = current.get("shares", 0)
        prev_shares = previous.get("shares", 0)

        if curr_shares == 0:
            return (-100.0, "sold")

        if prev_shares == 0:
            return (0.0, "new")

        change_pct = ((curr_shares - prev_shares) / prev_shares) * 100

        if abs(change_pct) < 1.0:
            return (change_pct, "held")
        elif change_pct > 0:
            return (change_pct, "increased")
        else:
            return (change_pct, "decreased")

    @staticmethod
    def _classify_conviction(avg_portfolio_weight: float) -> str:
        """
        Classify conviction level based on average portfolio weight.

        Typical portfolio construction:
          <0.5%  = filler / small position
          0.5-2% = standard position
          2-5%   = high conviction
          >5%    = very high conviction (concentrated bet)
        """
        if avg_portfolio_weight >= 0.05:
            return "very_high"
        elif avg_portfolio_weight >= 0.02:
            return "high"
        elif avg_portfolio_weight >= 0.005:
            return "moderate"
        else:
            return "low"

    @staticmethod
    def _empty_response(ticker: str) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "holders": [],
            "overlap_count": 0,
            "avg_portfolio_weight": 0.0,
            "conviction_level": "none",
            "recent_activity": {"buyers": [], "sellers": []},
        }

    # ─────────────────────────────────────────────────────────────────────────────
    # Database Operations
    # ─────────────────────────────────────────────────────────────────────────────

    def _get_or_create_investor(self, cik: str, investor_info: Dict[str, str]) -> Optional[int]:
        """Get investor_id from DB, or create if doesn't exist."""
        try:
            # Check if exists
            result = self.supabase.table("institutional_investors").select(
                "investor_id"
            ).eq("cik", cik).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]["investor_id"]
            
            # Create new investor
            insert_data = {
                "cik": cik,
                "investor_name": investor_info["name"],
                "firm_name": investor_info["firm"],
                "investor_tag": investor_info["tag"],
                "investment_style": investor_info.get("style", ""),
                "is_super_investor": True,
            }
            
            insert_result = self.supabase.table(
                "institutional_investors"
            ).insert(insert_data).execute()
            
            if insert_result.data and len(insert_result.data) > 0:
                logger.info(f"[DEBUG] Created investor: {investor_info['name']}")
                return insert_result.data[0]["investor_id"]
            
            return None
            
        except Exception as e:
            logger.error(f"[DEBUG] Error creating investor {cik}: {e}")
            return None

    def _get_company_id(self, ticker: str) -> Optional[int]:
        """Get company_id from companies table."""
        try:
            result = self.supabase.table("companies").select(
                "company_id"
            ).eq("ticker_symbol", ticker.upper()).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]["company_id"]
            
            return None
            
        except Exception as e:
            logger.error(f"[DEBUG] Error getting company_id for {ticker}: {e}")
            return None

    def _save_holdings_to_db(
        self,
        ticker: str,
        holders: List[Dict[str, Any]],
        quarter_date: str,
        filing_date: str,
    ) -> None:
        """Save holdings to institutional_holdings table."""
        try:
            company_id = self._get_company_id(ticker)
            if not company_id:
                logger.warning(f"[DEBUG] Cannot save holdings - company_id not found for {ticker}")
                return
            
            for holder in holders:
                # Get or create investor
                cik = None
                for cik_num, info in SUPER_INVESTORS.items():
                    if info["name"] == holder["investor_name"]:
                        cik = cik_num
                        break
                
                if not cik:
                    continue
                
                investor_id = self._get_or_create_investor(cik, {"name": holder["investor_name"], "firm": holder["firm"], "tag": holder["tag"], "style": holder.get("style", "")})
                if not investor_id:
                    continue
                
                # Check if holding already exists for this quarter
                existing = self.supabase.table("institutional_holdings").select(
                    "holding_id"
                ).eq("investor_id", investor_id).eq(
                    "company_id", company_id
                ).eq("quarter_end_date", quarter_date).execute()
                
                insert_data = {
                    "investor_id": investor_id,
                    "company_id": company_id,
                    "quarter_end_date": quarter_date,
                    "filing_date": filing_date,
                    "shares_held": holder["shares"],
                    "position_value": holder["value"],
                    "portfolio_weight": holder["portfolio_weight"],
                    "shares_change": int(holder.get("change_pct", 0) * holder["shares"] / 100) if holder.get("change_pct") and holder["shares"] else None,
                    "shares_change_pct": holder.get("change_pct", 0),
                    "change_type": holder.get("change_type", "held"),
                    "data_source": "edgar",
                }
                
                if existing.data and len(existing.data) > 0:
                    # Update existing
                    self.supabase.table("institutional_holdings").update(insert_data).eq(
                        "holding_id", existing.data[0]["holding_id"]
                    ).execute()
                    logger.info(f"[DEBUG] Updated holding: {holder['investor_name']} - {ticker}")
                else:
                    # Insert new
                    self.supabase.table("institutional_holdings").insert(insert_data).execute()
                    logger.info(f"[DEBUG] Inserted holding: {holder['investor_name']} - {ticker}")
                    
        except Exception as e:
            logger.error(f"[DEBUG] Error saving holdings to DB: {e}")