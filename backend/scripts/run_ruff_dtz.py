"""Run ruff DTZ check on the backend."""
import subprocess, sys
result = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "--select", "DTZ", "."],
    capture_output=True, text=True, cwd=sys.argv[1] if len(sys.argv) > 1 else ".",
)
print(result.stdout[-2000:])
if result.stderr:
    print("STDERR:", result.stderr[-500:])
sys.exit(result.returncode)
