#!/bin/bash

# ============================================
# StockerPro Cloud Workstation Memory Diagnostics
# Determine if Flutter build is being killed by OOM
# ============================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Memory & OOM Diagnostic Report"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================
# 1. System Memory Status
# ============================================

echo "📊 1. SYSTEM MEMORY STATUS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
free -h
echo ""
free -h | grep -i swap && echo "✅ Swap configured" || echo "⚠️  NO SWAP (potential bottleneck)"
echo ""

# ============================================
# 2. Memory Limits (Cgroups)
# ============================================

echo "📊 2. CGROUP MEMORY LIMITS (Container/Workstation Limits)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "/sys/fs/cgroup/memory/memory.limit_in_bytes" ]; then
    LIMIT=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null)
    if [ "$LIMIT" != "9223372036854771712" ] && [ -n "$LIMIT" ]; then  # Not unlimited
        LIMIT_GB=$(echo "scale=2; $LIMIT / 1024 / 1024 / 1024" | bc)
        echo "❌ MEMORY CGROUP LIMIT: ${LIMIT_GB}GB (workstation is memory-constrained)"
    else
        echo "✅ Memory cgroup: Unlimited"
    fi
else
    echo "⚠️  Unable to check cgroup limits (cgroups v2 or not accessible)"
fi
echo ""

# ============================================
# 3. Check for OOM Killer Events
# ============================================

echo "📊 3. OOM KILLER EVENTS (Past 50 lines)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check dmesg for recent OOM kills
if dmesg 2>/dev/null | grep -i "oom-kill" | tail -20; then
    echo ""
    echo "❌ OOM KILLER WAS TRIGGERED"
    echo "   This is likely why Flutter build was killed"
    echo ""
else
    echo "✅ No OOM killer events found in dmesg"
    echo ""
fi

# ============================================
# 4. Check System Logs
# ============================================

echo "📊 4. SYSTEM LOGS (Recent OOM entries)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

LOG_FOUND=false
if [ -f "/var/log/syslog" ]; then
    if grep -i "killed\|oom\|out of memory" /var/log/syslog | tail -10; then
        echo ""
        echo "❌ Found process termination logs in syslog"
        LOG_FOUND=true
    fi
fi

if [ "$LOG_FOUND" = false ] && [ -f "/var/log/messages" ]; then
    if grep -i "killed\|oom\|out of memory" /var/log/messages | tail -10; then
        echo ""
        echo "❌ Found process termination logs in messages"
        LOG_FOUND=true
    fi
fi

if [ "$LOG_FOUND" = false ]; then
    echo "✅ No OOM entries in standard logs"
fi
echo ""

# ============================================
# 5. Current Process Memory Usage
# ============================================

echo "📊 5. TOP MEMORY CONSUMERS (Current)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ps aux --sort=-%mem | head -10
echo ""

# ============================================
# 6. Disk Space (Writable Partitions)
# ============================================

echo "📊 6. WRITABLE DISK SPACE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
df -h | grep -E "^/dev|^/home|^/mnt|^tmpfs"
echo ""

# ============================================
# 7. Check /tmp Size
# ============================================

echo "📊 7. /tmp USAGE (Often a tmpfs RAM disk)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -d "/tmp" ]; then
    du -sh /tmp 2>/dev/null || echo "Unable to measure /tmp"
    df -h /tmp
else
    echo "No /tmp directory"
fi
echo ""
