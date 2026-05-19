// web/src/features/portfolio/components/PortfolioEntrySelector.tsx
'use client';

import { useState } from 'react';
import { Upload, Plus, FileText } from 'lucide-react';
import { ImportTransactionsModal } from './ImportTransactionsModal';
import { ManualTradeForm } from './ManualTradeForm';
import { cn } from '@/lib/utils';

interface PortfolioEntrySelectorProps {
    onClose?: () => void;
}

export function PortfolioEntrySelector({ onClose }: PortfolioEntrySelectorProps) {
    const [showImport, setShowImport] = useState(false);
    const [showManual, setShowManual] = useState(false);

    const handleImportClick = () => {
        setShowImport(true);
    };

    const handleManualClick = () => {
        setShowManual(true);
    };

    return (
        <div className="glass-panel p-8">
            <div className="text-center mb-6">
                <FileText className="mx-auto h-12 w-12 text-white/20 mb-3" />
                <h3 className="text-xl font-black text-white mb-2">
                    Add Portfolio Data
                </h3>
                <p className="text-white/50 max-w-md mx-auto">
                    Choose how you'd like to add transactions to your portfolio
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl mx-auto">
                {/* CSV Upload Option */}
                <button
                    onClick={handleImportClick}
                    className={cn(
                        "group relative overflow-hidden rounded-2xl p-6 text-left transition-all",
                        "glass-card hover:border-indigo-500/30 hover:-translate-y-1"
                    )}
                >
                    <div className="relative z-10">
                        <div className="h-12 w-12 rounded-xl bg-indigo-500/10 flex items-center justify-center mb-4 ring-1 ring-indigo-500/20 group-hover:ring-indigo-500/40 transition-all">
                            <Upload className="h-6 w-6 text-indigo-400" />
                        </div>
                        <h4 className="text-lg font-black text-white mb-2">
                            Upload CSV
                        </h4>
                        <p className="text-sm text-white/50 mb-4">
                            Import your complete transaction history from your brokerage statement
                        </p>
                        <div className="space-y-1">
                            <div className="flex items-center gap-2 text-xs text-white/40">
                                <div className="h-1 w-1 rounded-full bg-emerald-400" />
                                <span>Bulk import thousands of transactions</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-white/40">
                                <div className="h-1 w-1 rounded-full bg-emerald-400" />
                                <span>Supports Wealthsimple, IBKR, Questrade</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-white/40">
                                <div className="h-1 w-1 rounded-full bg-emerald-400" />
                                <span>Automatic duplicate detection</span>
                            </div>
                        </div>
                    </div>
                    <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>

                {/* Manual Entry Option */}
                <button
                    onClick={handleManualClick}
                    className={cn(
                        "group relative overflow-hidden rounded-2xl p-6 text-left transition-all",
                        "glass-card hover:border-violet-500/30 hover:-translate-y-1"
                    )}
                >
                    <div className="relative z-10">
                        <div className="h-12 w-12 rounded-xl bg-violet-500/10 flex items-center justify-center mb-4 ring-1 ring-violet-500/20 group-hover:ring-violet-500/40 transition-all">
                            <Plus className="h-6 w-6 text-violet-400" />
                        </div>
                        <h4 className="text-lg font-black text-white mb-2">
                            Manual Entry
                        </h4>
                        <p className="text-sm text-white/50 mb-4">
                            Add individual transactions one at a time with full control
                        </p>
                        <div className="space-y-1">
                            <div className="flex items-center gap-2 text-xs text-white/40">
                                <div className="h-1 w-1 rounded-full bg-violet-400" />
                                <span>Enter buys, sells, dividends, deposits</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-white/40">
                                <div className="h-1 w-1 rounded-full bg-violet-400" />
                                <span>Perfect for ad-hoc entries</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-white/40">
                                <div className="h-1 w-1 rounded-full bg-violet-400" />
                                <span>Add notes and custom details</span>
                            </div>
                        </div>
                    </div>
                    <div className="absolute inset-0 bg-gradient-to-br from-violet-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
            </div>

            <p className="text-xs text-white/30 text-center mt-6">
                You can use both methods together - import your history via CSV and add new trades manually
            </p>

            {/* Modals */}
            <ImportTransactionsModal
                open={showImport}
                onOpenChange={setShowImport}
            />
            <ManualTradeForm
                open={showManual}
                onOpenChange={setShowManual}
            />
        </div>
    );
}