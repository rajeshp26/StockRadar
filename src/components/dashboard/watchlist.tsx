'use client';

import type { Stock } from '@/lib/types';
import { useEffect, useState } from 'react';
import { StockCard } from './stock-card';
import { Button } from '../ui/button';
import { PlusCircle, Bell, TrendingUp } from 'lucide-react';
import { AddStockDialog } from './add-stock-dialog';
import { useToast } from '@/hooks/use-toast';

type WatchlistProps = {
  initialStocks: Stock[];
};

export function Watchlist({ initialStocks }: WatchlistProps) {
  const [stocks, setStocks] = useState<Stock[]>(initialStocks);
  const [isAddDialogOpen, setAddDialogOpen] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    const interval = setInterval(() => {
      setStocks((currentStocks) =>
        currentStocks.map((stock) => {
          const change = (Math.random() - 0.5) * 2; // a value between -1 and 1
          const newPrice = Math.max(0, stock.price + change);
          const changePercent = (change / stock.price) * 100;

          // Check for alerts
          if (stock.targetBuy && newPrice <= stock.targetBuy) {
            toast({
              title: 'Buy Alert!',
              description: `${stock.symbol} has reached your buy target of $${stock.targetBuy.toFixed(2)}. Current price: $${newPrice.toFixed(2)}`,
              variant: 'default',
            });
          }
          if (stock.targetSell && newPrice >= stock.targetSell) {
             toast({
              title: 'Sell Alert!',
              description: `${stock.symbol} has reached your sell target of $${stock.targetSell.toFixed(2)}. Current price: $${newPrice.toFixed(2)}`,
              variant: 'default',
            });
          }

          return {
            ...stock,
            price: newPrice,
            change,
            changePercent,
          };
        })
      );
    }, 2000); // Update every 2 seconds

    return () => clearInterval(interval);
  }, [toast]);

  const handleAddStock = (newStockData: Omit<Stock, 'id' | 'name' | 'price' | 'change' | 'changePercent'>) => {
    // In a real app, you'd fetch the stock name and current price from an API
    const newStock: Stock = {
      id: (stocks.length + 1).toString(),
      name: `${newStockData.symbol} Company`,
      price: Math.random() * 500, // mock price
      change: 0,
      changePercent: 0,
      ...newStockData,
    };
    setStocks([...stocks, newStock]);
  };

  const handleRemoveStock = (stockId: string) => {
    setStocks(stocks.filter((stock) => stock.id !== stockId));
  };
  
  if (stocks.length === 0) {
    return (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center p-8">
            <TrendingUp className="h-16 w-16 text-muted-foreground" />
            <h3 className="text-2xl font-bold tracking-tight">Your watchlist is empty</h3>
            <p className="text-sm text-muted-foreground">
                Start tracking stocks by adding them to your watchlist.
            </p>
            <Button onClick={() => setAddDialogOpen(true)}>
                <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
            </Button>
            <AddStockDialog open={isAddDialogOpen} onOpenChange={setAddDialogOpen} onAddStock={handleAddStock} />
        </div>
    );
  }

  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-0">
      <div className="flex justify-end mb-4">
        <Button onClick={() => setAddDialogOpen(true)}>
          <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
        </Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {stocks.map((stock) => (
          <StockCard key={stock.id} stock={stock} onRemove={handleRemoveStock} />
        ))}
      </div>
      <AddStockDialog open={isAddDialogOpen} onOpenChange={setAddDialogOpen} onAddStock={handleAddStock} />
    </div>
  );
}
