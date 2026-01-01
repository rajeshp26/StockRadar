
'use client';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useEffect, useState } from 'react';

/**
 * Reusable dialog for adding or editing stock target prices.
 */
type StockTargetDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: { symbol: string; targetBuy: number | null; targetSell: number | null }) => void;
  mode?: 'add' | 'edit';
  initialData?: {
    symbol: string;
    targetBuy: number | null;
    targetSell: number | null;
  };
};

export function StockTargetDialog({ 
  open, 
  onOpenChange, 
  onSave, 
  mode = 'add',
  initialData 
}: StockTargetDialogProps) {
  const [symbol, setSymbol] = useState(initialData?.symbol || '');
  const [targetBuy, setTargetBuy] = useState(initialData?.targetBuy?.toString() || '');
  const [targetSell, setTargetSell] = useState(initialData?.targetSell?.toString() || '');

  // Reset or populate fields when initialData changes
  useEffect(() => {
    if (open) {
      setSymbol(initialData?.symbol || '');
      setTargetBuy(initialData?.targetBuy?.toString() || '');
      setTargetSell(initialData?.targetSell?.toString() || '');
    }
  }, [open, initialData]);

  const handleSave = () => {
    onSave({
      symbol: symbol.toUpperCase(),
      targetBuy: targetBuy ? parseFloat(targetBuy) : null,
      targetSell: targetSell ? parseFloat(targetSell) : null,
    });
    // Don't reset in edit mode if you want to keep the UI stable, 
    // but the parent usually handles the 'open' state.
    if (mode === 'add') {
      setSymbol('');
      setTargetBuy('');
      setTargetSell('');
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{mode === 'add' ? 'Add Stock' : `Edit ${symbol}`}</DialogTitle>
          <DialogDescription>
            {mode === 'add' 
              ? 'Enter the stock symbol and your target prices.' 
              : 'Update your target prices for this stock.'}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="symbol" className="text-right">
              Symbol
            </Label>
            <Input
              id="symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="col-span-3"
              disabled={mode === 'edit'} // Symbol cannot be changed in edit mode
              placeholder="e.g., AAPL"
            />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="target-buy" className="text-right">
              Target Buy
            </Label>
            <Input
              id="target-buy"
              type="number"
              step="0.01"
              value={targetBuy}
              onChange={(e) => setTargetBuy(e.target.value)}
              className="col-span-3"
              placeholder="Optional"
            />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="target-sell" className="text-right">
              Target Sell
            </Label>
            <Input
              id="target-sell"
              type="number"
              step="0.01"
              value={targetSell}
              onChange={(e) => setTargetSell(e.target.value)}
              className="col-span-3"
              placeholder="Optional"
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleSave}>
            {mode === 'add' ? 'Add to Watchlist' : 'Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
