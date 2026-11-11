// Extract the JSON document from a stream that has log lines in front of it.
//
// SUPERSEDED for the AC-7 harness: g6 now runs the browser and records its own per-run log as
// the artifact (framework/verifier/fixtures/run-ac7-real.sh), so nothing in that path consumes a
// JSON report. Kept because the behaviour it works around is still true of Playwright and a
// future reader who reaches for `--reporter=json` will hit it.
//
// Measured need: Playwright's `--reporter=json` writes the report to stdout, but the suite's
// global-setup logs `[E2E] Navigating to login page ...` with console.log first. Redirecting
// stdout to a file therefore produces a file that starts with `[E2E] ...` and is not valid JSON,
// so the recorded evidence artifact cannot be parsed by anything downstream. The matrix hashes
// whatever it is given, so a broken artifact still "binds" -- the shape has to be right at the
// point of capture.
//
// Usage: node pluck-json.js <input> <output>
// Exit: 0 a JSON document was written | 1 no JSON document found
const fs = require('fs');

const [input, output] = process.argv.slice(2);
if (!input || !output) {
  console.error('pluck-json: usage: pluck-json.js <input> <output>');
  process.exit(2);
}

const raw = fs.readFileSync(input, 'utf8');
const start = raw.indexOf('{');
if (start < 0) {
  console.error('pluck-json: no JSON object found in ' + input);
  process.exit(1);
}

const body = raw.slice(start);
try {
  JSON.parse(body);
} catch (err) {
  console.error('pluck-json: trailing content is not valid JSON: ' + err.message);
  process.exit(1);
}

fs.writeFileSync(output, body.endsWith('\n') ? body : body + '\n', 'utf8');
process.exitCode = 0;
