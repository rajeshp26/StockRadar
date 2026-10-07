# framework/quality/

Baseline static-analysis configs for `framework/gates/g4_executable.sh`'s
per-language branches. Every file here was verified against a deliberately
bad fixture during this framework's audit — see the comment header in each
file for exactly what was tested and what it caught. Nothing in this
directory is invented from a tool's marketing copy; each claim below is
either something I ran or something the gate itself reports as unavailable.

## What runs automatically vs. what you set up once

G4 never installs anything and never treats a missing tool as a pass — it
reports it under "tools unavailable" and moves on. What you get per language:

| Language | Tool(s) | Auto-discovered? | Setup needed |
|---|---|---|---|
| Python | `ruff`, `mypy`, `bandit` | Yes, if on `PATH` | Copy `python/pyproject.ruff.toml`'s `[tool.ruff]` block into the project's `pyproject.toml` — **without it, ruff runs with bare defaults and will not catch hardcoded secrets or magic-value comparisons.** Verified: same file, bare ruff = 0 findings; with this config = 3 findings (hardcoded password, SQL-injection shape, `shell=True`). |
| JS / TS / React | `eslint` (+ `tsc` if `tsconfig.json` present) | Only if `package.json` declares a `"lint"` script **and** `node_modules` exists | Copy `javascript/eslint.config.baseline.js` to `eslint.config.js`, add the `"lint": "eslint ."` script, install the pinned versions in that file's header comment — **do not let npm resolve ESLint past `^9`**, see below. |
| C / C++ | `cppcheck` (`--addon=misra`) | Yes, if on `PATH` (`apt-get install cppcheck`) | None for the check itself. For human-readable MISRA rule text (not just rule numbers) you need a legally obtained copy of the MISRA C:2012 document and `--rule-texts=<file>` — MISRA's rule prose is proprietary and this framework does not ship or fetch it. |
| Java | `checkstyle` jar, `pmd` script | Only if `CHECKSTYLE_JAR` / `PMD_BIN` env vars point at a real jar/executable | Download release jars (see versions below) and export the two env vars, or point them at your CI's own copies. |
| Any of the above | `gitleaks` | Yes, if on `PATH` | None. Runs regardless of detected language — a hardcoded secret doesn't respect file extensions. |

## Real version pins that matter (found by actually installing these, not assumed)

- **ESLint must stay on `^9` for `eslint-plugin-react` compatibility.** `eslint-plugin-react@7.37.5` (current at time of writing) declares `peerDependencies: { eslint: "^3 || ... || ^9.7" }`. If `npm install` is allowed to resolve ESLint 10 anyway (e.g. via `--legacy-peer-deps`), the plugin crashes at runtime: `TypeError: contextOrFilename.getFilename is not a function` inside `react/display-name`, on every file, not just ones with real issues. This is not a hypothetical — I hit it by doing the "obvious" thing (`npm install eslint eslint-plugin-react ...` with no version pin) and had to downgrade to fix it.
- Checkstyle and PMD are jars/scripts, not `apt`/`pip`/`npm` packages, hence the env-var discovery pattern instead of a `have <binary>` check. Versions used during verification: Checkstyle 10.20.2 (`checkstyle-10.20.2-all.jar`), PMD 7.8.0 (`pmd-dist-7.8.0-bin.zip`), both pulled from their GitHub release assets. Newer releases should work the same way; nothing here pins to those exact versions on purpose.
- Cppcheck 2.13.0 (Ubuntu's `apt` package) was used for verification; the MISRA addon (`misra.py`) ships inside the same package, no separate install.

## Coverage gaps, stated plainly rather than papered over

- **Arithmetic magic numbers vs. comparison magic numbers.** Python's `ruff` `PLR2004` rule only fires on magic values in *comparisons* (`if x == 42`), not arithmetic (`x * 86400`). Checkstyle's `MagicNumber` check (Java) is stricter — it fires on the arithmetic case too. There is no equally strict off-the-shelf Python equivalent wired in here; a custom Ruff/Pylint plugin would be a further increment, not something this patch invents.
- **Generic hardcoded credentials with an unrecognizable variable name and no known-provider format.** `gitleaks` catches known secret *shapes* (Stripe/AWS/GitHub-token-style strings, private keys, high-entropy strings). `ruff`'s `S105`/bandit's `B105` catch obviously-named variables (`password`, `secret`, `api_key`, ...). A hardcoded value that is neither a recognizable secret format nor obviously named (e.g. a business-logic constant that should have been a named config value) is a code-review judgment call, not a pattern a static tool reliably flags — that's still the `gsd-code-reviewer` agent's job, not a gap this patch claims to close.
- **C/C++ MISRA rule text.** Rule *numbers* are free; rule *prose* is MISRA Ltd's copyrighted document. This framework reports violated rule numbers only.
