// framework/experiments/plan.mjs
// Deterministic experiment plan builder (P3 increment 3).
//
// The manifest is the experimental specification; the plan is derived from it
// mechanically and reproducibly: same manifest + corpus + seed -> byte-identical
// plan. A/B assignment comes from the manifest/scheduler here - never from the
// worker. The plan is pure: no I/O, no randomness beyond the seeded PRNG.
export function mulberry32(seed) {
  let a = seed >>> 0
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function buildPlan(manifest, corpus) {
  if (!manifest || !Array.isArray(manifest.conditions) || manifest.conditions.length !== 2) {
    throw new Error("plan: manifest must declare exactly two conditions (A, B)")
  }
  if (!corpus || !Array.isArray(corpus.tasks) || corpus.tasks.length === 0) {
    throw new Error("plan: corpus must declare at least one task")
  }
  if (typeof manifest.seed !== "number" || !Number.isInteger(manifest.seed)) {
    throw new Error("plan: manifest must declare an integer seed")
  }
  const condA = manifest.conditions.find((c) => c.id === "A")
  const condB = manifest.conditions.find((c) => c.id === "B")
  if (!condA || !condB) throw new Error("plan: conditions must be A and B")
  const total = condA.runs + condB.runs
  if (total < 1) throw new Error("plan: zero runs scheduled")

  // Arm assignment: exactly condA.runs x A and condB.runs x B, order deterministically
  // shuffled by the manifest seed. The worker never sees this list.
  const arms = []
  for (let i = 0; i < condA.runs; i++) arms.push("A")
  for (let i = 0; i < condB.runs; i++) arms.push("B")
  const rand = mulberry32(manifest.seed)
  for (let i = arms.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[arms[i], arms[j]] = [arms[j], arms[i]]
  }

  // Run identity and task assignment are both manifest/corpus-derived. Tasks cycle
  // so both arms see the same task multiset (task drift cannot confound the arm).
  const runs = []
  for (let i = 0; i < total; i++) {
    const runOrder = i + 1
    const arm = arms[i]
    const cond = arm === "A" ? condA : condB
    const task = corpus.tasks[i % corpus.tasks.length]
    runs.push({
      run_id: `R-${String(runOrder).padStart(4, "0")}`,
      run_order: runOrder,
      arm,
      profile: cond.profile,
      task_id: task.id,
      task_type: task.type,
      task_name: task.name,
    })
  }
  return { runs, total }
}

// Plan digest: stable string for ledger/dataset consistency checks.
export function planDigest(plan) {
  return plan.runs.map((r) => `${r.run_id}:${r.arm}:${r.profile}:${r.task_id}`).join("\n")
}
