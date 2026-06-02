// web/src/features/super-investors/services/super-investors-page.service.ts
// Service layer for the standalone /super-investors page.
// Follows the same doFetch + readJsonSafe pattern as analysis.service.ts.

import type {
    OverviewData,
    TopStocksData,
    OverlapData,
    ActivityData,
    InvestorsListData,
    InvestorPortfolioData,
    SectorsData,
} from "../types/super-investors-page.types";

const DEFAULT_TIMEOUT_MS = 20_000;

function apiPath(path: string): string {
    return `/api/proxy${path}`;
}

async function doFetch(
    input: RequestInfo,
    init: RequestInit = {},
    timeoutMs: number = DEFAULT_TIMEOUT_MS
): Promise<Response> {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(input, {
            credentials: "include",
            cache: "no-store",
            signal: controller.signal,
            ...init,
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
                ...(init.headers || {}),
            },
        });
    } finally {
        clearTimeout(id);
    }
}

async function readJsonSafe<T>(res: Response): Promise<T | null> {
    try {
        return (await res.json()) as T;
    } catch {
        return null;
    }
}

async function getOrThrow<T>(url: string, timeoutMs?: number): Promise<T> {
    let res: Response;
    try {
        res = await doFetch(url, { method: "GET" }, timeoutMs);
    } catch (err: any) {
        throw new Error(err?.message || "Network error.");
    }
    if (res.ok) {
        const body = await readJsonSafe<T>(res);
        if (!body) throw new Error("Invalid response from server.");
        return body;
    }
    const errorBody = (await readJsonSafe<{ detail?: string }>(res)) || {};
    throw new Error(
        errorBody?.detail || `Request failed with status ${res.status}`
    );
}

// ── Overview ─────────────────────────────────────────────────────────────────

export async function fetchSuperInvestorsOverview(): Promise<OverviewData> {
    return getOrThrow<OverviewData>(apiPath("/super-investors/overview"));
}

// ── Top Stocks ───────────────────────────────────────────────────────────────

export interface TopStocksParams {
    sector?: string;
    style?: string;
    minInvestors?: number;
    limit?: number;
}

export async function fetchTopStocks(
    params: TopStocksParams = {}
): Promise<TopStocksData> {
    const qs = new URLSearchParams();
    if (params.sector) qs.set("sector", params.sector);
    if (params.style) qs.set("style", params.style);
    if (params.minInvestors) qs.set("min_investors", String(params.minInvestors));
    if (params.limit) qs.set("limit", String(params.limit));
    const query = qs.toString() ? `?${qs}` : "";
    return getOrThrow<TopStocksData>(
        apiPath(`/super-investors/top-stocks${query}`)
    );
}

// ── Overlap ───────────────────────────────────────────────────────────────────

export interface OverlapParams {
    minInvestors?: number;
    sector?: string;
    limit?: number;
}

export async function fetchOverlap(
    params: OverlapParams = {}
): Promise<OverlapData> {
    const qs = new URLSearchParams();
    if (params.minInvestors) qs.set("min_investors", String(params.minInvestors));
    if (params.sector) qs.set("sector", params.sector);
    if (params.limit) qs.set("limit", String(params.limit));
    const query = qs.toString() ? `?${qs}` : "";
    return getOrThrow<OverlapData>(apiPath(`/super-investors/overlap${query}`));
}

// ── Activity ──────────────────────────────────────────────────────────────────

export interface ActivityParams {
    changeType?: string;
    investorTag?: string;
    quarters?: number;
    limit?: number;
}

export async function fetchActivity(
    params: ActivityParams = {}
): Promise<ActivityData> {
    const qs = new URLSearchParams();
    if (params.changeType) qs.set("change_type", params.changeType);
    if (params.investorTag) qs.set("investor_tag", params.investorTag);
    if (params.quarters) qs.set("quarters", String(params.quarters));
    if (params.limit) qs.set("limit", String(params.limit));
    const query = qs.toString() ? `?${qs}` : "";
    return getOrThrow<ActivityData>(apiPath(`/super-investors/activity${query}`));
}

// ── Investors list ────────────────────────────────────────────────────────────

export async function fetchInvestorsList(): Promise<InvestorsListData> {
    return getOrThrow<InvestorsListData>(apiPath("/super-investors/investors"));
}

// ── Individual investor ───────────────────────────────────────────────────────

export async function fetchInvestorPortfolio(
    tag: string,
    quarters: number = 8
): Promise<InvestorPortfolioData> {
    return getOrThrow<InvestorPortfolioData>(
        apiPath(
            `/super-investors/investors/${encodeURIComponent(tag)}?quarters=${quarters}`
        )
    );
}

// ── Sectors ───────────────────────────────────────────────────────────────────

export async function fetchSectors(style?: string): Promise<SectorsData> {
    const qs = style ? `?style=${encodeURIComponent(style)}` : "";
    return getOrThrow<SectorsData>(apiPath(`/super-investors/sectors${qs}`));
}