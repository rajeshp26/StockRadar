// web/src/features/portfolio/hooks/usePortfolio.ts

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useServices } from "@/shared/contexts/ServiceContext";
import { useToast } from "@/hooks/use-toast";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import type {
    Brokerage,
    PortfolioAccount,
    PortfolioOverview,
    Holding,
    ImportTransactionsRequest,
    ImportStatusResponse,
} from "../types/portfolio.types";

/**
 * Hook for portfolio overview data
 */
export function usePortfolioOverview() {
    const { portfolioService } = useServices();

    return useQuery<PortfolioOverview, Error>({
        queryKey: QK.portfolioOverview(),
        queryFn: () => portfolioService.getPortfolioOverview(),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        refetchOnWindowFocus: true,
    });
}

/**
 * Hook for user's portfolio accounts
 */
export function usePortfolioAccounts() {
    const { portfolioService } = useServices();

    return useQuery<PortfolioAccount[], Error>({
        queryKey: QK.portfolioAccounts(),
        queryFn: () => portfolioService.getAccounts(),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        refetchOnWindowFocus: true,
    });
}

/**
 * Hook for holdings across all accounts
 */
export function useAllHoldings() {
    const { portfolioService } = useServices();

    return useQuery<Holding[], Error>({
        queryKey: QK.portfolioHoldings(),
        queryFn: () => portfolioService.getAllHoldings(),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        refetchOnWindowFocus: true,
    });
}

/**
 * Hook for account-specific holdings
 */
export function useAccountHoldings(accountId: number | null) {
    const { portfolioService } = useServices();

    return useQuery({
        queryKey: QK.portfolioAccountHoldings(accountId!),
        queryFn: () => portfolioService.getAccountHoldings(accountId!),
        enabled: accountId !== null,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

/**
 * Hook for supported brokerages
 */
export function useBrokerages() {
    const { portfolioService } = useServices();

    return useQuery<Brokerage[], Error>({
        queryKey: QK.portfolioBrokerages(),
        queryFn: () => portfolioService.getBrokerages(),
        staleTime: STALE.STATIC, // Brokerages rarely change
        gcTime: GC.STATIC,
        retry: 1,
    });
}

/**
 * Hook for importing transactions
 */
export function useImportTransactions() {
    const { portfolioService } = useServices();
    const { toast } = useToast();

    return useMutation({
        mutationFn: async (request: ImportTransactionsRequest) => {
            return portfolioService.importTransactions(request);
        },
        onError: (error: Error) => {
            toast({
                title: "Import Error",
                description: error.message || "An error occurred during import",
                variant: "destructive",
            });
        },
    });
}

/**
 * Hook for deleting an account
 */
export function useDeleteAccount() {
    const { portfolioService } = useServices();
    const queryClient = useQueryClient();
    const { toast } = useToast();

    return useMutation({
        mutationFn: (accountId: number) => portfolioService.deleteAccount(accountId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: QK.portfolioOverview() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioAccounts() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioHoldings() });

            toast({
                title: "Account Deleted",
                description: "Account and all associated data have been removed.",
            });
        },
        onError: (error: Error) => {
            toast({
                title: "Delete Failed",
                description: error.message || "Failed to delete account",
                variant: "destructive",
            });
        },
    });
}

/**
 * Hook for polling import job status
 */
export function useImportStatus(importBatchId: string | null) {
    const { portfolioService } = useServices();

    return useQuery<ImportStatusResponse, Error>({
        queryKey: ['portfolio', 'import-status', importBatchId],
        queryFn: () => portfolioService.getImportStatus(importBatchId!),
        enabled: !!importBatchId,
        refetchInterval: (query) => {
            const status = query.state.data?.status;
            if (status === 'completed' || status === 'failed') {
                return false;
            }
            return 2000;
        },
        staleTime: 1000,
        gcTime: 0,
    });
}