#!/usr/bin/env bash
# Windows toolchain resolution for bash on Windows (WSL interop).
#
# THE DEFECT THIS FIXES
# =====================
# Every gate is a bash script. On Windows the only bash is WSL's, and WSL resolves a
# command name to a file of exactly that name. Windows toolchains install `node.exe`,
# `ruff.exe`, `pytest.exe` -- the PE is reachable through interop only under its full
# name, so `command -v node` fails while `/mnt/c/nvm4w/nodejs/node.exe` sits on PATH.
#
# Measured on this host before this file existed:
#
#     command -v node   -> (nothing)     /mnt/c/nvm4w/nodejs/node.exe     existed
#     command -v ruff   -> (nothing)     .../Python311/Scripts/ruff.exe   existed
#     command -v pytest -> (nothing)     .../Python313/Scripts/pytest.exe existed
#
# Consequences were not cosmetic. G4 reported `FAIL types` because
# `node_modules/.bin/tsc` is `#!/bin/sh ... exec node`, and reported Python as having
# "zero static analysis" because ruff/mypy/bandit were all invisible. The gate was
# reading "tool not installed" for tools that were installed. Any Windows host lost
# its entire JS/TS and Python toolchain this way, silently, on every run.
#
# THE FIX, AND WHY THIS SHAPE
# ===========================
# Create a shim directory of extensionless symlinks to the Windows `.exe` binaries and
# APPEND it to PATH. Appending, not prepending, is deliberate: a real WSL-native tool
# must always win over a Windows PE, so this only supplies names that are missing. The
# symlink itself is a real PE at its real path, so Windows DLL resolution is intact --
# the same mechanism `validate.py:_win_py_shim()` already relies on for python3.
#
# python3/python are deliberately NOT in the list below: the interpreter must stay the
# one the suite chose, or POSIX state roots leak into framework/.manifest (see
# validate.py:100). Interpreter selection stays a caller concern.
#
# Sourcing has the side effect of initialising. It is idempotent and a no-op off WSL.

if [ -z "${BASH_VERSION:-}" ]; then
  echo "BLOCKED: framework gates require bash. Run: bash $0" >&2
  exit 2
fi

# Tools worth aliasing. Override with FRAMEWORK_WIN_TOOLS="_tool _other".
FRAMEWORK_WIN_TOOLS_DEFAULT="node npm npx tsc eslint prettier ruff mypy bandit pytest gitleaks cppcheck java javac"

_framework_is_wsl() {
  [ -n "${WSL_DISTRO_NAME:-}" ] && return 0
  [ -r /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null
}

_framework_toolchain_init() {
  # Idempotent: gates source _lib.sh once, but tests and nested gates may not be so tidy.
  [ -n "${_FRAMEWORK_TOOLCHAIN_DIR:-}" ] && return 0

  _framework_is_wsl || return 0

  local dir="${TMPDIR:-/tmp}/framework-toolchain-$(id -u 2>/dev/null || echo 0)"
  mkdir -p "$dir" 2>/dev/null || return 0

  local -a path_dirs
  IFS=: read -r -a path_dirs <<< "$PATH"

  local tools="${FRAMEWORK_WIN_TOOLS:-$FRAMEWORK_WIN_TOOLS_DEFAULT}"
  local t p made=0
  for t in $tools; do
    # A native tool always wins; only fill genuinely missing names.
    if command -v "$t" >/dev/null 2>&1; then
      continue
    fi
    for p in "${path_dirs[@]}"; do
      if [ -n "$p" ] && [ -x "$p/$t.exe" ]; then
        if ln -sf "$p/$t.exe" "$dir/$t" 2>/dev/null; then
          made=1
        fi
        break
      fi
    done
  done

  if [ "$made" -eq 1 ]; then
    # Also prepend, so a native tool still wins (native dirs are later in PATH order
    # than they were before only if they were absent -- command -v above guarantees we
    # only added names that had no native provider).
    PATH="$PATH:$dir"
    export PATH
    _FRAMEWORK_TOOLCHAIN_DIR="$dir"
  fi
  return 0
}

# Absolute path of a resolved tool, or empty. Prefer this over parsing `command -v`
# output in callers: it never returns a shell builtin name.
framework_tool_path() {
  local p
  p="$(type -P "$1" 2>/dev/null)" || p=""
  [ -n "$p" ] || p="$(command -v "$1" 2>/dev/null)" || p=""
  # `command -v printf` yields the bare word "printf"; only return real files.
  if [ -n "$p" ] && [ -e "$p" ]; then printf '%s' "$p"; fi
  return 0
}

_framework_toolchain_init
