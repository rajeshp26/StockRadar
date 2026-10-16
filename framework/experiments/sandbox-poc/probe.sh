#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# sandbox-poc / probe.sh  —  DISPOSABLE PROOF-OF-CONCEPT (technical-validation)
#
# Question: can THIS host (Windows + WSL bash) enforce the OS-level sandbox
# controls the security-audit skill requires before any target-controlled
# execution?
#
# This file is throwaway validation evidence. It is NOT part of the framework,
# is wired into no gate, and changes nothing outside its own directory. It
# should be deleted once the validation record is written.
#
# Exit codes: 0 = all probes pass (sandbox enforceable)
#             1 = one or more probes failed (NOT enforceable -> source-only)
#             3 = cannot run (not Linux / no shell primitives)
# ---------------------------------------------------------------------------
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/sandbox-poc.XXXXXX")" || { echo "cannot create scratch"; exit 3; }
RESULTS=()
OVERALL=0
INCOMPLETE=0

cleanup() { rm -rf "$SCRATCH" 2>/dev/null || true; }
trap cleanup EXIT

record() { # name status detail
  local name="$1" status="$2" detail="$3"
  RESULTS+=("$name|$status|$detail")
  printf '%-22s %-5s %s\n' "$name" "$status" "$detail" >&2
  [ "$status" = "FAIL" ] && OVERALL=1
  [ "$status" = "SKIP" ] && INCOMPLETE=1
  return 0
}

have() { command -v "$1" >/dev/null 2>&1; }

echo "== sandbox POC ==" >&2
echo "cwd:  $HERE" >&2
echo "uname: $(uname -srm 2>/dev/null || echo unknown)" >&2
echo "id:   $(id -un 2>/dev/null || echo unknown) uid=$(id -u 2>/dev/null || echo '?')" >&2
echo >&2

# --- platform gate -----------------------------------------------------------
if [ "$(uname -s 2>/dev/null)" != "Linux" ]; then
  record platform FAIL "not Linux (got '$(uname -s 2>/dev/null)'); WSL/Linux primitives unavailable"
fi

# --- probe 7 (part a): Win32 -> WSL boundary --------------------------------
case "$HERE" in
  /mnt/[a-z]/*) record win32_wsl PASS "repo reached via Windows drive at $HERE" ;;
  *)            record win32_wsl NOTE "not under /mnt (native Linux, or path not translated)" ;;
esac

# --- tool detection ----------------------------------------------------------
HAS_BWRAP=no;  have bwrap   && HAS_BWRAP=yes
HAS_SOCAT=no;  have socat   && HAS_SOCAT=yes
HAS_UNSHARE=no; have unshare && HAS_UNSHARE=yes
HAS_TIMEOUT=no; have timeout && HAS_TIMEOUT=yes
record tools_info PASS "bwrap=$HAS_BWRAP socat=$HAS_SOCAT unshare=$HAS_UNSHARE timeout=$HAS_TIMEOUT"

# Build read-only bind list from directories that actually exist.
BINDS=()
for d in /usr /bin /sbin /lib /lib64 /lib32 /etc; do
  [ -e "$d" ] && BINDS+=(--ro-bind "$d" "$d")
done
record bwrap_bases PASS "ro-bind roots: ${BINDS[*]:-none}"

USERNSPASS=no
# --- probe 1a: unprivileged user namespaces (the prerequisite for bubblewrap) --
if [ "$HAS_UNSHARE" != yes ]; then
  record userns SKIP "unshare(1) not installed"
else
  out="$(unshare --user --map-root-user /bin/true 2>&1)"
  if [ $? -eq 0 ]; then
    record userns PASS "--user --map-root-user works unprivileged"
  else
    record userns FAIL "userns denied: $(echo "$out" | tr '\n' ' ' | cut -c1-160)"
  fi
  out2="$(unshare --user --map-root-user --mount --net --pid --fork /bin/true 2>&1)"
  if [ $? -eq 0 ]; then
    USERNSPASS=yes
    record userns_full PASS "user+mount+net+pid namespaces creatable unprivileged"
  else
    record userns_full FAIL "$(echo "$out2" | tr '\n' ' ' | cut -c1-160)"
  fi
fi

# --- sysctl state (why userns may be denied) ---------------------------------
SYSCTL=""
for f in /proc/sys/kernel/unprivileged_userns_clone /proc/sys/user/max_user_namespaces /proc/sys/kernel/apparmor_restrict_unprivileged_userns; do
  [ -r "$f" ] && SYSCTL="$SYSCTL $(basename "$f")=$(cat "$f" 2>/dev/null)"
done
record userns_sysctl INFO "${SYSCTL:-no userns knobs exposed}"

# --- cgroup v2 (resource limits, and who may create a subgroup) ---------------
CG="$(stat -fc %T /sys/fs/cgroup 2>/dev/null || echo none)"
CGCTRL="$(cat /sys/fs/cgroup/cgroup.controllers 2>/dev/null || echo none)"
if mkdir -p "/sys/fs/cgroup/poc.$$" 2>/dev/null; then
  rmdir "/sys/fs/cgroup/poc.$$" 2>/dev/null || true
  record cgroup PASS "fs=$CG controllers=[$CGCTRL] delegated (can create subgroups)"
else
  record cgroup INFO "fs=$CG controllers=[$CGCTRL] direct subgroup creation denied to uid $(id -u) (expected; see cgroup_user for the delegated path)"
fi

# --- installability of the missing primitives --------------------------------
if have apt-get; then
  bw="$(dpkg -s bubblewrap >/dev/null 2>&1 && echo installed || echo missing)"
  so="$(dpkg -s socat      >/dev/null 2>&1 && echo installed || echo missing)"
  record pkg_mgr INFO "apt-get present; bubblewrap=$bw socat=$so (install is a provisioning decision, not done here)"
else
  record pkg_mgr INFO "no apt-get; check the distro package manager for bubblewrap/socat"
fi

# --- resource limits that do NOT need cgroups ---------------------------------
mkdir -p "$SCRATCH/scratch"
if ( ulimit -f 64 2>/dev/null; dd if=/dev/zero of="$SCRATCH/scratch/big2" bs=1024 count=4096 2>/dev/null ); then
  record ulimit_kernel FAIL "kernel RLIMIT_FSIZE not enforced (wrote a 4MB file under a 32KB cap)"
else
  record ulimit_kernel PASS "kernel RLIMIT_FSIZE enforced in-process (ulimit -f kills an over-size write)"
fi

# --- per-run cgroup limits via user systemd (if present) ----------------------
if have systemd-run; then
  if systemd-run --user --scope -p MemoryMax=268435456 --quiet /bin/true 2>/dev/null; then
    record cgroup_user PASS "systemd-run --user --scope MemoryMax works (per-run cgroup limits available)"
  else
    record cgroup_user FAIL "systemd-run --user unavailable; cgroup memory/pids limits fall back to ulimit+timeout"
  fi
else
  record cgroup_user INFO "systemd-run absent"
fi

# --- probe 1: unprivileged bwrap start (userns / unshare EPERM is the known risk)
if [ "$HAS_BWRAP" != yes ]; then
  record bwrap_start SKIP "bwrap not installed"
else
  err="$(bwrap "${BINDS[@]}" --proc /proc --dev /dev --tmpfs /tmp \
        --unshare-pid --unshare-net --unshare-ipc --unshare-uts \
        --die-with-parent /bin/true 2>&1)"
  if [ $? -eq 0 ]; then
    record bwrap_start PASS "sandbox entered and exited cleanly"
  else
    record bwrap_start FAIL "bwrap start failed: $(echo "$err" | tr '\n' ' ' | cut -c1-160)"
  fi
fi

# --- probe 2: read-only target, scratch-only write --------------------------
mkdir -p "$SCRATCH/target" "$SCRATCH/scratch"
echo secret > "$SCRATCH/target/secret.txt"
if [ "$HAS_BWRAP" != yes ]; then
  record fs_ro_scratch_rw SKIP "bwrap not installed"
else
  out="$(bwrap "${BINDS[@]}" --proc /proc --dev /dev \
        --ro-bind "$SCRATCH/target" /target --bind "$SCRATCH/scratch" /work \
        --unshare-net --die-with-parent /bin/bash -c '
          cat /target/secret.txt >/dev/null 2>&1        || { echo RO_READ_FAIL; exit 21; }
          echo hello > /work/ok.txt 2>/dev/null          || { echo SCRATCH_WRITE_FAIL; exit 22; }
          if { echo hacked > /target/evil.txt; } 2>/dev/null; then echo TARGET_WRITE_SUCCEEDED; exit 23; fi
          echo OK
        ' 2>&1)"
  case "$out" in
    *TARGET_WRITE_SUCCEEDED*) record fs_ro_scratch_rw FAIL "target was writable: $out" ;;
    *OK*)                     record fs_ro_scratch_rw PASS "target read-only, scratch writable, write to target blocked" ;;
    *)                        record fs_ro_scratch_rw FAIL "got: $out" ;;
  esac
fi

# --- probe 3: network isolation ---------------------------------------------
if [ "$HAS_BWRAP" != yes ]; then
  record net_isolation SKIP "bwrap not installed"
elif [ "$HAS_TIMEOUT" != yes ]; then
  record net_isolation SKIP "timeout(1) absent; cannot bound the egress attempt safely"
else
  out="$(bwrap "${BINDS[@]}" --proc /proc --dev /dev --unshare-net --die-with-parent /bin/bash -c '
        if command -v ip >/dev/null 2>&1; then
          ip -o link show 2>/dev/null | grep -qw eth0 && { echo NET_IFACE_UP; exit 31; }
        fi
        timeout 4 bash -c "exec 3<>/dev/tcp/1.1.1.1/443" 2>/dev/null && { echo EGRESS_OK; exit 32; }
        echo OK
      ' 2>&1)"
  if [ "$out" = "OK" ]; then
    record net_isolation PASS "no external iface; outbound connect failed; loopback-only namespace"
  else
    record net_isolation FAIL "got: $out"
  fi
fi

# --- probe 4: empty allowlisted environment ---------------------------------
if [ "$HAS_BWRAP" != yes ]; then
  record env_allowlist SKIP "bwrap not installed"
else
  out="$(bwrap "${BINDS[@]}" --proc /proc --dev /dev --unshare-net --die-with-parent \
        --clearenv --setenv PATH /usr/bin:/bin /bin/bash -c 'env | sed "s/=.*//" | sort -u' 2>&1)"
  extra="$(echo "$out" | grep -vx -e PATH -e PWD -e SHLVL -e _ -e OLDPWD || true)"
  if [ -z "$extra" ]; then
    record env_allowlist PASS "only PATH (plus shell builtins) present: [$(echo "$out" | tr '\n' ' ')]"
  else
    record env_allowlist FAIL "unexpected inherited vars: [$(echo "$extra" | tr '\n' ' ')]"
  fi
fi

# --- probe 5: resource limits ------------------------------------------------
if [ "$HAS_BWRAP" != yes ]; then
  record limits SKIP "bwrap not installed"
else
  out="$(bwrap "${BINDS[@]}" --proc /proc --dev /dev --unshare-net --die-with-parent \
        --bind "$SCRATCH/scratch" /work /bin/bash -c '
          ulimit -f 64 2>/dev/null && echo fset >/dev/null || echo f_noset
          ulimit -v 262144 2>/dev/null || echo v_noset
          ulimit -u 64 2>/dev/null || echo u_noset
          dd if=/dev/zero of=/work/big bs=1024 count=4096 >/dev/null 2>&1 \
             && echo FSIZE_NOT_ENFORCED || echo fsize_enforced
          echo OK
        ' 2>&1)"
  case "$out" in
    *fsize_enforced*) record limits PASS "ulimit file-size enforced in sandbox (cgroup delegation still unverified)" ;;
    *FSIZE_NOT_ENFORCED*) record limits FAIL "file-size ulimit not enforced ($out)" ;;
    *) record limits FAIL "unexpected: $out" ;;
  esac
  if [ "$HAS_TIMEOUT" = yes ]; then
    timeout 1 sleep 5 2>/dev/null && record wallclock FAIL "timeout did not kill an over-long child" \
                                  || record wallclock PASS "wall-clock bound killable via timeout(1)"
  fi
fi

# --- probe 6: promotion primitives (reject unsafe scratch entries) -----------
promote_ok() { # path -> 0 acceptable, 1 reject
  local p="$1" links
  [ -L "$p" ] && return 1
  [ -p "$p" ] && return 1
  [ -S "$p" ] && return 1
  [ -d "$p" ] && return 1
  [ -f "$p" ] || return 1
  links="$(stat -c '%h' "$p" 2>/dev/null)" || return 1
  [ "$links" = "1" ] || return 1
  return 0
}
S="$SCRATCH/scratch"
echo ok > "$S/good.txt"
ln -s /etc/passwd "$S/link"  2>/dev/null || true
mkfifo "$S/fifo" 2>/dev/null || true
echo hard > "$S/hard-src"
ln "$S/hard-src" "$S/hard"   2>/dev/null || true
mkdir -p "$S/dir"
head -c 2000 /dev/zero > "$S/oversize" 2>/dev/null || true
MAX_BYTES=1024

promo_check() { # fixture expect
  local f="$S/$1" expect="$2" got
  if [ ! -e "$f" ] && [ "$expect" = reject ]; then record "promote_$1" SKIP "fixture absent"; return; fi
  if promote_ok "$f"; then got=accept; else got=reject; fi
  if [ "$got" = "$expect" ]; then record "promote_$1" PASS "-> $got (expected)"
  else record "promote_$1" FAIL "-> $got (expected $expect)"; fi
}
promo_check good.txt accept
promo_check link     reject
promo_check fifo     reject
promo_check hard     reject
promo_check dir      reject
sz="$(stat -c '%s' "$S/oversize" 2>/dev/null || echo 0)"
if [ "$sz" -gt "$MAX_BYTES" ]; then record promote_oversize PASS "size $sz > cap $MAX_BYTES -> rejectable by byte bound"
else record promote_oversize FAIL "size $sz not exceeding cap $MAX_BYTES"; fi

# --- verdict -----------------------------------------------------------------
if [ "$OVERALL" -eq 1 ]; then
  VERDICT="NOT_ENFORCEABLE"
elif [ "$INCOMPLETE" -eq 1 ]; then
  if [ "$HAS_BWRAP" != yes ] && [ "$USERNSPASS" = yes ]; then
    VERDICT="ENFORCEABLE_PENDING_INSTALL"
  else
    VERDICT="INCOMPLETE"
  fi
else
  VERDICT="ENFORCEABLE"
fi

{
  echo "# sandbox POC result ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
  echo "host: $(uname -srm 2>/dev/null)"
  echo "verdict: $VERDICT"
  echo
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r n s d <<< "$r"
    printf '%-22s %-5s %s\n' "$n" "$s" "$d"
  done
} > "$HERE/RESULT.txt" 2>/dev/null || true

{
  printf '{\n  "verdict": "%s",\n  "host": "%s",\n  "probes": [\n' "$VERDICT" "$(uname -srm 2>/dev/null)"
  first=1
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r n s d <<< "$r"
    d="${d//\\/\\\\}"; d="${d//\"/\\\"}"
    [ "$first" -eq 0 ] && printf ',\n'
    first=0
    printf '    {"probe": "%s", "status": "%s", "detail": "%s"}' "$n" "$s" "$d"
  done
  printf '\n  ]\n}\n'
} > "$HERE/RESULT.json" 2>/dev/null || true

echo >&2
echo "VERDICT: $VERDICT" >&2
echo "written: $HERE/RESULT.txt, $HERE/RESULT.json" >&2
[ "$VERDICT" = "ENFORCEABLE" ] && exit 0 || exit 1
