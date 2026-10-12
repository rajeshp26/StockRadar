#!/usr/bin/env node
/**
 * Deterministic npm-test entry point.
 *
 * npm test must run every declared suite or fail loudly. A glob that matched
 * nothing used to make `node --test` exit 0 with zero tests (a vacuous pass),
 * violating the framework's "zero checks executed is FAIL, never a pass" rule
 * (framework/gates/EXIT_CODES.md, Universal rules). This runner enumerates each
 * declared suite up front, refuses to start when a suite is missing or empty,
 * then delegates the collected files to `node --test`.
 *
 * Usage:
 *   node framework/tools/run_tests.mjs                  # normal run
 *   node framework/tools/run_tests.mjs --plugin-dir X   # override plugin suite root
 */
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";

const ROOT = resolve(import.meta.dirname, "..", "..");

// Declared suites. Each MUST contain at least one *.test.mjs file or the run
// refuses to start - a missing suite is a FAIL, never a silent skip.
const SUITES = [
  { name: "plugin", defaultDir: "framework/opencode/plugin" },
  { name: "experiments", defaultDir: "framework/experiments" },
];

function parseArgs(argv) {
  const out = { pluginDir: null };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--plugin-dir" && argv[i + 1]) {
      out.pluginDir = argv[i + 1];
      i += 1;
    }
  }
  return out;
}

function collect(root, relDir) {
  const dir = resolve(root, relDir);
  if (!existsSync(dir)) return { dir, files: null };
  const files = readdirSync(dir)
    .filter((name) => name.endsWith(".test.mjs"))
    .sort()
    .map((name) => join(dir, name));
  return { dir, files };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const suites = SUITES.map((suite) => ({
    name: suite.name,
    ...collect(ROOT, args.pluginDir && suite.name === "plugin" ? args.pluginDir : suite.defaultDir),
  }));

  for (const suite of suites) {
    if (suite.files === null || suite.files.length === 0) {
      console.error(
        `[run-tests] FATAL: declared suite '${suite.name}' has no *.test.mjs files at ${suite.dir}`,
      );
      console.error("[run-tests] zero checks executed for a declared suite is a FAIL, never a pass.");
      process.exit(1);
    }
  }

  const files = suites.flatMap((suite) => suite.files);
  console.log(`[run-tests] ${files.length} test file(s) across ${suites.length} declared suite(s):`);
  for (const suite of suites) {
    console.log(`  - ${suite.name}: ${suite.files.length} file(s) @ ${suite.dir}`);
  }
  console.log("[run-tests] delegating to node --test ...");

  const res = spawnSync(process.execPath, ["--test", ...files], { stdio: "inherit" });
  if (res.status !== 0) {
    console.error(
      `[run-tests] node --test exited ${res.status === null ? "(killed by signal)" : res.status}`,
    );
    process.exit(res.status ?? 1);
  }
  process.exit(0);
}

main();