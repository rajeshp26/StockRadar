'use client';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useEffect, useRef, useState, useCallback } from 'react';
import { PlusCircle, Save, DollarSign, Search, X } from 'lucide-react';
import { watchlistService, type StockSearchResult, type ListingIdentity } from '@/features/watchlists/services/watchlist.service';

export type AddStockSelection = {
  symbol:     string;
  targetBuy:  number | null;
  targetSell: number | null;
  listing?:   ListingIdentity;
};

type StockTargetDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: AddStockSelection) => void;
  mode?: 'add' | 'edit';
  initialData?: {
    symbol:     string;
    targetBuy:  number | null;
    targetSell: number | null;
  };
};

// Badge colour per instrument type
const TYPE_STYLES: Record<string, string> = {
  equity:      'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
  etf:         'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  future:      'bg-amber-500/20  text-amber-300  border-amber-500/30',
  mutualfund:  'bg-violet-500/20 text-violet-300 border-violet-500/30',
  index:       'bg-sky-500/20    text-sky-300    border-sky-500/30',
};

export function StockTargetDialog({
  open,
  onOpenChange,
  onSave,
  mode = 'add',
  initialData,
}: StockTargetDialogProps) {
  /* ── Core form state ───────────────────────────────────── */
  const [symbol,     setSymbol]     = useState(initialData?.symbol           || '');
  const [targetBuy,  setTargetBuy]  = useState(initialData?.targetBuy?.toString()  || '');
  const [targetSell, setTargetSell] = useState(initialData?.targetSell?.toString() || '');
  const [selected,   setSelected]   = useState<ListingIdentity | null>(null);

  /* ── Typeahead state ───────────────────────────────────── */
  const [suggestions,   setSuggestions]   = useState<StockSearchResult[]>([]);
  const [showDropdown,  setShowDropdown]  = useState(false);
  const [isSearching,   setIsSearching]   = useState(false);
  const [activeIndex,   setActiveIndex]   = useState(-1);   // keyboard nav
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef    = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  /* ── Reset on open ─────────────────────────────────────── */
  useEffect(() => {
    if (open) {
      setSymbol(    initialData?.symbol              || '');
      setTargetBuy( initialData?.targetBuy?.toString()  || '');
      setTargetSell(initialData?.targetSell?.toString() || '');
      setSelected(null);
      setSuggestions([]);
      setShowDropdown(false);
      setActiveIndex(-1);
    }
  }, [open, initialData]);

  /* ── Debounced search ──────────────────────────────────── */
  const runSearch = useCallback(async (q: string) => {
    if (q.length < 1) {
      setSuggestions([]);
      setShowDropdown(false);
      return;
    }
    setIsSearching(true);
    try {
      const results = await watchlistService.searchStocks(q);
      setSuggestions(results);
      setShowDropdown(results.length > 0);
      setActiveIndex(-1);
    } catch {
      setSuggestions([]);
      setShowDropdown(false);
    } finally {
      setIsSearching(false);
    }
  }, []);

  const handleSymbolChange = (raw: string) => {
    const val = raw.toUpperCase();
    setSymbol(val);
    setSelected(null);   // any manual edit invalidates a previously selected listing
    setActiveIndex(-1);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (val.length < 1) {
      setSuggestions([]);
      setShowDropdown(false);
      return;
    }
    debounceRef.current = setTimeout(() => runSearch(val), 300);
  };

  /* ── Select a suggestion ───────────────────────────────── */
  const selectSuggestion = (s: StockSearchResult) => {
    setSymbol(s.symbol);
    setSelected({
      security_id:     s.security_id,
      symbol:          s.symbol,
      exchange:        s.exchange,
      kind:            s.kind,
      currency:        s.currency,
      provider_symbol: s.provider_symbol,
    });
    setSuggestions([]);
    setShowDropdown(false);
    setActiveIndex(-1);
    if (debounceRef.current) clearTimeout(debounceRef.current);
  };

  /* ── Keyboard navigation ───────────────────────────────── */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showDropdown || suggestions.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(i => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, -1));
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      selectSuggestion(suggestions[activeIndex]);
    } else if (e.key === 'Escape') {
      setShowDropdown(false);
      setActiveIndex(-1);
    }
  };

  /* ── Save ──────────────────────────────────────────────── */
  const handleSave = () => {
    onSave({
      symbol:     symbol.toUpperCase(),
      targetBuy:  targetBuy  ? parseFloat(targetBuy)  : null,
      targetSell: targetSell ? parseFloat(targetSell) : null,
      listing:    selected ?? undefined,
    });
    if (mode === 'add') {
      setSymbol(''); setTargetBuy(''); setTargetSell('');
      setSelected(null);
      setSuggestions([]); setShowDropdown(false);
    }
    onOpenChange(false);
  };

  const isValid = symbol.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={[
          '!bg-[rgba(10,13,26,0.92)]',
          'border border-white/10',
          'shadow-[0_32px_80px_rgba(0,0,0,0.7)]',
          'backdrop-blur-[30px]',
          'rounded-3xl',
          'p-0 gap-0',
          'sm:max-w-md',
          'overflow-visible',   // allow dropdown to escape the dialog box
        ].join(' ')}
      >
        {/* ── Top gradient stripe ──────────────────────── */}
        <div
          className="h-px w-full rounded-t-3xl bg-[linear-gradient(90deg,transparent,rgba(99,102,241,0.6)_40%,rgba(139,92,246,0.4)_70%,transparent)]"
          aria-hidden="true"
        />

        {/* ── Header ───────────────────────────────────── */}
        <div className="px-8 pt-8 pb-6">
          <div className="flex items-center gap-3 mb-1">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
              {mode === 'add'
                ? <PlusCircle className="h-4 w-4 text-indigo-400" />
                : <Save        className="h-4 w-4 text-indigo-400" />
              }
            </div>
            <DialogTitle className="text-base font-black text-white tracking-tight">
              {mode === 'add' ? 'Add Stock' : `Edit ${symbol}`}
            </DialogTitle>
          </div>
          <DialogDescription className="text-xs text-white/35 ml-11">
            {mode === 'add'
              ? 'Search for a ticker and set optional price targets.'
              : 'Update your target prices for this position.'}
          </DialogDescription>
        </div>

        {/* ── Form body ────────────────────────────────── */}
        <div className="px-8 pb-8 space-y-4">

          {/* ── Symbol / Search ──────────────────────── */}
          <div className="space-y-2">
            <label
              htmlFor="dialog-symbol"
              className="block text-[10px] font-black uppercase tracking-[0.18em] text-white/30"
            >
              Ticker Symbol
            </label>

            {/* Input + dropdown wrapper — position:relative so dropdown anchors here */}
            <div className="relative">
              {/* Search icon / spinner */}
              <div className="pointer-events-none absolute inset-y-0 left-4 flex items-center">
                {isSearching
                  ? <div className="h-3.5 w-3.5 rounded-full border border-white/20 border-t-indigo-400 animate-spin" />
                  : <Search className="h-3.5 w-3.5 text-white/25" />
                }
              </div>

              {selected && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5 pointer-events-none">
                  <span className="text-[10px] font-mono text-indigo-300 bg-indigo-500/15 border border-indigo-500/30 px-1.5 py-0.5 rounded">
                    {selected.exchange}
                  </span>
                  {selected.kind === 'CDR' && (
                    <span className="text-[9px] font-black uppercase text-amber-300 bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 rounded">
                      CDR
                    </span>
                  )}
                </div>
              )}

              <input
                ref={inputRef}
                id="dialog-symbol"
                value={symbol}
                onChange={e => handleSymbolChange(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={() => {
                  // small delay so click on suggestion fires first
                  setTimeout(() => setShowDropdown(false), 150);
                }}
                onFocus={() => {
                  if (suggestions.length > 0) setShowDropdown(true);
                }}
                disabled={mode === 'edit'}
                placeholder="Search symbol or company…"
                autoComplete="off"
                autoCapitalize="characters"
                className={[
                  'w-full pl-10 py-3 rounded-xl text-sm font-bold',
                  selected ? 'pr-28' : 'pr-4',
                  'bg-white/5 border border-white/8 text-white',
                  'placeholder:text-white/20 placeholder:font-normal',
                  'focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15',
                  'transition-all duration-150',
                  mode === 'edit' && 'opacity-50 cursor-not-allowed',
                ].join(' ')}
              />

              {/* Suggestions dropdown */}
              {showDropdown && mode === 'add' && (
                <div
                  ref={dropdownRef}
                  className={[
                    'absolute z-50 left-0 right-0 mt-1.5',
                    'rounded-xl overflow-hidden',
                    'bg-[rgba(12,15,30,0.98)] border border-white/10',
                    'shadow-[0_16px_48px_rgba(0,0,0,0.7)]',
                    'backdrop-blur-xl',
                  ].join(' ')}
                >
                  {suggestions.map((s, i) => (
                    <button
                      key={s.security_id}
                      type="button"
                      data-testid="listing-suggestion"
                      data-security-id={s.security_id}
                      data-symbol={s.symbol}
                      data-exchange={s.exchange}
                      data-kind={s.kind}
                      onMouseDown={() => selectSuggestion(s)}   // mousedown fires before blur
                      className={[
                        'w-full flex items-center justify-between px-4 py-2.5 text-left',
                        'transition-colors duration-75 cursor-pointer',
                        i === activeIndex
                          ? 'bg-indigo-500/20'
                          : 'hover:bg-white/5',
                        i !== suggestions.length - 1 && 'border-b border-white/5',
                      ].join(' ')}
                    >
                      {/* Left: symbol + name */}
                      <div className="flex flex-col min-w-0">
                        <span className="text-sm font-black text-indigo-400 leading-tight">
                          {s.symbol}
                        </span>
                        <span className="text-[11px] text-white/50 truncate leading-tight mt-0.5">
                          {s.name}
                        </span>
                      </div>

                      {/* Right: exchange + type badge */}
                      <div className="flex items-center gap-2 ml-3 flex-shrink-0">
                        {s.exchange && (
                          <span className="text-[10px] text-white/30 font-mono">
                            {s.exchange}
                          </span>
                        )}
                        {s.type && (
                          <span className={[
                            'text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded-md border',
                            TYPE_STYLES[s.type] ?? 'bg-white/10 text-white/40 border-white/10',
                          ].join(' ')}>
                            {s.type}
                          </span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Target prices ────────────────────────── */}
          <div className="grid grid-cols-2 gap-3">
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
                onChange={e => setTargetBuy(e.target.value)}
                placeholder="Optional"
                className={[
                  'w-full px-4 py-3 rounded-xl text-sm font-bold',
                  'bg-white/5 border border-white/8 text-white',
                  'placeholder:text-white/20',
                  'focus:outline-none focus:border-emerald-500/60 focus:ring-2 focus:ring-emerald-500/15',
                  'transition-all duration-150',
                  '[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none',
                ].join(' ')}
              />
            </div>

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
                onChange={e => setTargetSell(e.target.value)}
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

          {/* ── Hint ─────────────────────────────────── */}
          <p className="text-[9px] text-white/20 leading-relaxed">
            Target prices are optional. You'll see alerts when the stock price crosses your targets.
          </p>

          {/* ── Actions ──────────────────────────────── */}
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
                : <><Save        className="h-3.5 w-3.5" /> Save Changes</>
              }
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}