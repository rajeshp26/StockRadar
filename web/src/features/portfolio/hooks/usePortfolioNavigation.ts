'use client';

import { useSearchParams, useRouter } from 'next/navigation';
import { useCallback, useMemo } from 'react';
import type { TabId } from '../types/portfolio.types';

const DEFAULT_TAB: TabId = 'overview';

export function usePortfolioNavigation() {
    const searchParams = useSearchParams();
    const router = useRouter();

    const activeTab = useMemo(() => {
        const tab = searchParams.get('tab') as TabId | null;
        return tab ?? DEFAULT_TAB;
    }, [searchParams]);

    const selectedAccountId = useMemo(() => {
        const id = searchParams.get('account');
        return id ? Number(id) : null;
    }, [searchParams]);

    const setActiveTab = useCallback(
        (tab: TabId) => {
            const params = new URLSearchParams(searchParams.toString());
            params.set('tab', tab);
            router.replace(`?${params.toString()}`, { scroll: false });
        },
        [router, searchParams]
    );

    const setSelectedAccountId = useCallback(
        (accountId: number | null) => {
            const params = new URLSearchParams(searchParams.toString());
            if (accountId) {
                params.set('account', String(accountId));
            } else {
                params.delete('account');
            }
            router.replace(`?${params.toString()}`, { scroll: false });
        },
        [router, searchParams]
    );

    const getAccountUrl = useCallback(
        (accountId: number) => {
            const params = new URLSearchParams(searchParams.toString());
            params.set('account', String(accountId));
            params.set('tab', 'overview');
            return `?${params.toString()}`;
        },
        [searchParams]
    );

    return {
        activeTab,
        selectedAccountId,
        setActiveTab,
        setSelectedAccountId,
        getAccountUrl,
    };
}
