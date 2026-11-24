// web/src/features/portfolio/components/ImportTransactionsModal.tsx
// Async CSV import with background job polling

'use client';

import { useState, useEffect, useCallback } from 'react';
import { Upload, AlertCircle, CheckCircle2, Loader2, AlertTriangle } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useServices } from '@/shared/contexts/ServiceContext';
import { useImportTransactions, useBrokerages, useImportStatus } from '../hooks/usePortfolio';
import { useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/hooks/use-toast';
import { QK } from '@/lib/query-keys';
import { ACCOUNT_TYPE_LABELS, type ImportSummary } from '../types/portfolio.types';
import { cn } from '@/lib/utils';

interface ImportTransactionsModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

const STEP_MESSAGES: Record<string, string> = {
    pending: 'Queued for processing...',
    processing: 'Processing transactions...',
    completed: 'Import complete!',
    failed: 'Import failed',
};

const countLabel = (n: number, singular: string, pluralForm?: string) =>
    `${n.toLocaleString()} ${n === 1 ? singular : (pluralForm ?? `${singular}s`)}`;

function describeImportError(raw?: string | null): string {
    const message = raw?.trim();
    if (!message) return 'An error occurred during import.';
    if (/missing required columns/i.test(message)) {
        return `${message.replace(/\.$/, '')}. Expected columns include effective_date (or transaction_date), account_id, activity_type, symbol and net_cash_amount.`;
    }
    if (/unsupported brokerage/i.test(message)) {
        return `${message.replace(/\.$/, '')}. Select a supported brokerage and try again.`;
    }
    return message;
}

export function ImportTransactionsModal({ open, onOpenChange }: ImportTransactionsModalProps) {
    const { portfolioService } = useServices();
    const queryClient = useQueryClient();
    const { toast } = useToast();
    const { data: brokerages, isLoading: brokLoading } = useBrokerages();
    const importMutation = useImportTransactions();

    const [selectedBrokerage, setSelectedBrokerage] = useState<string>('');
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [accountFilter, setAccountFilter] = useState<Set<string>>(new Set());
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [importBatchId, setImportBatchId] = useState<string | null>(null);

    const { data: importStatus } = useImportStatus(importBatchId);

    // The status endpoint returns a per-category breakdown. Derive it from the
    // row pipeline for jobs created before that breakdown existed, so an old
    // job still explains an exact repeat upload correctly.
    const summary: ImportSummary = importStatus?.result ?? {
        new_entries: importStatus?.rows_inserted ?? 0,
        already_imported: Math.max(0, (importStatus?.rows_parsed ?? 0) - (importStatus?.rows_inserted ?? 0)),
        skipped_rows: Math.max(0, (importStatus?.total_rows ?? 0) - (importStatus?.rows_parsed ?? 0)),
        accounts_created: 0,
        accounts_updated: 0,
        symbols_created: 0,
    };
    const isComplete = importStatus?.status === 'completed';
    // An exact re-upload is a success, but "0 transactions imported" reads as
    // a failure. Treat it as its own state with an unambiguous message.
    const isNoOpReupload = isComplete && summary.new_entries === 0 && summary.already_imported > 0;

    const availableAccountTypes =
        selectedBrokerage === 'wealthsimple'
            ? ['TFSA', 'RRSP', 'Non-registered', 'FHSA']
            : selectedBrokerage === 'ibkr'
                ? ['401k', 'IRA', 'Roth IRA', 'Non-registered']
                : [];

    // Handle completion/failure from polling
    useEffect(() => {
        if (!importStatus) return;

        if (importStatus.status === 'completed') {
            queryClient.invalidateQueries({ queryKey: QK.portfolioOverview() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioAccounts() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioHoldings() });

            if (summary.new_entries === 0 && summary.already_imported > 0) {
                toast({
                    title: 'Already Up to Date',
                    description: `All ${countLabel(summary.already_imported, 'row')} were already imported — no new transactions were added.`,
                });
            } else {
                const breakdown = [
                    summary.new_entries > 0
                        ? `${countLabel(summary.new_entries, 'new transaction')} added`
                        : null,
                    summary.already_imported > 0
                        ? `${countLabel(summary.already_imported, 'row')} already imported`
                        : null,
                    summary.skipped_rows > 0
                        ? `${countLabel(summary.skipped_rows, 'row')} skipped`
                        : null,
                ].filter(Boolean);
                toast({
                    title: 'Import Successful',
                    description: breakdown.join(' · ') || 'Import complete.',
                });
            }
        } else if (importStatus.status === 'failed') {
            toast({
                title: 'Import Failed',
                description: describeImportError(importStatus.error),
                variant: 'destructive',
            });
        }
        // Depend on the primitive counts, not the recreated `summary` object.
    }, [importStatus, queryClient, toast, summary.new_entries, summary.already_imported, summary.skipped_rows]);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file && file.type === 'text/csv') {
            setSelectedFile(file);
        } else {
            setSelectedFile(null);
            alert('Please select a CSV file');
        }
    };

    const toggleAccountType = (accountType: string) => {
        const newFilter = new Set(accountFilter);
        if (newFilter.has(accountType)) {
            newFilter.delete(accountType);
        } else {
            newFilter.add(accountType);
        }
        setAccountFilter(newFilter);
    };

    const handleImport = async () => {
        if (!selectedBrokerage || !selectedFile) return;

        try {
            const base64Content = await portfolioService.fileToBase64(selectedFile);
            const request = {
                brokerage_code: selectedBrokerage,
                csv_content: base64Content,
                account_filter: accountFilter.size > 0 ? Array.from(accountFilter) : undefined,
            };

            const result = await importMutation.mutateAsync(request);

            if (result.import_batch_id) {
                setImportBatchId(result.import_batch_id);
            }
        } catch (error) {
            console.error('Import error:', error);
        }
    };

    const handleClose = useCallback(() => {
        // Refresh portfolio data if import completed successfully
        if (importStatus?.status === 'completed') {
            queryClient.invalidateQueries({ queryKey: QK.portfolioOverview() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioAccounts() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioHoldings() });
        }
        setSelectedBrokerage('');
        setSelectedFile(null);
        setAccountFilter(new Set());
        setShowAdvanced(false);
        setImportBatchId(null);
        importMutation.reset();
        onOpenChange(false);
    }, [importMutation, onOpenChange, importStatus, queryClient]);

    const isDuplicateImport = importMutation.data?.duplicate_import;

    // Determine display state
    const isQueued = importMutation.isSuccess && importMutation.data?.success && !importBatchId;
    const isPolling = !!importBatchId && (!importStatus || (importStatus.status !== 'completed' && importStatus.status !== 'failed'));
    const isFailed = (importStatus?.status === 'failed')
        || (importMutation.isError && !importBatchId)
        || (importMutation.data?.success === false && !importBatchId && !isDuplicateImport);
    const isProcessing = isQueued || isPolling;
    // A duplicate CSV is no longer a hard stop: imports resume by row identity,
    // so re-uploading is how a user picks up transactions added to a later export.
    const canImport = selectedBrokerage && selectedFile && !isProcessing && !importMutation.isPending;

    const progressPct = importStatus && importStatus.total_rows > 0
        ? Math.round((Math.max(importStatus.rows_parsed, importStatus.rows_inserted) / importStatus.total_rows) * 100)
        : 0;

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="glass-panel sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="text-xl font-black text-white">
                        Import Transactions
                    </DialogTitle>
                    <DialogDescription className="text-white/50">
                        Upload your brokerage CSV export to import transactions into your portfolio
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-6 py-4">
                    {/* Brokerage Selection */}
                    <div className="space-y-2">
                        <Label htmlFor="brokerage" className="text-white/70">
                            Brokerage
                        </Label>
                        <Select value={selectedBrokerage} onValueChange={setSelectedBrokerage}>
                            <SelectTrigger
                                id="brokerage"
                                className="glass-input"
                                disabled={brokLoading || isProcessing}
                            >
                                <SelectValue placeholder="Select your brokerage" />
                            </SelectTrigger>
                            <SelectContent className="glass-panel border-white/10">
                                {brokerages?.map((brokerage) => (
                                    <SelectItem
                                        key={brokerage.brokerage_id}
                                        value={brokerage.brokerage_code}
                                        className="focus:bg-white/5"
                                    >
                                        {brokerage.brokerage_name} ({brokerage.country_code})
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* File Upload */}
                    <div className="space-y-2">
                        <Label htmlFor="csv-file" className="text-white/70">
                            CSV File
                        </Label>
                        <div className="flex items-center gap-3">
                            <Button
                                type="button"
                                variant="outline"
                                className="glass-button-secondary"
                                disabled={isProcessing}
                                onClick={() => document.getElementById('csv-file')?.click()}
                            >
                                <Upload className="mr-2 h-4 w-4" />
                                Choose File
                            </Button>
                            <span className="text-sm text-white/40 truncate flex-1">
                                {selectedFile ? selectedFile.name : 'No file selected'}
                            </span>
                        </div>
                        <input
                            id="csv-file"
                            type="file"
                            accept=".csv"
                            className="hidden"
                            disabled={isProcessing}
                            onChange={handleFileChange}
                        />
                    </div>

                    {/* Advanced Options */}
                    {selectedBrokerage && !isProcessing && (
                        <div className="space-y-3">
                            <button
                                type="button"
                                className="text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
                                onClick={() => setShowAdvanced(!showAdvanced)}
                            >
                                {showAdvanced ? '− Hide' : '+ Show'} Advanced Options
                            </button>

                            {showAdvanced && (
                                <div className="glass-card p-4 space-y-3">
                                    <Label className="text-white/70 text-sm">
                                        Filter by Account Type (optional)
                                    </Label>
                                    <p className="text-xs text-white/40">
                                        Select specific account types to import. Leave all unchecked to import all accounts.
                                    </p>
                                    <div className="space-y-2">
                                        {availableAccountTypes.map((accountType) => (
                                            <div key={accountType} className="flex items-center gap-2">
                                                <Checkbox
                                                    id={`account-${accountType}`}
                                                    checked={accountFilter.has(accountType)}
                                                    onCheckedChange={() => toggleAccountType(accountType)}
                                                    className="border-white/20 data-[state=checked]:bg-indigo-500"
                                                />
                                                <Label
                                                    htmlFor={`account-${accountType}`}
                                                    className="text-sm text-white/60 cursor-pointer"
                                                >
                                                    {ACCOUNT_TYPE_LABELS[accountType] || accountType}
                                                </Label>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* DUPLICATE WARNING */}
                    {isDuplicateImport && (
                        <Alert className="glass-card border-amber-500/20">
                            <AlertTriangle className="h-5 w-5 text-amber-400" />
                            <AlertTitle className="text-white font-bold">Duplicate Import Detected</AlertTitle>
                            <AlertDescription className="text-white/60">
                                <p className="mb-2">{importMutation.data?.warning}</p>
                                <p className="text-xs text-white/40">
                                    This exact CSV file was previously imported on{' '}
                                    {importMutation.data?.previous_import_date
                                        ? new Date(importMutation.data.previous_import_date).toLocaleDateString()
                                        : 'a previous date'}.
                                    Importing again will skip duplicate transactions automatically.
                                </p>
                            </AlertDescription>
                        </Alert>
                    )}

                    {/* PROGRESS: Queued / Processing */}
                    {isProcessing && (
                        <div className="glass-card p-4 space-y-3">
                            <div className="flex items-center gap-3">
                                <Loader2 className="h-5 w-5 text-indigo-400 animate-spin flex-shrink-0" />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-white truncate">
                                        {importStatus
                                            ? STEP_MESSAGES[importStatus.status] || 'Processing...'
                                            : 'Queued for processing...'}
                                    </p>
                                    {importStatus && importStatus.total_rows > 0 && (
                                        <p className="text-xs text-white/40">
                                            {importStatus.rows_parsed > 0
                                                ? `${importStatus.rows_parsed} / ${importStatus.total_rows} rows`
                                                : `${importStatus.total_rows} rows to process`}
                                        </p>
                                    )}
                                </div>
                            </div>
                            {/* Progress bar */}
                            {importStatus && importStatus.total_rows > 0 && (
                                <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-indigo-500 rounded-full transition-all duration-500 ease-out"
                                        style={{ width: `${Math.min(progressPct, 99)}%` /* stack-allow: inline-style */ }}
                                    />
                                </div>
                            )}
                        </div>
                    )}

                    {/* SUCCESS / NO-OP RE-UPLOAD */}
                    {isComplete && (
                        <div className={cn(
                            'glass-card p-4 border',
                            isNoOpReupload ? 'border-indigo-400/20' : 'border-emerald-500/20',
                        )}>
                            <div className="flex items-start gap-3">
                                <CheckCircle2 className={cn(
                                    'h-5 w-5 flex-shrink-0 mt-0.5',
                                    isNoOpReupload ? 'text-indigo-400' : 'text-emerald-400',
                                )} />
                                <div className="flex-1 space-y-2">
                                    <p className="text-sm font-medium text-white">
                                        {isNoOpReupload ? 'Nothing New to Import' : 'Import Successful'}
                                    </p>
                                    <div className="space-y-1">
                                        {summary.new_entries > 0 && (
                                            <p className="text-xs text-emerald-400">
                                                {countLabel(summary.new_entries, 'new transaction')} added
                                            </p>
                                        )}
                                        {summary.already_imported > 0 && (
                                            <p className="text-xs text-white/60">
                                                {countLabel(summary.already_imported, 'row')} already imported — skipped
                                            </p>
                                        )}
                                        {summary.skipped_rows > 0 && (
                                            <p className="text-xs text-amber-400">
                                                {countLabel(summary.skipped_rows, 'row')} skipped (blank amounts or unsupported activity)
                                            </p>
                                        )}
                                        {isNoOpReupload && (
                                            <p className="text-xs text-white/40">
                                                Your portfolio is already up to date. No changes were made.
                                            </p>
                                        )}
                                        {(summary.accounts_created > 0 || summary.symbols_created > 0) && (
                                            <p className="text-xs text-white/40">
                                                {[
                                                    summary.accounts_created > 0
                                                        ? `${countLabel(summary.accounts_created, 'new account')} created`
                                                        : null,
                                                    summary.symbols_created > 0
                                                        ? `${countLabel(summary.symbols_created, 'new company', 'new companies')} created`
                                                        : null,
                                                ].filter(Boolean).join(' · ')}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* FAILURE */}
                    {isFailed && (
                        <div className="glass-card p-4 border border-rose-500/20">
                            <div className="flex items-start gap-3">
                                <AlertCircle className="h-5 w-5 text-rose-400 flex-shrink-0 mt-0.5" />
                                <div className="flex-1">
                                    <p className="text-sm font-medium text-white">Import Failed</p>
                                    <p className="text-xs text-white/60">
                                        Reason: {describeImportError(
                                            importStatus?.error
                                            || importMutation.data?.error
                                            || importMutation.error?.message
                                        )}
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Actions */}
                <div className="flex justify-end gap-3 pt-4 border-t border-white/5">
                    <Button
                        type="button"
                        variant="outline"
                        className="glass-button-secondary"
                        onClick={handleClose}
                        disabled={isProcessing}
                    >
                        {isComplete ? 'Close' : 'Cancel'}
                    </Button>
                    <Button
                        type="button"
                        className="glass-button"
                        onClick={handleImport}
                        disabled={!canImport}
                    >
                        {isProcessing ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Processing...
                            </>
                        ) : (
                            <>
                                <Upload className="mr-2 h-4 w-4" />
                                Import
                            </>
                        )}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}