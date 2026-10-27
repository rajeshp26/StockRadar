import sys

with open(r'C:\Project\StockerPro\StockerPro\backend\scripts\preflight_dependencies.py', 'r') as f:
    content = f.read()

old = '''    critical = {n for n, _, _ in drift} & set(PIPELINE_CRITICAL)
    lines = [
        "=" * 68,
        "DEPENDENCY DRIFT DETECTED - installed environment != requirements.txt",
        "=" * 68,
    ]
    if critical:
        lines += [
            "",
            "!! FATAL: price-pipeline dependency is wrong.",
            "!! The provider cannot initialise, every fetch degrades to a warning,",
            "!! and price_history is starved without any error surfacing.",
            "!! PRICE DATA WRITTEN BY THIS PROCESS IS NOT TRUSTWORTHY.",
        ]
    for name, want, have in drift:
        tag = "  <-- PIPELINE CRITICAL" if name in PIPELINE_CRITICAL else ""
        shown = have if have is not None else "NOT INSTALLED"
        lines.append(f"  DRIFT {name}: declared {want}, installed {shown}{tag}")
    lines += ["", "Fix: python -m pip install -r backend/requirements.txt", ""]

    msg = "\\n".join(lines)

    if logger:
        logger.error(msg)
    else:
        print(msg, file=sys.stderr)

    if os.environ.get("PRICE_PREFLIGHT_FATAL", "").strip() in ("1", "true", "yes"):
        # Only a pipeline-critical drift is fatal; unrelated package drift is noise.
        if critical:
            raise RuntimeError(
                "PRICE_PREFLIGHT_FATAL: pipeline-critical dependency drift detected: "
                + ", ".join(sorted(critical))
            )
    return False'''

new = '''    critical = {n for n, _, _ in drift} & set(PIPELINE_CRITICAL)
    lines = [
        "=" * 68,
        "DEPENDENCY DRIFT DETECTED - installed environment != requirements.txt",
        "=" * 68,
    ]
    if critical:
        lines += [
            "",
            "!! FATAL: price-pipeline dependency is wrong.",
            "!! The provider cannot initialise, every fetch degrades to a warning,",
            "!! and price_history is starved without any error surfacing.",
            "!! PRICE DATA WRITTEN BY THIS PROCESS IS NOT TRUSTWORTHY.",
        ]
    for name, want, have in drift:
        tag = "  <-- PIPELINE CRITICAL" if name in PIPELINE_CRITICAL else ""
        shown = have if have is not None else "NOT INSTALLED"
        lines.append(f"  DRIFT {name}: declared {want}, installed {shown}{tag}")
    lines += ["", "Fix: python -m pip install -r backend/requirements.txt", ""]

    msg = "\\n".join(lines)

    if logger:
        logger.error(msg)
    else:
        print(msg, file=sys.stderr)

    # Make critical dependency drift fatal by default (professional-grade fail-fast)
    if critical:
        raise RuntimeError(
            "CRITICAL DEPENDENCY DRIFT: pipeline dependencies do not match requirements.txt. "
            "Run: pip install -r backend/requirements.txt. "
            "Critical: " + ", ".join(sorted(critical))
        )
    return False'''

if old not in content:
    print("NOT FOUND")
    sys.exit(1)
else:
    content = content.replace(old, new)
    with open(r'C:\Project\StockerPro\StockerPro\backend\scripts\preflight_dependencies.py', 'w') as f:
        f.write(content)
    print("DONE")
    sys.exit(0)
