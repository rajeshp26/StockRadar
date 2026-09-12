// framework/experiments/blinding.mjs
// Blinding layer for the P3 A/B experiment (DID-009, P3-EXPERIMENT-INTEGRITY
// "Blinding rule"). The recorder runs with an explicit per-run arm label
// (RUN_VALIDITY scores that); what is FROZEN and what a future comparator
// reads is an opaque dataset in which the arm label exists only as an
// authenticated token. No analysis - human or agent - can know run N = A or B
// until the key is revealed after freeze.
//
// Properties (each is a contract test in blinding.test.mjs):
//   - round-trip:   reveal(encode(D, key), key) === D                 (arms back)
//   - run binding:  tokens are bound to run_id; swapping tokens between
//                   records FAILS AAD authentication during reveal
//   - tamper:       any token removed/edited/foreign -> loud failure
//   - determinism:  encode(D, key) is byte-identical across calls
//   - key honesty:  wrong key -> GCM auth failure, never a wrong answer
//   - opaqueness:   token length is constant for all runs and arms; the
//                   token content is AES-256-GCM ciphertext, not the arm
//
// Key handling is deliberately external: the caller derives a key with
// deriveKey(secret, salt) and stores it where the comparator reaches it only
// after freeze (out of scope here - the recorder/comparator increments).
// This module never reads files and never touches the filesystem.
import { createCipheriv, createDecipheriv, scryptSync, createHash, randomBytes } from "node:crypto"

const NONCE_BYTES = 12
const PAD = 8 // fixed plaintext width -> uniform token length for arms A and B

export function deriveKey(secret, salt, length = 32) {
  return scryptSync(String(secret), String(salt), length)
}

// Fresh random secret (32 bytes, base64) for the caller to persist where the
// comparator reaches it only after freeze. Not used by encode itself.
export function generateSecret() {
  return randomBytes(32).toString("base64")
}

function nonceFor(runId) {
  return createHash("sha256").update(String(runId)).digest().subarray(0, NONCE_BYTES)
}

function padArm(arm) {
  const s = String(arm)
  if (s.length > PAD) throw new Error(`blinding: arm label too long: ${s}`)
  return Buffer.from(s.padEnd(PAD, " "), "utf8")
}

function unpad(buf) {
  return buf.toString("utf8").replace(/ +$/, "")
}

export function encodeRun(key, runId, arm) {
  if (!key) throw new Error("blinding: encodeRun requires a key")
  if (runId === undefined || runId === null || String(runId).length === 0) {
    throw new Error("blinding: encodeRun requires a non-empty runId")
  }
  if (arm === undefined || arm === null || String(arm).length === 0) {
    throw new Error("blinding: encodeRun requires a non-empty arm")
  }
  const nonce = nonceFor(runId)
  const cipher = createCipheriv("aes-256-gcm", key, nonce)
  cipher.setAAD(Buffer.from(String(runId), "utf8"))
  const ct = Buffer.concat([cipher.update(padArm(arm)), cipher.final()])
  const tag = cipher.getAuthTag()
  return Buffer.concat([tag, ct]).toString("base64")
}

export function revealRun(key, runId, token) {
  if (key === undefined || key === null) throw new Error("blinding: revealRun requires a key")
  if (runId === undefined || runId === null || String(runId).length === 0) {
    throw new Error("blinding: revealRun requires a non-empty runId")
  }
  if (typeof token !== "string" || token.length === 0) {
    throw new Error("blinding: revealRun requires a token string")
  }
  const raw = Buffer.from(token, "base64")
  if (raw.length < 16 + 1) throw new Error("blinding: revealRun malformed token")
  const tag = raw.subarray(0, 16)
  const ct = raw.subarray(16)
  const decipher = createDecipheriv("aes-256-gcm", key, nonceFor(runId))
  decipher.setAAD(Buffer.from(String(runId), "utf8"))
  decipher.setAuthTag(tag)
  const pt = Buffer.concat([decipher.update(ct), decipher.final()]) // may throw on auth failure
  return unpad(pt)
}

// Dataset in -> blinded dataset out. Every record keeps its full contents;
// only the plaintext `arm` is replaced by an opaque `arm_token`.
export function encodeDataset(key, dataset) {
  if (!Array.isArray(dataset)) throw new Error("blinding: dataset must be an array of run records")
  const encoded = dataset.map((rec) => {
    if (!rec || typeof rec !== "object") throw new Error("blinding: each record must be an object")
    if (rec.run_id === undefined || rec.run_id === null || String(rec.run_id).length === 0) {
      throw new Error(`blinding: record lacks run_id`)
    }
    if (rec.arm === undefined || rec.arm === null || String(rec.arm).length === 0) {
      throw new Error(`blinding: record ${rec.run_id} lacks arm`)
    }
    const token = encodeRun(key, rec.run_id, rec.arm)
    const { arm, ...rest } = rec
    return { ...rest, arm_token: token }
  })
  return { dataset: encoded, opaque: true, armed: false }
}

// Blinded dataset -> explicit dataset (arms restored). Refuses malformed or
// tampered input and refuses to invent an answer: wrong key or wrong run_id
// binding throws instead of returning a guess.
export function revealDataset(key, blinded) {
  if (!blinded || !Array.isArray(blinded.dataset)) {
    throw new Error("blinding: revealDataset requires { dataset: [...] }")
  }
  const out = blinded.dataset.map((rec) => {
    if (!rec || typeof rec !== "object") throw new Error("blinding: each record must be an object")
    if (typeof rec.arm_token !== "string" || rec.arm_token.length === 0) {
      throw new Error(`blinding: record ${String(rec.run_id)} lacks arm_token`)
    }
    if (rec.arm !== undefined) throw new Error(`blinding: record ${String(rec.run_id)} already carries a plaintext arm`)
    const arm = revealRun(key, rec.run_id, rec.arm_token)
    const { arm_token, ...rest } = rec
    return { ...rest, arm }
  })
  return out
}
