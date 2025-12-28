
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
import type { WatchlistItem } from '@/lib/types';
import { useState } from 'react';

/**
 * Props for the AddStockDialog component.
 */
type AddStockDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAddStock: (stock: Omit<WatchlistItem, 'id' | 'userId'>) => void;
};

/**
 * A dialog component for adding a new stock to the user's watchlist.
 * It captures the stock symbol and optional buy/sell targets.
 * @param {AddStockDialogProps} props - The component props.
 * @returns {JSX.Element} The rendered dialog component.
 */
export function AddStockDialog({ open, onOpenChange, onAddStock }: AddStockDialogProps) {
  const [symbol, setSymbol] = useState('');
  const [targetBuy, setTargetBuy] = useState('');
  const [targetSell, setTargetSell] = useState('');

  /**
   * Handles the 'Add' button click. It calls the onAddStock callback with the new
   * stock information and then resets the form fields and closes the dialog.
   */
  const handleAdd = () => {
    onAddStock({
      symbol: symbol.toUpperCase(),
      targetBuy: targetBuy ? parseFloat(targetBuy) : null,
      targetSell: targetSell ? parseFloat(targetSell) : null,
    });
    setSymbol('');
    setTargetBuy('');
    setTargetSell('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Add Stock to Watchlist</DialogTitle>
          <DialogDescription>
            Enter the stock symbol and your target prices.
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
              value={targetSell}
              onChange={(e) => setTargetSell(e.target.value)}
              className="col-span-3"
              placeholder="Optional"
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleAdd}>Add Stock</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
