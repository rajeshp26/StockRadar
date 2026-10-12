// framework/opencode/plugin/bootstrap.ts
// THE ONE committed OpenCode plugin an application repository needs.
//
// WHY THIS EXISTS
//   The framework surface (agents/, skills/, rules/) lives INSIDE the installed
//   `agentic-lifecycle` package, not in the application repo. OpenCode only auto-discovers
//   surface under `.opencode/`, so without a bridge the app sees ZERO framework agents,
//   skills, or rules. This plugin is that bridge.
//
// HOW (verified against @opencode-ai/plugin + @opencode-ai/sdk dist types in this repo)
//   - Plugin = (input, options?) => Promise<Hooks>; Hooks.config(cfg) receives the LIVE
//     Config object and mutates it in place (return value ignored).
//   - Config.skills.paths : string[]     -> extra roots scanned for **\/SKILL.md
//   - Config.instructions : string[]     -> extra instruction files
//   - Config.agent        : { [name]: AgentConfig } (open index signature)
//                                        -> inline agent definitions ({ prompt })
//
// PATH-AGNOSTIC ON PURPOSE (D8 forbids machine-specific absolute paths in committed files):
//   the surface is resolved at load time, never hard-coded, in this order:
//     1. $FRAMEWORK_SURFACE                       explicit override (dev tree / tests)
//     2. <worktree>/.opencode                     surface `framework init` materialised for
//                                                 this app; its @-includes are already
//                                                 rewritten, so it must win over the package
//     3. `python -c "import framework.opencode"`  installed package (install without init)
//     4. <worktree>/framework/opencode            source checkout (dev tree, no install)
//   If none resolves, config is left untouched - a missing framework must NEVER crash the host.
//
// MATERIALISED, NOT AUTHORED: `framework init` copies this file to <app>/.opencode/plugin/
//   and adds "./.opencode/plugin/bootstrap.ts" to the app opencode.json `plugin` array.
//   Do not hand-edit the app copy; re-run `framework init` to refresh it.
import type { Plugin, PluginInput } from "@opencode-ai/plugin"
import { execFileSync } from "node:child_process"
import { existsSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

const PY = process.platform === "win32" ? ["python", "python3"] : ["python3", "python"]

// Surface subdirectories, all optional and additive. Kept as data so the intent is greppable.
const SKILLS = "skills"
const RULES = "rules"
const AGENTS = "agents"

function mdFiles(dir: string): string[] {
  try {
    return readdirSync(dir).filter((f) => f.endsWith(".md")).sort()
  } catch {
    return []
  }
}

// Strategy 2: the framework is importable, so ask the interpreter where its surface is.
function installedSurface(): string | null {
  for (const py of PY) {
    try {
      const out = execFileSync(
        py,
        [
          "-c",
          "import framework.opencode,os,sys;sys.stdout.write(os.path.dirname(framework.opencode.__file__))",
        ],
        { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
      ).trim()
      if (out && existsSync(out)) return out
    } catch {
      // interpreter missing or package not installed - try the next interpreter
    }
  }
  return null
}

function hasSurface(root: string): boolean {
  return [SKILLS, RULES, AGENTS].some((d) => existsSync(join(root, d)))
}

export function resolveSurface(input?: PluginInput): string | null {
  const env = process.env.FRAMEWORK_SURFACE
  if (env && existsSync(env)) return env
  const base = input?.worktree || input?.directory || process.cwd()
  const appLocal = join(base, ".opencode")
  if (hasSurface(appLocal)) return appLocal
  const installed = installedSurface()
  if (installed) return installed
  const local = join(base, "framework", "opencode")
  return existsSync(local) ? local : null
}

// Injectable resolver: production resolves via the host; tests pass a fixture directory.
export function makeBootstrap(resolve: (input?: PluginInput) => string | null): Plugin {
  return async (input) => ({
    config: async (cfg) => {
      const surface = resolve(input)
      if (!surface) return

      const skillsDir = join(surface, SKILLS)
      if (existsSync(skillsDir)) {
        cfg.skills ??= {}
        cfg.skills.paths ??= []
        if (!cfg.skills.paths.includes(skillsDir)) cfg.skills.paths.push(skillsDir)
      }

      cfg.instructions ??= []
      for (const file of mdFiles(join(surface, RULES))) {
        const path = join(surface, RULES, file)
        if (!cfg.instructions.includes(path)) cfg.instructions.push(path)
      }

      const agentsDir = join(surface, AGENTS)
      const agentFiles = mdFiles(agentsDir)
      if (agentFiles.length) {
        cfg.agent ??= {}
        for (const file of agentFiles) {
          const name = file.replace(/\.md$/, "")
          if (cfg.agent[name]) continue // an app-defined agent of the same name wins
          cfg.agent[name] = { prompt: readFileSync(join(agentsDir, file), "utf8") }
        }
      }
    },
  })
}

export const BootstrapPlugin: Plugin = makeBootstrap(resolveSurface)

export default BootstrapPlugin
