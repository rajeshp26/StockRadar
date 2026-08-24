// Hand-authored transport. The generated file holds TYPES only and is never edited;
// this module supplies the call. Contract drift is caught by G1 comparing the generated
// file against the schema, so this layer cannot silently redefine the shape.
import type { RefreshRequest, RefreshResponse } from "@/contracts/api_004";

export type RefreshResult = RefreshResponse;

export async function refreshSession(body: RefreshRequest): Promise<RefreshResult> {
  const res = await fetch("/auth/refresh", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`refresh failed: ${res.status}`);
  return (await res.json()) as RefreshResult;
}
