# Seeded-defect rubric — design-skills pilot

Fixture: `fixture.html` (a self-contained "Dividends" screen).

Eleven defects are deliberately seeded. Six are **novel** (the imported skill's flow /
cognitive-load / UX-law / IA / prospect-refuge passes; no existing pipeline equivalent).
Five are **control** (already enforced by the existing six-pillar audit or the UI pipeline;
they must not regress).

Scoring is mechanical: a defect counts as found when a single finding names the element and
the problem, i.e. it contains at least two terms from that defect's `accept` list. A finding
that names the element but not the consequence does not count.

## Novel defects

| ID | Defect | Pass that names it | accept (any 2 in one finding) |
|---|---|---|---|
| D1 | Removing a holding gives no confirmation, no toast, no state change feedback | Action Cycle — evaluation / feedback | remove, holding, delete, no feedback, silent, toast, confirm |
| D2 | Destructive remove is immediate and irreversible (no undo) | Flow — control / user control | undo, irreversible, destructive, no confirmation, cannot recover, permanent |
| D3 | Timeframe select packs 14 options into one flat list, no grouping or default guidance | Hick's Law / cognitive load | 14, options, flat, unchunked, Hick, cognitive load, too many |
| D4 | Top navigation has no current/active state and no `aria-current`; user cannot tell where they are | Information architecture — location | active, current, aria-current, selected state, where am I, no indication |
| D5 | "Refresh prices" starts a 4 s operation with no spinner, skeleton, or disabled state | Action Cycle — perception / response time | spinner, loading, skeleton, disabled, 4, feedback, progress |
| D6 | Sharing is on by default and the privacy consequence is 10 px muted text at the bottom | Prospect-refuge / user control | sharing, default, on by default, privacy, buried, 10px, muted, consent |

## Control defects (must not regress)

| ID | Defect | Existing owner | accept (any 2 in one finding) |
|---|---|---|---|
| D7 | Error banner reads "Error 422." with no explanation or next step | UI copy contract | 422, error, no next step, unexplained, code only, recovery |
| D8 | Trash icon button has no visible label and no accessible name | Icon/label rule | icon-only, unlabeled, aria-label, accessible name, no label |
| D9 | Three equal-weight solid primary buttons compete | Button hierarchy | three, primary, equal, competing, hierarchy, multiple primary |
| D10 | Muted text `#6b7280` on `#0b0f14` is ~3.98:1, below 4.5:1 | Contrast rule | contrast, 4.5, 3.9, 3.98, below, muted, WCAG |
| D11 | Empty state says only "No data" | Empty-state copy | empty, no data, no next step, guidance, dead end |

## Metrics

- **Novel recall** = novel defects found / 6 (primary).
- **Control recall** = control defects found / 5 (guard).
- **Per-defect regression** = a defect found in baseline and missed in treatment.
- **Factual errors** = findings that assert something the fixture does not contain (guard).

## Keep / revert (pre-registered)

**KEEP** the review-path obligation only if all three hold:

1. Novel recall improves by at least 2 defects over baseline.
2. No per-defect regression on any defect found by baseline (novel or control).
3. No factual error introduced that baseline did not make.

**REVERT** otherwise: remove the review-path obligation, keep the import advisory. A skill that
does not measurably improve review output does not earn a mandatory slot.
