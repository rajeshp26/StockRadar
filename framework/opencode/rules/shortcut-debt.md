# Shortcut debt markers

A deliberate simplification that leaves a known ceiling in the code is a debt item. Mark it at
the code site so a deferral cannot quietly become permanent.

## The marker (MANDATORY when you take a shortcut)

```
shortcut: <the limit>, <when to upgrade>
```

* `<the limit>` - what the current code does not handle: one process, UTC only, O(n^2) below
  10k rows, no retry.
* `<when to upgrade>` - the concrete trigger that forces the full version: a second worker, a
  second timezone, rows above 10k, a vendor health endpoint.

Both halves are required. Put the marker on the line it constrains, in that language's comment
syntax.

## What a marker is not

A marker records a decision. It never authorises one.

* It is **not** acceptable evidence for a requirement. Gates, contracts, and checklists are
  unchanged by it.
* It may **never** cover the floor: validation at a trust boundary, data-loss error handling,
  security, accessibility, or anything the user explicitly asked for. Those are defects, not
  shortcuts.
* A marker with no upgrade trigger is `no-trigger`. That is rot, not a decision.

## Harvesting

`framework/retro/shortcut_debt.py` lists every marker with its ceiling and its upgrade trigger,
and reports `<N> markers, <M> with no trigger`. It exits non-zero when any marker has no
trigger.

Harvested rows feed the retrospective ledger's `accepted` tier (`framework/retro/ledger.py`) -
one debt system, two inputs. Do not start a second ledger.
