// web/src/features/portfolio/components/ManualTradeForm.tsx
// ENHANCEMENT: Show real-time feedback when creating new companies

'use client';

import { useState, useEffect } from 'react';
import { Plus, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { useServices } from '@/shared/contexts/ServiceContext';
import { usePortfolioAccounts } from '../hooks/usePortfolio';
import { QK } from '@/lib/query-keys';
import { cn } from '@/lib/utils';

interface ManualTradeFormProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

const ACTIVITY_TYPES = [
    { value: 'BUY', label: 'Buy' },
    { value: 'SELL', label: 'Sell' },
    { value: 'DIVIDEND', label: 'Dividend' },
    { value: 'DEPOSIT', label: 'Deposit' },
    { value: 'WITHDRAWAL', label: 'Withdrawal' },
];

export function ManualTradeForm({ open, onOpenChange }: ManualTradeFormProps) {
    const { portfolioService } = useServices();
    const { data: accounts, isLoading: accountsLoading } = usePortfolioAccounts();
    const { toast } = useToast();
    const queryClient = useQueryClient();

    const [accountId, setAccountId] = useState<string>('');
    const [activityType, setActivityType] = useState<string>('BUY');
    const [symbol, setSymbol] = useState('');
    const [quantity, setQuantity] = useState('');
    const [unitPrice, setUnitPrice] = useState('');
    const [commission, setCommission] = useState('0');
    const [transactionDate, setTransactionDate] = useState(
        new Date().toISOString().split('T')[0]
    );
    const [notes, setNotes] = useState('');

    // NEW: Symbol validation state
    const [isCheckingSymbol, setIsCheckingSymbol] = useState(false);
    const [symbolStatus, setSymbolStatus] = useState<{
        exists: boolean;
        companyName?: string;
        willCreate?: boolean;
    } | null>(null);

    // NEW: Check if company exists when symbol changes
    useEffect(() => {
        const checkSymbol = async () => {
            if (!symbol || symbol.length < 1) {
                setSymbolStatus(null);
                return;
            }

            const upperSymbol = symbol.toUpperCase();
            setIsCheckingSymbol(true);

            try {
                // Check if company exists in database
                const res = await portfolioService.api.get(`/companies/search?symbol=${upperSymbol}`);

                if (res.data.exists) {
                    setSymbolStatus({
                        exists: true,
                        companyName: res.data.company_name,
                        willCreate: false,
                    });
                } else {
                    setSymbolStatus({
                        exists: false,
                        willCreate: true,
                    });
                }
            } catch (error) {
                setSymbolStatus(null);
            } finally {
                setIsCheckingSymbol(false);
            }
        };

        const debounceTimer = setTimeout(checkSymbol, 500);
        return () => clearTimeout(debounceTimer);
    }, [symbol, portfolioService]);

    const addTransactionMutation = useMutation({
        mutationFn: async (data: any) => {
            const res = await portfolioService.api.post('/portfolio/transactions/manual', data);
            return res.data;
        },
        onSuccess: (result) => {
            // Invalidate all portfolio queries
            queryClient.invalidateQueries({ queryKey: QK.portfolioOverview() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioAccounts() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioHoldings() });
            if (accountId) {
                queryClient.invalidateQueries({
                    queryKey: QK.portfolioAccountHoldings(parseInt(accountId))
                });
            }

            // NEW: Show creation message if company was created
            if (result.company_created) {
                toast({
                    title: 'Transaction Added',
                    description: (
                        <div className="space-y-1">
                            <p>Your transaction has been recorded successfully.</p>
                            <p className="text-xs text-emerald-400">
                                ✓ New company created: {result.company_name}
                            </p>
                        </div>
                    ),
                });
            } else {
                toast({
                    title: 'Transaction Added',
                    description: 'Your transaction has been recorded successfully.',
                });
            }

            handleClose();
        },
        onError: (error: any) => {
            toast({
                title: 'Error',
                description: error.message || 'Failed to add transaction',
                variant: 'destructive',
            });
        },
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();

        // Validation
        if (!accountId) {
            toast({
                title: 'Validation Error',
                description: 'Please select an account',
                variant: 'destructive',
            });
            return;
        }

        if (['BUY', 'SELL'].includes(activityType)) {
            if (!symbol || !quantity || !unitPrice) {
                toast({
                    title: 'Validation Error',
                    description: 'Symbol, quantity, and price are required for buy/sell transactions',
                    variant: 'destructive',
                });
                return;
            }
        }

        if (['DIVIDEND', 'DEPOSIT', 'WITHDRAWAL'].includes(activityType) && !quantity) {
            toast({
                title: 'Validation Error',
                description: 'Amount is required',
                variant: 'destructive',
            });
            return;
        }

        // Prepare data
        const data = {
            account_id: parseInt(accountId),
            transaction_date: transactionDate,
            activity_type: activityType,
            symbol: symbol.toUpperCase() || null,
            quantity: quantity ? parseFloat(quantity) : null,
            unit_price: unitPrice ? parseFloat(unitPrice) : null,
            commission: parseFloat(commission),
            notes: notes || null,
        };

        addTransactionMutation.mutate(data);
    };

    const handleClose = () => {
        setAccountId('');
        setActivityType('BUY');
        setSymbol('');
        setQuantity('');
        setUnitPrice('');
        setCommission('0');
        setTransactionDate(new Date().toISOString().split('T')[0]);
        setNotes('');
        setSymbolStatus(null);
        onOpenChange(false);
    };

    const requiresSymbol = ['BUY', 'SELL'].includes(activityType);
    const requiresPrice = ['BUY', 'SELL'].includes(activityType);
    const isMoneyMovement = ['DIVIDEND', 'DEPOSIT', 'WITHDRAWAL'].includes(activityType);

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="glass-panel sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="text-xl font-black text-white">
                        Add Transaction
                    </DialogTitle>
                    <DialogDescription className="text-white/50">
                        Manually enter a single transaction
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-4 py-4">
                    {/* Account Selection */}
                    <div className="space-y-2">
                        <Label htmlFor="account" className="text-white/70">
                            Account *
                        </Label>
                        <Select value={accountId} onValueChange={setAccountId} disabled={accountsLoading}>
                            <SelectTrigger id="account" className="glass-input">
                                <SelectValue placeholder="Select account" />
                            </SelectTrigger>
                            <SelectContent className="glass-panel border-white/10">
                                {accounts?.map((account) => (
                                    <SelectItem
                                        key={account.account_id}
                                        value={account.account_id.toString()}
                                        className="focus:bg-white/5"
                                    >
                                        {account.account_name} ({account.account_type})
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Activity Type */}
                    <div className="space-y-2">
                        <Label htmlFor="activity-type" className="text-white/70">
                            Transaction Type *
                        </Label>
                        <Select value={activityType} onValueChange={setActivityType}>
                            <SelectTrigger id="activity-type" className="glass-input">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="glass-panel border-white/10">
                                {ACTIVITY_TYPES.map((type) => (
                                    <SelectItem
                                        key={type.value}
                                        value={type.value}
                                        className="focus:bg-white/5"
                                    >
                                        {type.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Date */}
                    <div className="space-y-2">
                        <Label htmlFor="date" className="text-white/70">
                            Transaction Date *
                        </Label>
                        <Input
                            id="date"
                            type="date"
                            value={transactionDate}
                            onChange={(e) => setTransactionDate(e.target.value)}
                            className="glass-input"
                            max={new Date().toISOString().split('T')[0]}
                        />
                    </div>

                    {/* Symbol (for BUY/SELL) with NEW status indicator */}
                    {requiresSymbol && (
                        <div className="space-y-2">
                            <Label htmlFor="symbol" className="text-white/70">
                                Ticker Symbol *
                            </Label>
                            <div className="relative">
                                <Input
                                    id="symbol"
                                    type="text"
                                    value={symbol}
                                    onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                                    className="glass-input pr-10"
                                    placeholder="e.g., AAPL"
                                    maxLength={10}
                                />
                                {isCheckingSymbol && (
                                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                                        <Loader2 className="h-4 w-4 animate-spin text-white/40" />
                                    </div>
                                )}
                            </div>

                            {/* NEW: Symbol status feedback */}
                            {symbolStatus && !isCheckingSymbol && (
                                <div className={cn(
                                    "flex items-start gap-2 p-3 rounded-lg text-xs",
                                    symbolStatus.exists
                                        ? "bg-emerald-500/10 border border-emerald-500/20"
                                        : "bg-amber-500/10 border border-amber-500/20"
                                )}>
                                    {symbolStatus.exists ? (
                                        <>
                                            <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                                            <div>
                                                <p className="font-medium text-emerald-400">
                                                    Company exists: {symbolStatus.companyName}
                                                </p>
                                                <p className="text-white/50 mt-0.5">
                                                    Transaction will be linked to existing company
                                                </p>
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            <AlertCircle className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
                                            <div>
                                                <p className="font-medium text-amber-400">
                                                    New company will be created
                                                </p>
                                                <p className="text-white/50 mt-0.5">
                                                    Company details will be fetched from market data automatically
                                                </p>
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Quantity / Amount */}
                    <div className="space-y-2">
                        <Label htmlFor="quantity" className="text-white/70">
                            {isMoneyMovement ? 'Amount *' : 'Quantity (Shares) *'}
                        </Label>
                        <Input
                            id="quantity"
                            type="number"
                            step="any"
                            value={quantity}
                            onChange={(e) => setQuantity(e.target.value)}
                            className="glass-input"
                            placeholder={isMoneyMovement ? '0.00' : '0'}
                        />
                    </div>

                    {/* Unit Price (for BUY/SELL) */}
                    {requiresPrice && (
                        <div className="space-y-2">
                            <Label htmlFor="price" className="text-white/70">
                                Price per Share *
                            </Label>
                            <Input
                                id="price"
                                type="number"
                                step="0.01"
                                value={unitPrice}
                                onChange={(e) => setUnitPrice(e.target.value)}
                                className="glass-input"
                                placeholder="0.00"
                            />
                        </div>
                    )}

                    {/* Commission (for BUY/SELL) */}
                    {requiresPrice && (
                        <div className="space-y-2">
                            <Label htmlFor="commission" className="text-white/70">
                                Commission
                            </Label>
                            <Input
                                id="commission"
                                type="number"
                                step="0.01"
                                value={commission}
                                onChange={(e) => setCommission(e.target.value)}
                                className="glass-input"
                                placeholder="0.00"
                            />
                        </div>
                    )}

                    {/* Notes */}
                    <div className="space-y-2">
                        <Label htmlFor="notes" className="text-white/70">
                            Notes (Optional)
                        </Label>
                        <Textarea
                            id="notes"
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            className="glass-input min-h-[80px]"
                            placeholder="Add any additional notes..."
                            maxLength={500}
                        />
                    </div>

                    {/* Summary */}
                    {requiresPrice && quantity && unitPrice && (
                        <div className="glass-card p-4 border-white/10">
                            <p className="text-xs text-white/40 mb-1">Total Value</p>
                            <p className="text-lg font-bold text-white">
                                ${(parseFloat(quantity) * parseFloat(unitPrice) + parseFloat(commission || '0')).toFixed(2)}
                            </p>
                        </div>
                    )}

                    {/* Actions */}
                    <div className="flex justify-end gap-3 pt-4 border-t border-white/5">
                        <Button
                            type="button"
                            variant="outline"
                            className="glass-button-secondary"
                            onClick={handleClose}
                            disabled={addTransactionMutation.isPending}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            className="glass-button"
                            disabled={addTransactionMutation.isPending}
                        >
                            {addTransactionMutation.isPending ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Adding...
                                </>
                            ) : (
                                <>
                                    <Plus className="mr-2 h-4 w-4" />
                                    Add Transaction
                                </>
                            )}
                        </Button>
                    </div>
                </form>
            </DialogContent>
        </Dialog>
    );
}