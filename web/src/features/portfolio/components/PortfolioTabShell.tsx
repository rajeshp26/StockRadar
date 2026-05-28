'use client';

import { useState } from 'react';
import { Upload, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePortfolioAccounts } from '../hooks/usePortfolio';
import { AccountChipStrip } from './AccountChipStrip';
import { TabBar } from './TabBar';
import { OverviewTab } from './OverviewTab';
import { PerformanceTab } from './PerformanceTab';
import { HoldingsTab } from './HoldingsTab';
import { DividendsTab } from './DividendsTab';
import { TransactionsTab } from './TransactionsTab';
import { AllocationTab } from './AllocationTab';
import { ImportTransactionsModal } from './ImportTransactionsModal';
import { ManualTradeForm } from './ManualTradeForm';
import { usePortfolioNavigation } from '../hooks/usePortfolioNavigation';
import { Skeleton } from '@/components/ui/skeleton';
import type { TabId } from '../types/portfolio.types';

interface PortfolioTabShellProps {
    initialTab?: TabId;
}

export function PortfolioTabShell({ initialTab }: PortfolioTabShellProps) {
    const { activeTab, selectedAccountId, setActiveTab, setSelectedAccountId } =
        usePortfolioNavigation();
    const { data: accounts, isLoading: accountsLoading } = usePortfolioAccounts();

    const [showImportModal, setShowImportModal] = useState(false);
    const [showManualForm, setShowManualForm] = useState(false);

    const resolvedTab = initialTab ?? activeTab;

    const accountIds = selectedAccountId ? [selectedAccountId] : undefined;

    if (accountsLoading) {
        return (
            <div className="space-y-6">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-96 w-full" />
            </div>
        );
    }

    const renderTab = () => {
        switch (resolvedTab) {
            case 'overview':
                return <OverviewTab accountIds={accountIds} />;
            case 'performance':
                return <PerformanceTab accountIds={accountIds} />;
            case 'holdings':
                return <HoldingsTab accountIds={accountIds} />;
            case 'dividends':
                return <DividendsTab accountIds={accountIds} />;
            case 'transactions':
                return <TransactionsTab accountIds={accountIds} />;
            case 'allocation':
                return <AllocationTab accountIds={accountIds} />;
            default:
                return <OverviewTab accountIds={accountIds} />;
        }
    };

    return (
        <div className="space-y-6">
            {/* Header with action buttons */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <h2 className="text-xl font-bold text-white">Portfolio</h2>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        className="glass-button-secondary"
                        onClick={() => setShowManualForm(true)}
                    >
                        <Plus className="mr-2 h-4 w-4" />
                        Add Trade
                    </Button>
                    <Button
                        className="glass-button"
                        onClick={() => setShowImportModal(true)}
                    >
                        <Upload className="mr-2 h-4 w-4" />
                        Import CSV
                    </Button>
                </div>
            </div>

            {accounts && accounts.length > 0 && (
                <AccountChipStrip
                    accounts={accounts}
                    selectedAccountId={selectedAccountId}
                    onSelect={setSelectedAccountId}
                />
            )}

            <TabBar activeTab={resolvedTab} onTabChange={setActiveTab} />

            {renderTab()}

            <ImportTransactionsModal
                open={showImportModal}
                onOpenChange={setShowImportModal}
            />
            <ManualTradeForm
                open={showManualForm}
                onOpenChange={setShowManualForm}
            />
        </div>
    );
}
