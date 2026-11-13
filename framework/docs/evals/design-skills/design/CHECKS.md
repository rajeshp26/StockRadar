# Design-path checks (scoring — never shown to the designer)

Score the variant the decision sheet recommends. If none is recommended, score the
highest-scoring variant and record that fallback.

Each check is pass/fail on the variant's HTML/CSS/JS. Detection is by reading the source, not by
eyeballing a screenshot.

| ID | Check | Pass condition | Type |
|---|---|---|---|
| C1 | Destructive remove is recoverable | confirmation dialog/step **or** an undo action exists | skill |
| C2 | Refresh has a busy state | spinner, skeleton, `aria-busy`, or a disabled button while pending | skill |
| C3 | Time filter is bounded | ≤ 8 options, **or** grouped (`optgroup`) / progressively disclosed | skill |
| C4 | Current location is visible | if a nav exists: `aria-current`, `aria-selected`, or an active style on the current item | skill |
| C5 | Sharing is opt-in | share control is **not** checked by default, and the consequence is adjacent (`aria-describedby`, same fieldset, or inline label) | skill |
| C6 | Error has a next step | retry/action shown, not only a status code or generic message | skill |
| C7 | Focus is visible | `:focus-visible` defined, or no `outline: none` without a replacement | skill |
| C8 | One primary action | exactly one primary-styled CTA on the screen | skill |
| C9 | Targets are touch-sized | primary and icon buttons ≥ 44×44 px in CSS | skill |
| C10 | Empty state has a next step | empty state names the state and offers an action | skill |
| C11 | Total income is summarised | a total projected annual income figure is present | skill |
| C12 | Icon-only controls are named | every icon-only button has `aria-label` or visible text | control |

`control` = the existing pipeline already covers it; it must not regress.

## Keep / revert (pre-registered)

**KEEP** the design-path obligation only if both hold:

1. Treatment score ≥ baseline score + 3.
2. No check passed by baseline is failed by treatment.

**REVERT** otherwise: remove the `Design craft basis` section from the charter and keep the
import advisory. A design obligation that does not change the design output does not earn a
place in the charter.

## What this measures and does not

It measures whether the named principles changed the **design output** (behaviour, states,
structure), not whether the decision sheet cites them. Citation quality is not scored — that
was the failure mode the charter itself warns about.

It does not measure taste, visual craft, or whether the recommended direction is the best of the
three. Those remain human judgement.
