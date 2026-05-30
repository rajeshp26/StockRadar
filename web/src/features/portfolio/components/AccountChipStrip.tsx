'use client';

import { cn } from '@/lib/utils';
import type { PortfolioAccount } from '../types/portfolio.types';

interface AccountChipStripProps {
    accounts: PortfolioAccount[];
    selectedAccountId: number | null;
    onSelect: (accountId: number | null) => void;
    totalValue?: number;
}

export function AccountChipStrip({
    accounts,
    selectedAccountId,
    onSelect,
    totalValue,
}: AccountChipStripProps) {
    const allValue = accounts.reduce((sum, a) => sum + (a.total_value || 0), 0);

    return (
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
            <button
                onClick={() => onSelect(null)}
                className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold transition-all whitespace-nowrap border',
                    selectedAccountId === null
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-transparent text-white/60 border-white/10 hover:border-white/20 hover:text-white/80'
                )}
            >
                All Accounts
                <span className={cn(
                    'text-xs font-normal',
                    selectedAccountId === null ? 'text-blue-200' : 'text-white/30'
                )}>
                    ${(totalValue ?? allValue).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
            </button>

            {accounts.map((account) => {
                const isSelected = selectedAccountId === account.account_id;
                return (
                    <button
                        key={account.account_id}
                        onClick={() => onSelect(account.account_id)}
                        className={cn(
                            'flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold transition-all whitespace-nowrap border',
                            isSelected
                                ? 'bg-blue-600 text-white border-blue-600'
                                : 'bg-transparent text-white/60 border-white/10 hover:border-white/20 hover:text-white/80'
                        )}
                    >
                        {account.account_type}
                        <span className={cn(
                            'text-xs font-normal',
                            isSelected ? 'text-blue-200' : 'text-white/30'
                        )}>
                            ${(account.total_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </span>
                    </button>
                );
            })}
        </div>
    );
}
