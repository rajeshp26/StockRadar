'use client';

import { useState, useEffect } from 'react';
import { Upload, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePortfolioDashboard } from '../hooks/usePortfolio';
import { AccountChipStrip } from './AccountChipStrip';
import { TabBar } from './TabBar';
import { OverviewTab } from './OverviewTab';
import { PerformanceTab } from './PerformanceTab';
import { HoldingsTab } from './HoldingsTab';
import { DividendsTab } from './DividendsTab';
import { TransactionsTab } from './TransactionsTab';
import { AllocationTab } from './AllocationTab';
import { RiskPanel } from './RiskPanel';
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
    const { data: initialData, isLoading } = usePortfolioDashboard();

    useEffect(() => {
        console.time('[PERF] PortfolioTabShell mount → first paint');
        console.log('[PERF] PortfolioTabShell mounted');
    }, []);

    useEffect(() => {
        if (!isLoading && initialData) {
            console.timeEnd('[PERF] PortfolioTabShell mount → first paint');
            console.log(`[PERF] Dashboard data received: ${initialData.accounts.length} accounts, ${initialData.holdings.length} holdings, ${initialData.overview.total_value}`);
        }
    }, [isLoading, initialData]);
    const accounts = initialData?.accounts;

    const [showImportModal, setShowImportModal] = useState(false);
    const [showManualForm, setShowManualForm] = useState(false);

    const resolvedTab = initialTab ?? activeTab;

    const allAccountIds = accounts?.map(a => a.account_id);
    const accountIds = selectedAccountId ? [selectedAccountId] : allAccountIds;

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
            case 'risk':
                return <RiskPanel />;
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

            {/* Account chips — show skeleton while loading, render tabs immediately */}
            {isLoading ? (
                <Skeleton className="h-12 w-full" />
            ) : accounts && accounts.length > 0 ? (
                <AccountChipStrip
                    accounts={accounts}
                    selectedAccountId={selectedAccountId}
                    onSelect={setSelectedAccountId}
                />
            ) : null}

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
