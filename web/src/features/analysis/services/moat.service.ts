// web/src/features/analysis/services/moat.service.ts
/**
 * Moat evidence & AI narrative service functions.
 */
import { api } from "@/lib/api";

type Json = Record<string, any>;

export interface MoatEvidenceData {
  symbol: string;
  company_id: number;
  text_analysis_available: boolean;
  filing_type: string | null;
  filing_date: string | null;
  total_keyword_matches: number;
  groups_found: string[];
  evidence_by_group: Record<
    string,
    {
      keyword: string;
      keyword_group: string;
      section: string;
      snippet: string | null;
      relevance_score: number;
      filing_date: string | null;
    }[]
  >;
}

export interface MoatAiNarrativeData {
  symbol: string;
  company_id: number;
  narrative: {
    narrative: string;
    summary: string | null;
    model: string;
    generated_at: string;
    generation_time_ms: number | null;
  };
  available: boolean;
}

function apiPath(path: string): string {
  return `/api/proxy${path}`;
}

async function doFetch(
  input: RequestInfo,
  init: RequestInit = {}
): Promise<Response> {
  return fetch(input, {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
}

async function readJsonSafe<T = Json>(res: Response): Promise<T | null> {
  try {
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** GET — Moat keyword evidence. Optional refresh from EDGAR. */
export async function fetchMoatEvidence(
  symbol: string,
  refresh = false
): Promise<MoatEvidenceData> {
  const qs = refresh ? "?refresh=true" : "";
  const url = apiPath(
    `/analysis/${encodeURIComponent(symbol)}/moat/evidence${qs}`
  );
  const res = await doFetch(url, { method: "GET" });
  if (res.ok) {
    const body = await readJsonSafe<MoatEvidenceData>(res);
    if (body) return body;
  }
  throw new Error("Failed to load moat evidence.");
}

/** GET — Fetch cached AI narrative. */
export async function fetchMoatAiNarrative(
  symbol: string
): Promise<MoatAiNarrativeData> {
  const url = apiPath(
    `/analysis/${encodeURIComponent(symbol)}/moat/ai`
  );
  const res = await doFetch(url, { method: "GET" });
  if (res.ok) {
    const body = await readJsonSafe<MoatAiNarrativeData>(res);
    if (body) return body;
  }
  throw new Error("Failed to load AI narrative.");
}

/** POST — Generate AI narrative. */
export async function generateMoatAiNarrative(
  symbol: string
): Promise<MoatAiNarrativeData> {
  const url = apiPath(
    `/analysis/${encodeURIComponent(symbol)}/moat/ai`
  );
  const res = await doFetch(url, { method: "POST" });
  if (res.ok) {
    const body = await readJsonSafe<MoatAiNarrativeData>(res);
    if (body) return body;
  }
  throw new Error("Failed to generate AI narrative.");
}
