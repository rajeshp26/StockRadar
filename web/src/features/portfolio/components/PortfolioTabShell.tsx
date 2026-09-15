'use client';

import { useState } from 'react';
import { Upload, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { usePortfolioDashboard } from '../hooks/usePortfolio';
import { usePortfolioNavigation } from '../hooks/usePortfolioNavigation';
import { TabBar } from './TabBar';
import { AccountNavDropdown } from './AccountNavDropdown';
import { OverviewTab } from './OverviewTab';
import { DividendsTab } from './DividendsTab';
import { TransactionsTab } from './TransactionsTab';
import { RiskPanel } from './RiskPanel';
import { ImportTransactionsModal } from './ImportTransactionsModal';
import { ManualTradeForm } from './ManualTradeForm';
import type { TabId } from '../types/portfolio.types';

interface PortfolioTabShellProps {
    initialTab?: TabId;
}

export function PortfolioTabShell({ initialTab }: PortfolioTabShellProps) {
    const { activeTab, selectedAccountId, setActiveTab, setSelectedAccountId } =
        usePortfolioNavigation();
    const { data: initialData, isLoading } = usePortfolioDashboard();
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
            case 'dividends':
                return <DividendsTab accountIds={accountIds} />;
            case 'transactions':
                return <TransactionsTab accountIds={accountIds} />;
            case 'risk':
                return <RiskPanel accountIds={accountIds} />;
            default:
                return <OverviewTab accountIds={accountIds} />;
        }
    };

    return (
        <div className="space-y-6">
            {/* Header with global account selector and action buttons */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold text-white">Portfolio</h2>
                    {isLoading ? (
                        <Skeleton className="h-10 w-56 rounded-xl" />
                    ) : accounts && accounts.length > 0 ? (
                        <AccountNavDropdown
                            accounts={accounts}
                            selectedAccountId={selectedAccountId}
                            onSelect={setSelectedAccountId}
                        />
                    ) : null}
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