<!-- expect: PL03,PL04,PL05,PL06 -->
status: approved
files_or_components: [backend/shared/legacy_holding_price.py, backend/shared/legacy_quality.py]
acceptance_criteria: [ _resolve_holding_price applies a configurable max-age bound , quality is derived from computed price_age_days and not from PriceTier identity ]
