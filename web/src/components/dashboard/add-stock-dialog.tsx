'use client';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useEffect, useState } from 'react';
import { PlusCircle, Save, DollarSign } from 'lucide-react';

type StockTargetDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: {
    symbol:     string;
    targetBuy:  number | null;
    targetSell: number | null;
  }) => void;
  mode?: 'add' | 'edit';
  initialData?: {
    symbol:     string;
    targetBuy:  number | null;
    targetSell: number | null;
  };
};

export function StockTargetDialog({
  open,
  onOpenChange,
  onSave,
  mode = 'add',
  initialData,
}: StockTargetDialogProps) {
  /* ── State (logic unchanged) ──────────────────────────── */
  const [symbol,     setSymbol]     = useState(initialData?.symbol           || '');
  const [targetBuy,  setTargetBuy]  = useState(initialData?.targetBuy?.toString()  || '');
  const [targetSell, setTargetSell] = useState(initialData?.targetSell?.toString() || '');

  useEffect(() => {
    if (open) {
      setSymbol(    initialData?.symbol              || '');
      setTargetBuy( initialData?.targetBuy?.toString()  || '');
      setTargetSell(initialData?.targetSell?.toString() || '');
    }
  }, [open, initialData]);

  const handleSave = () => {
    onSave({
      symbol:     symbol.toUpperCase(),
      targetBuy:  targetBuy  ? parseFloat(targetBuy)  : null,
      targetSell: targetSell ? parseFloat(targetSell) : null,
    });
    if (mode === 'add') {
      setSymbol('');
      setTargetBuy('');
      setTargetSell('');
    }
    onOpenChange(false);
  };

  const isValid = symbol.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={[
          // Glass dialog surface — override shadcn defaults
          '!bg-[rgba(10,13,26,0.92)]',
          'border border-white/10',
          'shadow-[0_32px_80px_rgba(0,0,0,0.7)]',
          'backdrop-blur-[30px]',
          'rounded-3xl',
          'p-0 gap-0',
          'sm:max-w-md',
          'overflow-hidden',
        ].join(' ')}
      >
        {/* ── Top gradient stripe ──────────────────────── */}
        <div
          className="h-px w-full"
          style={{
            background:
              'linear-gradient(90deg, transparent, rgba(99,102,241,0.6) 40%, rgba(139,92,246,0.4) 70%, transparent)',
          }}
          aria-hidden="true"
        />

        {/* ── Header ───────────────────────────────────── */}
        <div className="px-8 pt-8 pb-6">
          <div className="flex items-center gap-3 mb-1">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
              {mode === 'add'
                ? <PlusCircle className="h-4 w-4 text-indigo-400" />
                : <Save className="h-4 w-4 text-indigo-400" />
              }
            </div>
            <DialogTitle className="text-base font-black text-white tracking-tight">
              {mode === 'add' ? 'Add Stock' : `Edit ${symbol}`}
            </DialogTitle>
          </div>
          <DialogDescription className="text-xs text-white/35 ml-11">
            {mode === 'add'
              ? 'Enter a ticker symbol and optional target prices.'
              : 'Update your target prices for this position.'}
          </DialogDescription>
        </div>

        {/* ── Form body ────────────────────────────────── */}
        <div className="px-8 pb-8 space-y-4">

          {/* Symbol */}
          <div className="space-y-2">
            <label
              htmlFor="dialog-symbol"
              className="block text-[10px] font-black uppercase tracking-[0.18em] text-white/30"
            >
              Ticker Symbol
            </label>
            <input
              id="dialog-symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              disabled={mode === 'edit'}
              placeholder="e.g. AAPL"
              autoComplete="off"
              autoCapitalize="characters"
              className={[
                'w-full px-4 py-3 rounded-xl text-sm font-bold',
                'bg-white/5 border border-white/8 text-white',
                'placeholder:text-white/20',
                'focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15',
                'transition-all duration-150',
                mode === 'edit' && 'opacity-50 cursor-not-allowed',
              ].join(' ')}
            />
          </div>

          {/* Target prices row */}
          <div className="grid grid-cols-2 gap-3">
            {/* Buy target */}
            <div className="space-y-2">
              <label
                htmlFor="dialog-target-buy"
                className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-400/60"
              >
                <DollarSign className="h-2.5 w-2.5" />
                Buy Target
              </label>
              <input
                id="dialog-target-buy"
                type="number"
                step="0.01"
                min="0"
                value={targetBuy}
                onChange={(e) => setTargetBuy(e.target.value)}
                placeholder="Optional"
                className={[
                  'w-full px-4 py-3 rounded-xl text-sm font-bold',
                  'bg-white/5 border border-white/8 text-white',
                  'placeholder:text-white/20',
                  'focus:outline-none focus:border-emerald-500/60 focus:ring-2 focus:ring-emerald-500/15',
                  'transition-all duration-150',
                  // Hide number input spinners
                  '[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none',
                ].join(' ')}
              />
            </div>

            {/* Sell target */}
            <div className="space-y-2">
              <label
                htmlFor="dialog-target-sell"
                className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-rose-400/60"
              >
                <DollarSign className="h-2.5 w-2.5" />
                Sell Target
              </label>
              <input
                id="dialog-target-sell"
                type="number"
                step="0.01"
                min="0"
                value={targetSell}
                onChange={(e) => setTargetSell(e.target.value)}
                placeholder="Optional"
                className={[
                  'w-full px-4 py-3 rounded-xl text-sm font-bold',
                  'bg-white/5 border border-white/8 text-white',
                  'placeholder:text-white/20',
                  'focus:outline-none focus:border-rose-500/60 focus:ring-2 focus:ring-rose-500/15',
                  'transition-all duration-150',
                  '[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none',
                ].join(' ')}
              />
            </div>
          </div>

          {/* Hint */}
          <p className="text-[9px] text-white/20 leading-relaxed">
            Target prices are optional. You'll see alerts when the stock price crosses your targets.
          </p>

          {/* ── Actions ─────────────────────────────────── */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={() => onOpenChange(false)}
              className={[
                'flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest',
                'bg-white/5 border border-white/8 text-white/40',
                'hover:bg-white/10 hover:text-white/70',
                'transition-all duration-150',
              ].join(' ')}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!isValid}
              className={[
                'flex-[2] py-3 rounded-xl text-[10px] font-black uppercase tracking-widest',
                'inline-flex items-center justify-center gap-2',
                'transition-all duration-150',
                isValid
                  ? 'bg-indigo-600 border border-indigo-500/50 text-white shadow-[0_4px_16px_rgba(99,102,241,0.3)] hover:bg-indigo-500 hover:shadow-[0_6px_24px_rgba(99,102,241,0.45)] active:scale-[0.98]'
                  : 'bg-white/5 border border-white/8 text-white/20 cursor-not-allowed',
              ].join(' ')}
            >
              {mode === 'add'
                ? <><PlusCircle className="h-3.5 w-3.5" /> Add to Watchlist</>
                : <><Save className="h-3.5 w-3.5" /> Save Changes</>
              }
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}