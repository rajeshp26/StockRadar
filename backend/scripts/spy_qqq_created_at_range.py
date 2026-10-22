# spy_qqq_created_at_range.py
# READ-ONLY. min/max created_at for SPY (61) and QQQ (379) price rows --
# were all 2,512 rows of each loaded in the 2026-10-01 bulk seed?
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402

ph = supabase.table("price_history")
for cid, tk in ((61, "SPY"), (379, "QQQ")):
    n = (ph.select("price_date", count="exact")
         .eq("company_id", cid).execute()).count
    lo = (ph.select("created_at").eq("company_id", cid)
          .order("created_at").limit(1).execute().data or [])
    hi = (ph.select("created_at").eq("company_id", cid)
          .order("created_at", desc=True).limit(1).execute().data or [])
    print(f"{tk}: rows={n}  "
          f"created_at min={lo[0]['created_at'][:19] if lo else '-'}  "
          f"max={hi[0]['created_at'][:19] if hi else '-'}")
