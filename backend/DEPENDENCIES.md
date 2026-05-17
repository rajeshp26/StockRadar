# Dependency Management

Uses [pip-tools](https://github.com/jazzband/pip-tools) (pip-compile + pip-sync).

## File Layout

| File | Purpose |
|---|---|
| `requirements.in` | Human-authored direct deps |
| `requirements.txt` | Auto-generated lock file (never edit) |
| `requirements-dev.in` | Dev-only deps (pytest, etc.) |
| `requirements-dev.txt` | Auto-generated dev lock file (never edit) |

## Workflow

```bash
# Generate lock files from .in files
pip-compile requirements.in -o requirements.txt
pip-compile requirements-dev.in -o requirements-dev.txt

# Sync venv to exact locked versions
pip-sync requirements-dev.txt
```

## Adding / Upgrading a Dependency

1. Edit `requirements.in`
2. Run `pip-compile requirements.in -o requirements.txt`
3. Run `pip-sync requirements-dev.txt`
4. Test

## Known Constraints

| Package | Reason |
|---|---|
| `yfinance==1.2.0` | stockdex 1.2.5 pins `curl_cffi==0.12.0`; yfinance >=1.2.1 requires `curl_cffi>=0.15` → conflict. Pin to 1.2.0 (`curl_cffi>=0.7,<0.14`) until stockdex updates its pin. |
| `fsspec<=2025.10.0` | pandas 3.x requires this max version. |
