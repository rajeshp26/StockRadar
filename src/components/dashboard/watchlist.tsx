
'use client';

import { useState, useMemo } from 'react';
import { StockCard } from './stock-card';
import { Button } from '../ui/button';
import { PlusCircle, TrendingUp, DollarSign } from 'lucide-react';
import { StockTargetDialog } from './add-stock-dialog';
import { useAuth } from '../auth/auth-provider';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { cn } from '@/lib/utils';
import { useWatchlist } from '@/features/watchlists/hooks/useWatchlist';
import { StockPriceInfo } from '@/features/watchlists/types/watchlist.types';

export function Watchlist() {
  const [isAddDialogOpen, setAddDialogOpen] = useState(false);
  const [isEditDialogOpen, setEditDialogOpen] = useState(false);
  const [editingStock, setEditingStock] = useState<StockPriceInfo | null>(null);
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');

  const { loading: isAuthLoading } = useAuth();
  
  // All business logic is now encapsulated in this hook
  const { 
    stocks, 
    isLoading, 
    addStock, 
    updateTargets, 
    removeStock 
  } = useWatchlist();

  const buyTriggeredStocks = useMemo(() => 
    stocks.filter(stock => stock.targetBuy && stock.price <= stock.targetBuy), 
    [stocks]
  );
  
  const sellTriggeredStocks = useMemo(() => 
    stocks.filter(stock => stock.targetSell && stock.price >= stock.targetSell), 
    [stocks]
  );

  const filteredStocks = useMemo(() => {
    switch (filter) {
      case 'buy': return buyTriggeredStocks;
      case 'sell': return sellTriggeredStocks;
      default: return stocks;
    }
  }, [filter, stocks, buyTriggeredStocks, sellTriggeredStocks]);

  if (isLoading || isAuthLoading) {
    return (
      <div className="flex flex-1 items-start justify-center p-8">
        <div className="h-16 w-16 animate-spin rounded-full border-4 border-dashed border-primary"></div>
      </div>
    );
  }

  if (stocks.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center p-8">
        <TrendingUp className="h-16 w-16 text-muted-foreground" />
        <h3 className="text-2xl font-bold tracking-tight">Your watchlist is empty</h3>
        <Button onClick={() => setAddDialogOpen(true)}>
          <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
        </Button>
        <StockTargetDialog 
          open={isAddDialogOpen} 
          onOpenChange={setAddDialogOpen} 
          onSave={(data) => addStock(data.symbol, data.targetBuy, data.targetSell)} 
        />
      </div>
    );
  }

  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-0">
       <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-3 mb-6">
        <Card 
          className={cn('cursor-pointer hover:bg-muted/50', filter === 'all' && 'bg-muted')} 
          onClick={() => setFilter('all')}
        >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">All Stocks</CardTitle>
            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stocks.length}</div>
          </CardContent>
        </Card>
        
        <Card 
          className={cn('cursor-pointer hover:bg-muted/50', filter === 'buy' && 'bg-muted')} 
          onClick={() => setFilter('buy')}
        >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Buy Alerts</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{buyTriggeredStocks.length}</div>
          </CardContent>
        </Card>
        
        <Card 
          className={cn('cursor-pointer hover:bg-muted/50', filter === 'sell' && 'bg-muted')} 
          onClick={() => setFilter('sell')}
        >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sell Alerts</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{sellTriggeredStocks.length}</div>
          </CardContent>
        </Card>
      </div>

      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">
            {filter === 'buy' && 'Buy Alert Stocks'}
            {filter === 'sell' && 'Sell Alert Stocks'}
            {filter === 'all' && 'My Watchlist'}
        </h2>
        <Button onClick={() => setAddDialogOpen(true)}>
          <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
        </Button>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredStocks.map((stock) => (
          <StockCard 
            key={stock.id} 
            stock={stock as any} 
            onRemove={() => removeStock(stock.id)} 
            onEdit={(s) => {
              setEditingStock(s as any);
              setEditDialogOpen(true);
            }}
          />
        ))}
      </div>
      
      <StockTargetDialog 
        open={isAddDialogOpen} 
        onOpenChange={setAddDialogOpen} 
        onSave={(data) => addStock(data.symbol, data.targetBuy, data.targetSell)} 
        mode="add"
      />
      
      <StockTargetDialog 
        open={isEditDialogOpen} 
        onOpenChange={setEditDialogOpen} 
        onSave={(data) => editingStock && updateTargets(editingStock.id, data.targetBuy, data.targetSell)} 
        mode="edit"
        initialData={editingStock ? {
          symbol: editingStock.symbol,
          targetBuy: editingStock.targetBuy,
          targetSell: editingStock.targetSell
        } : undefined}
      />
    </div>
  );
}
