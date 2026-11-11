// Reachability must be measured from the side the BROWSER runs on.
//
// Measured failure this exists for: a curl probe inside WSL reported the backend "reachable"
// (http://localhost:8001/health -> 200) while the Windows Next.js server proxying to
// http://127.0.0.1:8001 answered 502 "fetch failed" on every call. The browser runs on Windows,
// so a probe from WSL proves nothing about what the browser can reach -- worse, it inverts the
// verdict: a dead stack reads as live, the suite runs, fails, and a stack outage is recorded as
// a product failure. This script runs on the same side as the browser (node.exe) and exits
// non-zero when a dependency is not there.
//
// WHY IT RETRIES
// ==============
// Measured: a 5s single-shot probe reported the WSL-hosted backend as `BAD --- (The operation was
// aborted due to timeout)` twice, immediately after a long framework run, and the very next probe
// answered `200` in 25ms. The first Windows -> WSL TCP connection after an idle period is the slow
// one; the service was never down. A single short timeout therefore produced a false UNVERIFIABLE,
// which is the safe direction but still a flaky harness: the same stack reads as live or dead
// depending on how recently it was touched.
//
// So a timeout is retried with a longer deadline, and the retry is REPORTED. A dependency that is
// genuinely unreachable fails every attempt and still exits non-zero; a dependency that answers
// with an HTTP error is not retried at all.
//
// Usage: node probe-stack.js <url> [<url> ...]
// Exit: 0 every URL answered below 500 | 1 at least one did not | 2 no URLs given
const urls = process.argv.slice(2);
if (!urls.length) {
  console.error('probe-stack: no URLs given');
  process.exit(2);
}

// Escalating deadlines. Only a TIMEOUT is retried: an HTTP 4xx/5xx is an answer, and retrying it
// would turn a real error into a slow one.
const ATTEMPTS = [5000, 15000, 30000];

(async () => {
  let bad = 0;
  for (const url of urls) {
    let answered = false;
    for (let i = 0; i < ATTEMPTS.length; i++) {
      const timeout = ATTEMPTS[i];
      try {
        const res = await fetch(url, { signal: AbortSignal.timeout(timeout) });
        const ok = res.status < 500;
        const note = i ? ` (attempt ${i + 1}, ${timeout / 1000}s)` : '';
        console.log(`${ok ? 'OK  ' : 'BAD '} ${res.status} ${url}${note}`);
        if (!ok) bad++;
        answered = true;
        break;
      } catch (err) {
        const last = i === ATTEMPTS.length - 1;
        if (last) {
          console.log(`BAD   --- ${url} (${err.message}; ${ATTEMPTS.length} attempts)`);
          bad++;
          answered = true;
          break;
        }
        console.log(`RETRY --- ${url} (${err.message}; next deadline ${ATTEMPTS[i + 1] / 1000}s)`);
      }
    }
    if (!answered) bad++;
  }
  // Set the exit code instead of calling process.exit(): exiting from inside an async body
  // aborts libuv while a socket handle is still closing, which prints
  // "Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)" on Windows. The verdict is the
  // exit code, so it must not be dressed up as a crash.
  process.exitCode = bad ? 1 : 0;
})();
