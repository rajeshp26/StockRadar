// framework/opencode/plugin/bootstrap.test.mjs
// Unit harness for the install bootstrap (D5). Proves the `config(cfg)` hook injects the
// packaged surface into the LIVE config exactly as OpenCode requires, and that a missing
// surface is a no-op (never a crash).
//
// Run standalone:  node --test framework/opencode/plugin/bootstrap.test.mjs
// Run via g4:      npm test
//
// node:test + node:assert ONLY - no framework dependencies. Deterministic, <1s.
import { test, describe } from "node:test"
import assert from "node:assert/strict"
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { makeBootstrap, resolveSurface } from "./bootstrap.ts"

function makeSurface() {
  const root = mkdtempSync(join(tmpdir(), "bootstrap-"))
  mkdirSync(join(root, "skills", "demo"), { recursive: true })
  writeFileSync(join(root, "skills", "demo", "SKILL.md"), "---\nname: demo\n---\nbody\n")
  mkdirSync(join(root, "rules"))
  writeFileSync(join(root, "rules", "b-rule.md"), "rule b\n")
  writeFileSync(join(root, "rules", "a-rule.md"), "rule a\n")
  mkdirSync(join(root, "agents"))
  writeFileSync(join(root, "agents", "team-lead.md"), "you are team-lead\n")
  writeFileSync(join(root, "agents", "reviewer.md"), "you are reviewer\n")
  return root
}

describe("bootstrap config hook", () => {
  test("injects skills.paths, instructions, and agents from the resolved surface", async () => {
    const root = makeSurface()
    try {
      const plugin = makeBootstrap(() => root)
      const hooks = await plugin({ worktree: root })
      const cfg = {}
      await hooks.config(cfg)

      assert.deepEqual(cfg.skills.paths, [join(root, "skills")])
      assert.deepEqual(cfg.instructions, [join(root, "rules", "a-rule.md"), join(root, "rules", "b-rule.md")])
      assert.equal(cfg.agent["team-lead"].prompt, "you are team-lead\n")
      assert.equal(cfg.agent.reviewer.prompt, "you are reviewer\n")
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  test("is additive and idempotent - does not clobber host config or duplicate entries", async () => {
    const root = makeSurface()
    try {
      const plugin = makeBootstrap(() => root)
      const hooks = await plugin({ worktree: root })
      const cfg = { skills: { paths: ["/host/skills"] }, instructions: ["/host/AGENTS.md"], agent: {} }
      await hooks.config(cfg)
      await hooks.config(cfg)

      assert.deepEqual(cfg.skills.paths, ["/host/skills", join(root, "skills")])
      assert.deepEqual(cfg.instructions, ["/host/AGENTS.md", join(root, "rules", "a-rule.md"), join(root, "rules", "b-rule.md")])
      assert.equal(Object.keys(cfg.agent).length, 2)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  test("an app-defined agent of the same name is never overwritten", async () => {
    const root = makeSurface()
    try {
      const plugin = makeBootstrap(() => root)
      const hooks = await plugin({ worktree: root })
      const cfg = { agent: { reviewer: { prompt: "app override" } } }
      await hooks.config(cfg)
      assert.equal(cfg.agent.reviewer.prompt, "app override")
      assert.equal(cfg.agent["team-lead"].prompt, "you are team-lead\n")
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  test("missing surface is a no-op - never throws", async () => {
    const plugin = makeBootstrap(() => null)
    const hooks = await plugin({ worktree: "C:/does/not/exist" })
    const cfg = {}
    await hooks.config(cfg)
    assert.deepEqual(cfg, {})
  })
})

describe("resolveSurface - app-local precedence", () => {
  test("prefers the materialised <worktree>/.opencode surface over the packaged one", () => {
    const app = mkdtempSync(join(tmpdir(), "app-"))
    const prev = process.env.FRAMEWORK_SURFACE
    delete process.env.FRAMEWORK_SURFACE
    try {
      mkdirSync(join(app, ".opencode", "skills", "demo"), { recursive: true })
      writeFileSync(join(app, ".opencode", "skills", "demo", "SKILL.md"), "---\nname: demo\n---\n")
      assert.equal(resolveSurface({ worktree: app }), join(app, ".opencode"))
    } finally {
      if (prev !== undefined) process.env.FRAMEWORK_SURFACE = prev
      rmSync(app, { recursive: true, force: true })
    }
  })

  test("honours $FRAMEWORK_SURFACE before the app-local tree", () => {
    const app = mkdtempSync(join(tmpdir(), "app-"))
    const override = mkdtempSync(join(tmpdir(), "override-"))
    const prev = process.env.FRAMEWORK_SURFACE
    try {
      mkdirSync(join(app, ".opencode", "rules"), { recursive: true })
      process.env.FRAMEWORK_SURFACE = override
      assert.equal(resolveSurface({ worktree: app }), override)
    } finally {
      if (prev === undefined) delete process.env.FRAMEWORK_SURFACE
      else process.env.FRAMEWORK_SURFACE = prev
      rmSync(app, { recursive: true, force: true })
      rmSync(override, { recursive: true, force: true })
    }
  })
})
