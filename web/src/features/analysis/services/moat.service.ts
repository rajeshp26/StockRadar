// web/src/features/analysis/services/moat.service.ts
/**
 * Moat evidence & AI narrative service functions.
 * Uses the shared axios instance (api) for all HTTP requests.
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
  return path;
}

function errMessage(err: unknown): string {
  return (err as any)?.message || "Request failed";
}

/** GET — Moat keyword evidence. Optional refresh from EDGAR. */
export async function fetchMoatEvidence(
  symbol: string,
  refresh = false
): Promise<MoatEvidenceData> {
  const qs = refresh ? "?refresh=true" : "";
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/moat/evidence${qs}`);
  try {
    const resp = await api.get(url);
    const body = resp.data as MoatEvidenceData;
    if (body) return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
  throw new Error("Failed to load moat evidence.");
}

/** GET — Fetch cached AI narrative. */
export async function fetchMoatAiNarrative(
  symbol: string
): Promise<MoatAiNarrativeData> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/moat/ai`);
  try {
    const resp = await api.get(url);
    const body = resp.data as MoatAiNarrativeData;
    if (body) return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
  throw new Error("Failed to load AI narrative.");
}

/** POST — Generate AI narrative. */
export async function generateMoatAiNarrative(
  symbol: string
): Promise<MoatAiNarrativeData> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/moat/ai`);
  try {
    const resp = await api.post(url, {});
    const body = resp.data as MoatAiNarrativeData;
    if (body) return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
  throw new Error("Failed to generate AI narrative.");
}
