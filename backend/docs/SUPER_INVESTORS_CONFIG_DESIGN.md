# Super Investors — Configurable Architecture Design v3

## 1. Current Architecture (Analysis)

### 1.1 Data Source

All super investor definitions are **hardcoded** in a Python dictionary in
`backend/application/services/super_investors_service.py:34`:

```python
SUPER_INVESTORS: Dict[str, Dict[str, str]] = {
    "0001067983": {
        "name": "Warren Buffett",
        "firm": "BERKSHIRE HATHAWAY INC",
        "tag": "BUFFETT",
        "style": "Long-Term Compounder",    # display name → DB column `investment_style`
        "category": "lt_compounder",        # URL filter slug
        "quarters": 20,                     # quarters of history to fetch
    },
    # ... 23 more entries
}
```

A **second** hardcoded dict exists in `backend/scripts/validate_ciks.py:13` for CIK
validation against SEC EDGAR, with a different structure:

```python
INVESTORS = {
    "0001067983": ("Warren Buffett", "Berkshire Hathaway", ["13F-HR"]),
    # ...
}
```

### 1.2 Flow: Category Slug → Filter Query

The frontend sends a category slug via query param, which the backend maps to a
DB `investment_style` value:

```
Frontend (page.tsx)              Backend API (super_investors.py)
┌─────────────────────┐          ┌──────────────────────────────────┐
│ STYLES = [           │          │ style_map = {                   │
│   "value",           │  ──GET──→│   "value": "Value",             │
│   "lt_compounder",   │  ?style= │   "lt_compounder":              │
│   "growth",          │  value   │     "Long-Term Compounder",     │
│   "activist",        │          │   "growth": "Growth",           │
│   "sector",          │          │   "activist": "Activist",       │
│ ]                    │          │   "sector": "Sector",           │
│ STYLE_LABELS = {     │          │ }                                │
│   value: "Value",    │          └──────────┬───────────────────────┘
│   lt_compounder:     │                     │
│     "Compounders",   │                     ▼
│   growth: "Growth",  │          DB: WHERE investment_style = "Value"
│   ...                │
│ }                    │
└─────────────────────┘
```

### 1.3 All Touch Points (Current)

| # | Layer | File | Lines | What it does |
|---|-------|------|-------|-------------|
| 1 | **Source data** | `backend/application/services/super_investors_service.py` | 34–232 | `SUPER_INVESTORS` dict — canonical list |
| 2 | **Service** | same file | 311, 597–599 | Iterates dict to fetch 13F data |
| 3 | **Scheduler** | `backend/application/schedulers/super_investors_scheduler.py` | 74 | Iterates dict to plan refresh jobs |
| 4 | **API router** | `backend/api/super_investors.py` | 369–375 | Hardcoded `style_map` for category→style mapping |
| 5 | **CIK validator** | `backend/scripts/validate_ciks.py` | 13–38 | Duplicate hardcoded `INVESTORS` dict |
| 6 | **Backfill script** | `backend/scripts/backfill_super_investors.py` | 22, 288 | Imports `SUPER_INVESTORS` |
| 7 | **Frontend types** | `web/.../super-investors-page.types.ts` | 9–14 | `InvestorStyle` union type |
| 8 | **Frontend filters** | `web/.../page.tsx` | 330–334 | Hardcoded `STYLES` + `STYLE_LABELS` arrays |
| 9 | **Tests** | `backend/tests/test_scheduler_plan_methods.py` | 22–39 | Mocks `SUPER_INVESTORS` |

### 1.4 Constraints & Gaps

1. **Adding an investor = 6+ file changes** (dict + CIK validation + style_map +
   frontend type + frontend filter arrays + possibly tests).
2. **Duplicate source of truth** — `INVESTORS` in `validate_ciks.py` drifts from
   `SUPER_INVESTORS` (different names, CIKs, missing entries).
3. **style vs category duality** — DB stores `style` (display name), URL uses
   `category` (slug). Must be kept in sync manually.
4. **No `CREATE TABLE` in repo** — `institutional_investors.investment_style` is
   a free-text `varchar` with no CHECK constraint. No mechanism prevents drift
   between config values and DB values.
5. **Tests mock the live dict** — `test_scheduler_plan_methods.py` patches
   `mod.SUPER_INVESTORS` directly, coupling tests to module internals.

---

## 2. Proposal: Config-Driven Super Investors

### 2.1 Design Goals

1. **Zero code changes to add/remove investors** — Edit one JSON file, restart
   (or call reload endpoint).
2. **Single source of truth** — One config file drives backend, scheduler, API
   filters, CIK validation, and informs the frontend.
3. **Dynamic frontend filters** — Available styles/categories fetched from API,
   not hardcoded. TypeScript codegen preserves compile-time safety for slugs.
4. **Backward compatible** — Existing DB schema unchanged. Existing API response
   shapes unchanged. Migration is incremental and reversible.
5. **Enforceable** — Config validation catches errors at load. DB ingestion
   always writes `investment_style` from the config, never free-form.

### 2.2 Non-Goals

- **Editing config without restart**: Out of scope for v1. An admin reload
  endpoint exists, but config changes require either a restart or explicit
  reload call. In-flight scheduler jobs use the config that was active when
  they started.
- **DB FK constraint**: `investment_style` stays as free-text `varchar`.
  The config will be the single source of truth; the DB follows what the
  config writes. An FK constraint can be added later as a migration.
- **GUI for editing config**: The config is a checked-in JSON file, versioned
  alongside the codebase.

### 2.3 Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Malformed JSON crashes startup | Low (committed file) | CI schema validation + eager Python validation with clear error messages |
| Config and DB drift | Medium | Ingestion always resolves `style` from config; no other path sets `investment_style`. Migration substep 4a normalizes existing rows. |
| CIK becomes invalid (firm stops filing) | Low | `active: false` flag for soft-disable; CIK validation runs in CI on config changes |
| Frontend stale if API styles change without codegen update | Low | Codegen runs in CI; generated file must match checked-in version (`git diff --exit-code`) |

### 2.4 Config File Format

Rich object form for `style_categories` — extensible without future breaking
changes.

```jsonc
{
  "$schema": "./super_investors.schema.json",
  "version": 1,
  "style_categories": {
    "lt_compounder": {
      "label": "Long-Term Compounder",
      "short_label": "Compounders",
      "sort_order": 1,
      "description": "Patient, buy-and-hold investors focused on durable business quality"
    },
    "value": {
      "label": "Value",
      "short_label": "Value",
      "sort_order": 2,
      "description": "Margin-of-safety investors seeking undervalued securities"
    },
    "growth": {
      "label": "Growth",
      "short_label": "Growth",
      "sort_order": 3,
      "description": "Quality growth investors backing scalable business models"
    },
    "activist": {
      "label": "Activist",
      "short_label": "Activist",
      "sort_order": 4,
      "description": "Event-driven investors pushing for corporate change"
    },
    "sector": {
      "label": "Sector",
      "short_label": "Sector",
      "sort_order": 5,
      "description": "Deep domain specialists targeting specific industries"
    },
    "venture_contrarian": {
      "label": "Venture / Contrarian",
      "short_label": "Venture",
      "sort_order": 6,
      "description": "Early-stage VC mentality with contrarian public market bets"
    }
  },
  "investors": [
    {
      "cik": "0001067983",
      "name": "Warren Buffett",
      "firm": "BERKSHIRE HATHAWAY INC",
      "tag": "BUFFETT",
      "style_category": "lt_compounder",
      "quarters": 20,
      "active": true
    },
    // ... existing 23 investors ...
    {
      "cik": "0001211060",
      "name": "Peter Thiel",
      "firm": "FOUNDERS FUND MANAGEMENT LLC",
      "tag": "THIEL",
      "style_category": "venture_contrarian",
      "quarters": 4,
      "active": true
    }
  ]
}
```

**Design decisions:**
- `style_categories` is an **object** keyed by slug for fast O(1) lookup. The
  API returns an **array** for guaranteed ordering.
- `investors` is an **array** — explicit ordering, no key name collisions.
- `quarters` defaults to 20 if omitted (backward compatible).
- `active` defaults to `true` if omitted.
- `tag` must match `^[A-Z][A-Z_]*$` (validated at load).
- `version` bumps when the **set of style category slugs changes** (add/remove
  categories) or when the **config schema structure changes** (field
  addition/removal). It does not bump for content edits within existing
  categories (label text, description) or for adding/removing individual
  investors under existing categories. The frontend can use the version
  in the `/super-investors/styles` response for cache invalidation.

### 2.5 The `"venture_contrarian"` Mapping

| Concept | Value | Where used |
|---------|-------|------------|
| Config key (slug) | `"venture_contrarian"` | JSON key in `style_categories`, referenced by investor entries |
| `label` (DB display) | `"Venture / Contrarian"` | Stored in `investment_style` column, returned in API responses |
| `short_label` (UI) | `"Venture"` | Frontend filter chip text |
| URL query param | `?style=venture_contrarian` | Passed from frontend to backend API |

The slug uses underscores (not slashes) because it appears in URL query params.
The display label uses a space-padded slash — fine for DB storage and JSON
responses.

### 2.6 JSON Schema (`backend/config/super_investors.schema.json`)

Validates structure and format. Cross-key referential integrity (e.g.,
`style_category` exists in `style_categories`) is handled by the Python loader,
not JSON Schema.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["version", "style_categories", "investors"],
  "properties": {
    "version": { "type": "integer", "minimum": 1 },
    "style_categories": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": {
        "type": "object",
        "required": ["label", "sort_order"],  # short_label defaults to label if omitted
        "properties": {
          "label":       { "type": "string", "minLength": 1 },
          "short_label": { "type": "string", "minLength": 1 },
          "sort_order":  { "type": "integer", "minimum": 1 },
          "description": { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "investors": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["cik", "name", "firm", "tag", "style_category"],
        "properties": {
          "cik":            { "type": "string", "pattern": "^\\d{10}$" },
          "name":           { "type": "string", "minLength": 1 },
          "firm":           { "type": "string", "minLength": 1 },
          "tag":            { "type": "string", "pattern": "^[A-Z][A-Z_]*$" },
          "style_category": { "type": "string", "minLength": 1 },
          "quarters":       { "type": "integer", "minimum": 1, "maximum": 40 },
          "active":         { "type": "boolean" }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

### 2.7 Backend Loader

New module. Uses `functools.lru_cache` for thread-safe lazy singleton — no
explicit globals or locks.

```python
# backend/application/services/super_investors_loader.py

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"^[A-Z][A-Z_]*$")  # e.g. BUFFETT, TIGER_CUB

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StyleCategory:
    slug: str
    label: str
    short_label: str
    sort_order: int
    description: str = ""


@dataclass(frozen=True)
class InvestorEntry:
    cik: str
    name: str
    firm: str
    tag: str
    style_category: str
    quarters: int = 20
    active: bool = True


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "super_investors.json"
)


class SuperInvestorsConfig:
    """Loads and validates super investor definitions from a JSON config file."""

    def __init__(self, path: Path | str = _DEFAULT_CONFIG_PATH) -> None:
        self._source_path: str = str(path)

        with open(path) as f:
            raw: Dict[str, Any] = json.load(f)

        self.version: int = raw["version"]

        # Parse style categories
        self.style_categories: Dict[str, StyleCategory] = {
            slug: StyleCategory(
                slug=slug,
                label=meta["label"],
                short_label=meta.get("short_label", meta["label"]),
                sort_order=meta.get("sort_order", 100),
                description=meta.get("description", ""),
            )
            for slug, meta in raw["style_categories"].items()
        }

        # Parse investors
        self.investors: List[InvestorEntry] = [
            InvestorEntry(
                cik=inv["cik"],
                name=inv["name"],
                firm=inv["firm"],
                tag=inv["tag"],
                style_category=inv["style_category"],
                quarters=inv.get("quarters", 20),
                active=inv.get("active", True),
            )
            for inv in raw["investors"]
        ]

        # Validate before building derived views
        self._validate()

        # CIK-keyed dict (same shape as current SUPER_INVESTORS)
        # Only includes active investors.
        self.by_cik: Dict[str, Dict[str, Any]] = {
            inv.cik: {
                "name": inv.name,
                "firm": inv.firm,
                "tag": inv.tag,
                "style": self.style_categories[inv.style_category].label,
                "category": inv.style_category,
                "quarters": inv.quarters,
            }
            for inv in self.investors
            if inv.active
        }

        logger.info(
            "Loaded %d super investors, %d style categories from %s (v%d)",
            len([i for i in self.investors if i.active]),
            len(self.style_categories),
            self._source_path,
            self.version,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        """Eager — fails at load time with actionable error messages."""
        errors: List[str] = []
        seen_ciks: set[str] = set()
        seen_tags: set[str] = set()
        seen_sort_orders: set[int] = set()

        for inv in self.investors:
            # CIK format
            if not inv.cik.isdigit() or len(inv.cik) != 10:
                errors.append(
                    f"[{inv.cik}] CIK must be a 10-digit zero-padded string"
                )
            if inv.cik in seen_ciks:
                errors.append(f"[{inv.cik}] Duplicate CIK")
            seen_ciks.add(inv.cik)

            # Tag format + uniqueness
            if not _TAG_RE.match(inv.tag):
                errors.append(
                    f"[{inv.cik}] tag must match {_TAG_RE.pattern!r}, "
                    f"got {inv.tag!r}"
                )
            if inv.tag in seen_tags:
                errors.append(
                    f"[{inv.cik}] Duplicate tag {inv.tag!r} (used in URL paths)"
                )
            seen_tags.add(inv.tag)

            # Style category reference
            if inv.style_category not in self.style_categories:
                valid = sorted(self.style_categories.keys())
                errors.append(
                    f"[{inv.cik}] Unknown style_category {inv.style_category!r}. "
                    f"Valid: {valid}"
                )

            # Quarters range (40 = ~10 years of 13F data, operational limit)
            if not (1 <= inv.quarters <= 40):
                errors.append(
                    f"[{inv.cik}] quarters={inv.quarters} out of range 1–40"
                )

        # Style category sort order uniqueness
        for cat in self.style_categories.values():
            if cat.sort_order in seen_sort_orders:
                errors.append(
                    f"Duplicate sort_order {cat.sort_order} in style_categories "
                    f"(slug: {cat.slug})"
                )
            seen_sort_orders.add(cat.sort_order)

        if errors:
            raise ValueError(
                f"super_investors.json has {len(errors)} validation error(s):\n"
                + "\n".join(f"  • {e}" for e in errors)
            )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get_style_label(self, slug: str) -> Optional[str]:
        """Resolve a category slug to its display label."""
        cat = self.style_categories.get(slug)
        return cat.label if cat else None

    def get_sorted_styles(self) -> List[StyleCategory]:
        """Return all style categories sorted by sort_order (for API)."""
        return sorted(self.style_categories.values(), key=lambda c: c.sort_order)


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_config() -> SuperInvestorsConfig:
    """Return the singleton config, loading on first call (lazy, thread-safe)."""
    path = os.environ.get(
        "SUPER_INVESTORS_CONFIG_PATH",
        str(_DEFAULT_CONFIG_PATH),
    )
    return SuperInvestorsConfig(path)


def reset_config() -> None:
    """Reset singleton. Use in tests or after config reload."""
    get_config.cache_clear()


def reload_config() -> SuperInvestorsConfig:
    """
    Force a config reload after file change.

    All consumers use the fresh config on next access (the bridge shim
    uses module-level `__getattr__` which is evaluated dynamically).

    In-flight scheduler jobs continue with the config that was active
    when they were planned.
    """
    reset_config()
    return get_config()
```

**Design decisions:**
- `@lru_cache(maxsize=1)` — thread-safe, no explicit globals or locks.
- Immutable `@dataclass(frozen=True)` domain objects — no mutation bugs.
- `by_cik` computed eagerly in `__init__` — it's always needed and cheap
  (25 entries). No `None` sentinel, no memoization complexity.
- `_validate()` runs in `__init__`, catches: CIK format, CIK uniqueness,
  tag format + uniqueness, style category references, quarters range,
  sort order uniqueness.
- Config path via `SUPER_INVESTORS_CONFIG_PATH` env var or project-relative
  default. This should be added to the `Settings` class in `config.py` as
  `SUPER_INVESTORS_CONFIG_PATH: str = Field(default="")` (empty = use
  default path), consistent with existing project conventions.

### 2.8 Integration: Backend

#### `super_investors_service.py` — Expose a function, not a module-level dict

```python
# Before:
SUPER_INVESTORS: Dict[str, Dict[str, str]] = { ... }

# After:
def get_super_investors() -> Dict[str, Dict[str, Any]]:
    """Return active super investors keyed by CIK (from config)."""
    return get_config().by_cik
```

Consumers update from:

```python
from application.services.super_investors_service import SUPER_INVESTORS
# ... SUPER_INVESTORS[cik] ...

# To:
from application.services.super_investors_service import get_super_investors
# ... get_super_investors()[cik] ...
```

The function is called on each access, so `reload_config()` takes effect
immediately — unlike a module-level variable that captures the dict once.

**Backward compatibility shim** (temporary, for migration) — uses Python's
module-level `__getattr__` (PEP 562, Python 3.7+) so `from module import
SUPER_INVESTORS` and `module.SUPER_INVESTORS` work dynamically without
capturing at import time:

```python
# Bridge — remove after all consumers are migrated (step 12).
def __getattr__(name: str):
    if name == "SUPER_INVESTORS":
        return get_super_investors()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

This keeps existing imports working during the transition without the
import-time capture bug. Remove when step 12 is complete.

**Note**: Module `__getattr__` is not invoked for `from module import *`.
If any consumer uses star imports, add `SUPER_INVESTORS` to `__all__` or
migrate that consumer directly. Run
`grep -r "from application.services.super_investors_service import \*"`
to verify none exist.

#### Scheduler + backfill — minimal change

```python
# super_investors_scheduler.py:74 — before:
for cik, info in SUPER_INVESTORS.items():
# after:
for cik, info in get_super_investors().items():
```

```python
# backfill_super_investors.py — before:
from application.services.super_investors_service import SUPER_INVESTORS
# after — same import still works via the bridge shim
from application.services.super_investors_service import SUPER_INVESTORS
# TODO: migrate to get_super_investors() after bridge removal
```

#### `super_investors.py` (API router) — Remove hardcoded `style_map`

The `style_map` currently lives in two places:
- `get_top_stocks()` at line 369 (and again at 1075 for the sectors endpoint)

Both are replaced with the config-based resolution via FastAPI `Depends`:

```python
from fastapi import Depends

# Location: backend/api/dependencies.py
from application.services.super_investors_loader import (
    SuperInvestorsConfig,
    get_config,
)

def get_si_config() -> SuperInvestorsConfig:
    """FastAPI dependency for SuperInvestorsConfig injection."""
    return get_config()

# Convention:
#   API routes    → Depends(get_si_config)
#   Background    → get_config() directly
#   jobs/scripts  → (both read the same singleton)

@router.get("/super-investors/top-stocks")
async def get_top_stocks(
    style: Optional[str] = Query(None),
    cfg: SuperInvestorsConfig = Depends(get_si_config),
    ...
):
    style_label = cfg.get_style_label(style.lower()) if style else None
    ...
```

#### `validate_ciks.py` — Derive from config instead of duplicating

```python
# Before (hardcoded):
INVESTORS = {
    "0001067983": ("Warren Buffett", "Berkshire Hathaway", ["13F-HR"]),
    # ...
}

# After: wrap in a function so the module can be imported without
# immediately loading config (important for testability).
from application.services.super_investors_loader import get_config

def build_investors_from_config() -> dict:
    cfg = get_config()
    return {
        inv.cik: (inv.name, inv.firm, ["13F-HR"])
        for inv in cfg.investors
        if inv.active
    }

# Module-level assignment is intentional — this is a CLI script.
INVESTORS = build_investors_from_config()
```

Note: includes only **active** investors for file validation. Inactive CIKs
still appear in `cfg.investors` and can be validated if needed by passing
`active=False` to the validation function — but the default is active-only.

#### Close the DB drift loop

During 13F ingestion (both scheduler and backfill), `investment_style` is
always resolved via the config:

```python
# _get_or_create_investor() / backfill:
style = get_config().get_style_label(inv_info["category"]) or ""
insert_data = {
    ...
    "investment_style": style,  # always from config, never free-form
    ...
}
```

**Migration substep**: Before the cutover to config-based reads, run a
one-time SQL `UPDATE` that normalizes existing `investment_style` values
to match config labels:

```sql
-- Example: fix any 'Long Term Compounder' → 'Long-Term Compounder'
-- (dry-run first, then execute)
UPDATE institutional_investors
SET investment_style = 'Long-Term Compounder'
WHERE investment_style ILIKE '%Long Term%Compounder%';
```

This eliminates the drift window between step 4 (read from config) and
step 7 (write from config).

#### New API endpoint: `GET /super-investors/styles`

Returns styles as an **ordered array** (not object) for deterministic frontend
rendering:

```python
@router.get("/super-investors/styles")
def list_styles(cfg: SuperInvestorsConfig = Depends(get_si_config)):
    return {
        "version": cfg.version,
        "styles": [
            {
                "slug": cat.slug,
                "label": cat.label,
                "short_label": cat.short_label,
                "sort_order": cat.sort_order,
            }
            for cat in cfg.get_sorted_styles()
        ],
    }
```

Response:

```json
{
  "version": 1,
  "styles": [
    { "slug": "lt_compounder",      "label": "Long-Term Compounder",  "short_label": "Compounders", "sort_order": 1 },
    { "slug": "value",              "label": "Value",                 "short_label": "Value",       "sort_order": 2 },
    { "slug": "growth",             "label": "Growth",                "short_label": "Growth",      "sort_order": 3 },
    { "slug": "activist",           "label": "Activist",              "short_label": "Activist",    "sort_order": 4 },
    { "slug": "sector",             "label": "Sector",                "short_label": "Sector",      "sort_order": 5 },
    { "slug": "venture_contrarian", "label": "Venture / Contrarian",  "short_label": "Venture",     "sort_order": 6 }
  ]
}
```

Frontend renders `styles` in array order — no client-side sort needed.

### 2.9 Integration: Frontend

#### Replace hardcoded `STYLES` / `STYLE_LABELS` with API fetch

```typescript
// Before (hardcoded):
const STYLES = ["All", "value", "growth", "activist", "lt_compounder", "sector"];
const STYLE_LABELS: Record<string, string> = {
    value: "Value", growth: "Growth", activist: "Activist",
    lt_compounder: "Compounders", sector: "Sector",
};

// After (fetched from API):
function useStyles() {
    return useQuery({
        queryKey: ["super-investors", "styles"],
        queryFn: () => fetchSuperInvestorsStyles(),
        staleTime: Infinity,  // content rarely changes
    });
}
```

The `useStyles()` hook returns `{ version, styles: [...] }`. Filter chips
render from `useStyles().styles` instead of `STYLES`/`STYLE_LABELS` constants.

#### TypeScript types — codegen for slugs only

The generated file contains **types only** — no runtime constants that
duplicate the API endpoint.

```typescript
// web/src/types/generated/investor-styles.ts
// AUTO-GENERATED — do not edit. Source: backend/config/super_investors.json
//
// This file exists for type inference only. Do NOT use INVESTOR_STYLE_SLUGS
// as a render order — fetch that from GET /super-investors/styles instead.

export const INVESTOR_STYLE_SLUGS = [
  "lt_compounder",
  "value",
  "growth",
  "activist",
  "sector",
  "venture_contrarian",
] as const;

export type InvestorStyleSlug = (typeof INVESTOR_STYLE_SLUGS)[number];
```

No `INVESTOR_STYLE_LABELS` constant — that data lives in the API endpoint.
The generated file exists for **compile-time type safety** on slugs only.

**Codegen runs as a mandatory CI step** — CI fails if the generated file
differs from the checked-in version:

```bash
# CI step
python scripts/generate_investor_types.py
git diff --exit-code web/src/types/generated/investor-styles.ts
```

A pre-commit hook runs the same check before `git commit`. CI step 3 in the
pipeline below enforces it for the shared branch.

**Codegen script** (`backend/scripts/generate_investor_types.py`):

```python
import json
from pathlib import Path

CONFIG = Path("backend/config/super_investors.json")
OUTPUT = Path("web/src/types/generated/investor-styles.ts")

def main():
    data = json.loads(CONFIG.read_text())
    # Sort by sort_order for product-defined ordering; deterministic because
    # sort_order uniqueness is validated by the Python loader.
    categories = sorted(
        data["style_categories"].items(),
        key=lambda item: item[1].get("sort_order", 999),
    )
    slugs = [slug for slug, _ in categories]
    lines = [
        "// AUTO-GENERATED — do not edit. Source: backend/config/super_investors.json",
        "",
        "export const INVESTOR_STYLE_SLUGS = [",
        *[f'  "{s}",' for s in slugs],
        "] as const;",
        "",
        "export type InvestorStyleSlug = (typeof INVESTOR_STYLE_SLUGS)[number];",
        "",
    ]
    OUTPUT.write_text("\n".join(lines))

if __name__ == "__main__":
    main()
```

#### Error/loading state for `useStyles()`

If the `/super-investors/styles` endpoint fails, the filter UI gracefully
degrades — no style filters are shown rather than displaying broken UI.

```typescript
function useStyles() {
    const { data, isError } = useQuery({
        queryKey: ["super-investors", "styles"],
        queryFn: () => fetchSuperInvestorsStyles(),
        staleTime: Infinity,
    });
    return { styles: data?.styles ?? [], isError };
}
```

During loading, the filter pill row shows a compact skeleton placeholder
(three short shimmer bars). On error, the entire style filter section is
hidden — only sector and investor-count filters remain visible.

### 2.10 CI/CD & Validation Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                     CI on PR (config change)                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. JSON Schema validation                                   │
│     jsonschema -i config/super_investors.json \              │
│                config/super_investors.schema.json            │
│                                                              │
│  2. Python loader validation                                 │
│     python -c "from application.services                     │
│     .super_investors_loader import get_config; get_config()" │
│                                                              │
│  3. TypeScript codegen + diff check                          │
│     python scripts/generate_investor_types.py                │
│     git diff --exit-code web/src/types/generated/            │
│                                                              │
│  4. CIK validation (on config change only)                   │
│     python scripts/validate_ciks.py                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

The CI pipeline ensures:
- JSON is well-formed and structurally valid (step 1)
- Python loader accepts it with no validation errors (step 2)
- TypeScript types are regenerated and match the committed version (step 3)
- All CIKs are valid against SEC EDGAR (step 4 — runs only on config changes)

**Step 4 trigger** (GitHub Actions path filter):

```yaml
jobs:
  validate-ciks:
    if: github.event_name == 'pull_request'
    paths:
      - 'backend/config/super_investors.json'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install edgartools
      - run: python scripts/validate_ciks.py
```

CIK validation hits the SEC EDGAR API, which is an external network call.
Running it only on config changes avoids fragile network dependency on
every PR.

### 2.11 Migration Path

Steps grouped into **Pre-cutover** (prep), **Cutover** (functional switch),
and **Post-cutover** (cleanup). Rows are ordered top-to-bottom for execution.

| Phase | Step | What | Depends on |
|-------|------|------|------------|
| **Pre-cutover** | **1** | Create `backend/config/super_investors.json` with existing 24 investors, styles, schema | None |
| | **2** | Create `SuperInvestorsConfig` loader class + `get_config()` singleton | None |
| | **3** | Add `GET /super-investors/styles` endpoint with `Depends` wiring | Step 2 |
| | **4a** | **DB normalization**: run SQL to normalize existing `investment_style` values to current config labels | None |
| | **4b** | Add ingestion guard (always write `investment_style` from config) | Step 2 |
| **Cutover** | **5a** | Wire loader into `super_investors_service.py` → `get_super_investors()` function + `__getattr__` bridge shim | Steps 2, 4b |
| | **5b** | Wire loader into `super_investors.py` → replace `style_map` with `get_style_label()` | Step 2 |
| | **5c** | Wire loader into `validate_ciks.py` | Step 2 |
| **Post-cutover** | **6** | Frontend: add `useStyles()` hook + fetch from API | Step 3 |
| | **7** | Frontend: run codegen, commit generated `investor-styles.ts` | Step 1 |
| | **8** | CI: add validation pipeline (Schema + loader + codegen + CIK) | Steps 1–2 |
| | **9** | Update tests to mock `get_config()` / `reset_config()` | Step 2 |
| | **10** | Remove `__getattr__` bridge shim after all consumers migrated (grep repo — only `super_investors_service.py` should reference `SUPER_INVESTORS`) | Steps 5a–9 |
| | **11** | Add **Peter Thiel** entry + `venture_contrarian` to config | Steps 1–10 |

**Critical ordering**:
- Step 4a (DB normalization) must precede step 5a (read-from-config).
- Step 4b (write-from-config) must precede step 5a (read-from-config).
- Steps 5a–5c are the functional cutover (atomic, reversible together).
- Steps 6–11 are independent after the cutover.

Verification: CI can enforce step 10 with `grep -r 'SUPER_INVESTORS' backend/ --include='*.py' | grep -v super_investors_service.py`.

### 2.12 Test Strategy

```python
# Before — fragile module mutation:
import application.schedulers.super_investors_scheduler as mod
original = dict(mod.SUPER_INVESTORS)
mod.SUPER_INVESTORS = {"0001": {"name": "A", "tag": "v", ...}}
try:
    ...
finally:
    mod.SUPER_INVESTORS = original

# After — mock the loader singleton:
from application.services.super_investors_loader import reset_config, get_config
from unittest.mock import patch

# Option A: Use reset_config() with a test config file
def setup_method(self):
    reset_config()
    os.environ["SUPER_INVESTORS_CONFIG_PATH"] = str(TEST_CONFIG_PATH)

def teardown_method(self):
    reset_config()
    os.environ.pop("SUPER_INVESTORS_CONFIG_PATH", None)

# Option B: Patch get_config() directly (clean for unit tests)
@patch("application.services.super_investors_loader.get_config")
def test_plan_returns_correct_format(self, mock_get_config):
    mock_cfg = MagicMock(spec=SuperInvestorsConfig)
    mock_cfg.by_cik = {"0001": {"name": "A", "tag": "v", ...}}
    mock_get_config.return_value = mock_cfg
    ...
```

**Recommended**: Option B for unit tests (no filesystem dependency), Option A
for integration tests (validates actual file parsing).

**Patch target note**: When using `@patch`, target the **consumption site**
(where the name is looked up), not the definition site:

```python
# super_investors_scheduler.py imports:
from application.services.super_investors_service import get_super_investors

# Patch at the consumption site, not the loader:
@patch("application.services.super_investors_service.get_super_investors")
def test_plan(self, mock_get):
    ...
```

### 2.13 Health Check

```json
// GET /health
{
  "status": "ok",
  "super_investors": {
    "active": 25,
    "total": 25,
    "config_version": 1,
    "config_source": "super_investors.json"
  }
}
```

Separate counts for active vs total make troubleshooting obvious.

### 2.14 Admin Reload Endpoint

Optional. If implemented, must be authenticated:

```python
@router.post("/admin/super-investors/reload")
async def reload_super_investors(
    current_user: User = Depends(require_admin),
):
    """
    Reload super investor config from file without restart.
    
    NOTE: Requires admin authentication. Do not expose unauthenticated.
    In-flight scheduler jobs are unaffected (they use the config
    that was active when planned).
    """
    cfg = reload_config()
    return {
        "status": "ok",
        "version": cfg.version,
        "active_count": len(cfg.by_cik),
        "total_count": len(cfg.investors),
    }
```

### 2.15 File Structure (After)

```
backend/
├── config/
│   ├── super_investors.json           ← NEW: single source of truth
│   └── super_investors.schema.json    ← NEW: JSON Schema for CI + IDE
├── application/
│   └── services/
│       ├── super_investors_service.py  ← exports get_super_investors()
│       └── super_investors_loader.py   ← NEW: loader + get_config() singleton
├── api/
│   ├── dependencies.py                 ← NEW: get_si_config() FastAPI dependency
│   └── super_investors.py             ← Depends(get_si_config), /styles endpoint
├── scripts/
│   ├── generate_investor_types.py      ← NEW: TypeScript codegen
│   ├── validate_ciks.py               ← reads from loader
│   └── backfill_super_investors.py    ← uses bridge shim during migration; update to get_super_investors() after bridge removal
└── tests/
    ├── test_scheduler_plan_methods.py  ← mock get_config()
    └── test_super_investors_loader.py  ← NEW: unit tests for loader

web/src/
├── types/
│   └── generated/
│       └── investor-styles.ts         ← NEW: auto-generated slugs only
└── features/
    └── super-investors/
        ├── services/...               ← add fetchSuperInvestorsStyles()
        └── types/...                  ← generated InvestorStyleSlug type
```

---

## 3. Summary

### 3.1 The `"venture_contrarian"` Entry (Final)

In `backend/config/super_investors.json`:

```jsonc
{
  "style_categories": {
    "venture_contrarian": {
      "label": "Venture / Contrarian",
      "short_label": "Venture",
      "sort_order": 6,
      "description": "Early-stage VC mentality with contrarian public market bets"
    }
  },
  "investors": [
    {
      "cik": "0001211060",
      "name": "Peter Thiel",
      "firm": "FOUNDERS FUND MANAGEMENT LLC",
      "tag": "THIEL",
      "style_category": "venture_contrarian",
      "quarters": 4,
      "active": true
    }
  ]
}
```

That's it. No Python changes. No TypeScript changes (codegen picks it up).
One file.

### 3.2 Benefits Summary

| Concern | Before | After |
|---------|--------|-------|
| Add new investor | Edit 6 files in 2 repos | Edit 1 JSON file |
| Add new style category | Edit 4 files (backend map + frontend types + arrays + labels) | Add to `style_categories` in JSON, assign to an investor |
| Frontend filter UI | Hardcoded arrays, requires deploy | Dynamic from API |
| TypeScript type safety | Manual union, drifts from source | Generated from config, CI-enforced |
| CIK validation | Duplicate dict, name mismatches | Reads same config |
| DB drift | No protection, free-text `varchar` | Ingestion always writes from config |
| Test maintenance | Mock dict, mutate module globals | Mock `get_config()` singleton |
| Startup robustness | Import failure on bad config | Lazy load, clear validation errors |
| Config reload | No mechanism | Admin endpoint with auth guard |
