import { tool } from "@opencode-ai/plugin"

/**
 * Context Builder — deterministic pointer resolver.
 *
 * HARD CONSTRAINT: prefer pointers over copied content. Materialise content only when the
 * consuming agent cannot reasonably retrieve it itself. Never read the repository broadly,
 * never summarise files the agent can open, never assemble a large context package.
 */
const EXCERPT_CAP_CHARS = 2000        // per materialised excerpt
const TOTAL_MATERIALISE_CAP = 8000    // per invocation

export default tool({
  description:
    "Resolve a task pointer set into paths, symbol locations, contract files and impact sets. " +
    "Returns pointers plus capped excerpts. Does not assemble context packages.",
  args: {
    task_id: tool.schema.string().describe("GSD task id, e.g. 03-02"),
    requirements: tool.schema.array(tool.schema.string()).optional(),
    contracts: tool.schema.array(tool.schema.string()).optional(),
    decisions: tool.schema.array(tool.schema.string()).optional(),
    symbols: tool.schema.array(tool.schema.string()).optional(),
    level: tool.schema.enum(["pointers", "targeted", "system"]).default("targeted"),
    impact_required: tool.schema.boolean().default(false),
  },
  async execute(args, ctx) {
    const sh = async (cmd: string) => {
      try { return (await ctx.$`bash -lc ${cmd}`.text()).trim() } catch { return "" }
    }

    const stateRoot = await sh("python3 framework/adapters/gsd_state.py state-root")
    const plan = await sh(
      `python3 framework/adapters/gsd_state.py plan-path --task ${args.task_id}`)

    const out: any = {
      task_id: args.task_id,
      level: args.level,
      pointers: {
        plan,
        requirements: (args.requirements ?? []).map(id => ({ id, resolve: `gsd_state.py requirement --id ${id}` })),
        contracts: (args.contracts ?? []).map(id => ({ id, schema: `${stateRoot}/contracts/${id.toLowerCase()}.openapi.yaml` })),
        decisions: (args.decisions ?? []).map(id => ({ id, path: `${stateRoot}/decisions/${id}.md` })),
      },
      symbols: [] as any[],
      impact: null as any,
      materialised_chars: 0,
      truncated: [] as string[],
      provider_tier: await sh("python3 framework/adapters/code_intel.py tier --capability relationships"),
    }

    // Symbol locations only — never bodies.
    for (const s of args.symbols ?? []) {
      const loc = await sh(`python3 framework/adapters/code_intel.py locate --symbol '${s}'`)
      out.symbols.push({ symbol: s, location: loc || "unresolved" })
    }

    if (args.impact_required || args.level === "system") {
      out.impact = {
        set: await sh(`python3 framework/adapters/code_intel.py impact --task ${args.task_id}`),
        affected_tests: await sh(`python3 framework/adapters/code_intel.py affected-tests --task ${args.task_id}`),
        freshness: await sh("python3 framework/adapters/code_intel.py freshness"),
      }
    }

    // Materialise ONLY the contract schemas, which the agent must match exactly.
    if (args.level !== "pointers") {
      for (const c of out.pointers.contracts) {
        if (out.materialised_chars >= TOTAL_MATERIALISE_CAP) { out.truncated.push(c.id); continue }
        const body = await sh(`head -c ${EXCERPT_CAP_CHARS} ${c.schema} 2>/dev/null`)
        if (!body) continue
        c.excerpt = body
        out.materialised_chars += body.length
      }
    }

    out.instruction =
      "Retrieve what you need from these pointers yourself. Confirm sufficiency before acting; " +
      "if a critical item is unreadable, return CONTEXT_INSUFFICIENT naming it."
    return JSON.stringify(out, null, 2)
  },
})
