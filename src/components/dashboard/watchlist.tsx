'use client';

import type { Stock } from '@/lib/types';
import { useEffect, useState, useCallback } from 'react';
import { StockCard } from './stock-card';
import { Button } from '../ui/button';
import { PlusCircle, TrendingUp } from 'lucide-react';
import { AddStockDialog } from './add-stock-dialog';
import { useToast } from '@/hooks/use-toast';
import { getStockData } from '@/ai/flows/stock-flow';

type WatchlistProps = {
  initialStocks: Stock[];
};

export function Watchlist({ initialStocks }: WatchlistProps) {
  const [stocks, setStocks] = useState<Stock[]>(initialStocks);
  const [isAddDialogOpen, setAddDialogOpen] = useState(false);
  const { toast } = useToast();

  const fetchStockData = useCallback(async () => {
    if (stocks.length === 0) return;

    try {
      const symbols = stocks.map(s => s.symbol);
      const stockData = await getStockData({ symbols });
      
      setStocks(currentStocks => {
        return currentStocks.map(stock => {
          const newData = stockData.find(d => d.symbol === stock.symbol);
          if (!newData) return stock;

          const newPrice = newData.price;
          // Check for alerts
          if (stock.targetBuy && newPrice <= stock.targetBuy) {
            toast({
              title: 'Buy Alert!',
              description: `${stock.symbol} has reached your buy target of $${stock.targetBuy.toFixed(2)}. Current price: $${newPrice.toFixed(2)}`,
            });
          }
          if (stock.targetSell && newPrice >= stock.targetSell) {
             toast({
              title: 'Sell Alert!',
              description: `${stock.symbol} has reached your sell target of $${stock.targetSell.toFixed(2)}. Current price: $${newPrice.toFixed(2)}`,
            });
          }

          return {
            ...stock,
            price: newPrice,
            change: newData.change,
            changePercent: newData.changePercent,
            name: newData.name,
          };
        });
      });
    } catch (error) {
      console.error('Error fetching stock data:', error);
      toast({
        title: 'Error',
        description: 'Could not fetch latest stock data.',
        variant: 'destructive',
      });
    }
  }, [stocks, toast]);

  useEffect(() => {
    const interval = setInterval(fetchStockData, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, [fetchStockData]);

  const handleAddStock = async (newStockData: Omit<Stock, 'id' | 'name' | 'price' | 'change' | 'changePercent'>) => {
    try {
        const stockInfo = await getStockData({ symbols: [newStockData.symbol] });
        if (stockInfo && stockInfo.length > 0) {
            const newStock: Stock = {
                id: (stocks.length + 1).toString(),
                ...stockInfo[0],
                targetBuy: newStockData.targetBuy,
                targetSell: newStockData.targetSell,
            };
            setStocks([...stocks, newStock]);
        } else {
             toast({
                title: 'Error',
                description: `Could not find stock with symbol ${newStockData.symbol}.`,
                variant: 'destructive',
            });
        }
    } catch (error) {
        console.error('Error adding stock:', error);
        toast({
            title: 'Error',
            description: 'An error occurred while adding the stock.',
            variant: 'destructive',
        });
    }
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
