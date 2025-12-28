'use client';

import type { Stock, WatchlistItem } from '@/lib/types';
import { useEffect, useState, useCallback, useMemo } from 'react';
import { StockCard } from './stock-card';
import { Button } from '../ui/button';
import { PlusCircle, TrendingUp, DollarSign, Target } from 'lucide-react';
import { AddStockDialog } from './add-stock-dialog';
import { useToast } from '@/hooks/use-toast';
import { getStockData, type StockData } from '@/ai/flows/stock-flow';
import {
  useCollection,
  useFirestore,
  useMemoFirebase,
  useUser,
  addDocumentNonBlocking,
  deleteDocumentNonBlocking,
} from '@/firebase';
import { collection, doc } from 'firebase/firestore';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { cn } from '@/lib/utils';


type AlertType = 'buy' | 'sell';
type TriggeredAlerts = {
  [stockId: string]: {
    [key in AlertType]?: boolean;
  };
};
type Notification = {
  id: string;
  title: string;
  description: string;
  timestamp: Date;
};

/**
 * The main component for displaying and managing the user's stock watchlist.
 * It handles fetching watchlist items from Firestore, fetching simulated stock data,
 * and orchestrating add/remove operations.
 */
export function Watchlist() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [isAddDialogOpen, setAddDialogOpen] = useState(false);
  const [triggeredAlerts, setTriggeredAlerts] = useState<TriggeredAlerts>({});
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');

  const { toast } = useToast();
  const { user } = useUser();
  const firestore = useFirestore();

  // Memoize the Firestore collection reference to prevent re-renders.
  const watchlistCollectionRef = useMemoFirebase(
    () => (user ? collection(firestore, `users/${user.uid}/watchlist`) : null),
    [user, firestore]
  );

  // Subscribe to the user's watchlist collection in Firestore.
  const { data: watchlistItems, isLoading } =
    useCollection<WatchlistItem>(watchlistCollectionRef);

  /**
   * Fetches simulated stock data for the symbols in the user's watchlist,
   * merges it with the watchlist item data (targets), and updates the local state.
   * Also triggers buy/sell toast notifications if targets are met.
   */
  const fetchStockData = useCallback(async () => {
    if (!watchlistItems) {
      if (watchlistItems === null) { // Explicitly check for null (initial state or empty)
        setStocks([]);
      }
      return;
    }
    if (watchlistItems.length === 0) {
      setStocks([]);
      return;
    }

    try {
      const symbols = watchlistItems.map((s) => s.symbol);
      const updatedStockData = await getStockData({ symbols });

      const newStocks: Stock[] = watchlistItems
        .map((item) => {
          const newData = updatedStockData.find((d) => d.symbol === item.symbol);
          if (!newData) return null;

          return {
            id: item.id,
            symbol: item.symbol,
            targetBuy: item.targetBuy ?? null,
            targetSell: item.targetSell ?? null,
            name: newData.name,
            price: newData.price,
            change: newData.change,
            changePercent: newData.changePercent,
          };
        })
        .filter((s): s is Stock => s !== null);

      setStocks(newStocks);
      
      // Check for alerts
      const newTriggeredAlerts: TriggeredAlerts = { ...triggeredAlerts };
      const newNotifications: Notification[] = [];

      newStocks.forEach((stock) => {
        const hasBuyAlertBeenTriggered = triggeredAlerts[stock.id]?.buy;
        if (stock.targetBuy && stock.price <= stock.targetBuy && !hasBuyAlertBeenTriggered) {
          const notification: Notification = {
            id: `${stock.id}-buy-${Date.now()}`,
            title: 'Buy Alert!',
            description: `${stock.symbol} has reached your buy target of $${stock.targetBuy.toFixed(2)}. Current price: $${stock.price.toFixed(2)}`,
            timestamp: new Date(),
          };
          newNotifications.push(notification);
          if (!newTriggeredAlerts[stock.id]) newTriggeredAlerts[stock.id] = {};
          newTriggeredAlerts[stock.id].buy = true;
        }

        const hasSellAlertBeenTriggered = triggeredAlerts[stock.id]?.sell;
        if (stock.targetSell && stock.price >= stock.targetSell && !hasSellAlertBeenTriggered) {
          const notification: Notification = {
            id: `${stock.id}-sell-${Date.now()}`,
            title: 'Sell Alert!',
            description: `${stock.symbol} has reached your sell target of $${stock.targetSell.toFixed(2)}. Current price: $${stock.price.toFixed(2)}`,
            timestamp: new Date(),
          };
          newNotifications.push(notification);
          if (!newTriggeredAlerts[stock.id]) newTriggeredAlerts[stock.id] = {};
          newTriggeredAlerts[stock.id].sell = true;
        }
      });

      if (newNotifications.length > 0) {
        newNotifications.forEach(n => toast({ title: n.title, description: n.description }));
        setNotifications(prev => [...prev, ...newNotifications]);
        setTriggeredAlerts(newTriggeredAlerts);
      }

    } catch (error) {
      console.error('Error fetching stock data:', error);
      toast({
        title: 'Error',
        description: 'Could not fetch latest stock data.',
        variant: 'destructive',
      });
    }
  }, [watchlistItems, toast, triggeredAlerts]);


  // Effect to periodically refresh stock data.
  useEffect(() => {
    fetchStockData();
    const interval = setInterval(fetchStockData, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, [fetchStockData]);

  /**
   * Handles adding a new stock to the watchlist.
   * It validates the stock symbol and then adds it to the Firestore collection.
   * @param {Omit<WatchlistItem, 'id' | 'userId'>} newStockData - The data for the new stock.
   */
  const handleAddStock = async (
    newStockData: Omit<WatchlistItem, 'id' | 'userId'>
  ) => {
    if (!watchlistCollectionRef || !user) return;
    try {
      // Validate that the stock symbol exists before adding.
      const stockInfo = await getStockData({ symbols: [newStockData.symbol] });
      if (stockInfo && stockInfo.length > 0) {
        const itemToAdd: Omit<WatchlistItem, 'id'> = {
          ...newStockData,
          userId: user.uid,
        };
        addDocumentNonBlocking(watchlistCollectionRef, itemToAdd);
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

  /**
   * Handles removing a stock from the user's watchlist in Firestore.
   * @param {string} stockId - The document ID of the stock to remove.
   */
  const handleRemoveStock = (stockId: string) => {
    if (!watchlistCollectionRef) return;
    const docRef = doc(watchlistCollectionRef, stockId);
    deleteDocumentNonBlocking(docRef);
  };
  
  const buyTriggeredStocks = useMemo(() => stocks.filter(stock => stock.targetBuy && stock.price <= stock.targetBuy), [stocks]);
  const sellTriggeredStocks = useMemo(() => stocks.filter(stock => stock.targetSell && stock.price >= stock.targetSell), [stocks]);

  const filteredStocks = useMemo(() => {
    switch (filter) {
      case 'buy':
        return buyTriggeredStocks;
      case 'sell':
        return sellTriggeredStocks;
      default:
        return stocks;
    }
  }, [filter, stocks, buyTriggeredStocks, sellTriggeredStocks]);


  // Display a loading spinner while fetching initial watchlist data.
  if (isLoading) {
     return (
      <div className="flex flex-1 items-start justify-center rounded-lg border border-dashed shadow-sm p-8">
        <div className="h-16 w-16 animate-spin rounded-full border-4 border-dashed border-primary"></div>
      </div>
    );
  }

  // Display a welcome/empty state message if the watchlist is empty.
  if (stocks.length === 0 && watchlistItems?.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center p-8">
        <TrendingUp className="h-16 w-16 text-muted-foreground" />
        <h3 className="text-2xl font-bold tracking-tight">
          Your watchlist is empty
        </h3>
        <p className="text-sm text-muted-foreground">
          Start tracking stocks by adding them to your watchlist.
        </p>
        <Button onClick={() => setAddDialogOpen(true)}>
          <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
        </Button>
        <AddStockDialog
          open={isAddDialogOpen}
          onOpenChange={setAddDialogOpen}
          onAddStock={handleAddStock}
        />
      </div>
    );
  }

  // Display the grid of stock cards.
  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-0">
      <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-3 mb-6">
        <Card
            className={cn('cursor-pointer hover:bg-muted/50', filter === 'all' && 'bg-muted')}
            onClick={() => setFilter('all')}
          >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">All Stocks</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stocks.length}</div>
            <p className="text-xs text-muted-foreground">
              Total stocks in your watchlist
            </p>
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
            <p className="text-xs text-muted-foreground">
              Stocks at or below your buy target
            </p>
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
            <p className="text-xs text-muted-foreground">
              Stocks at or above your sell target
            </p>
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
          <StockCard key={stock.id} stock={stock} onRemove={handleRemoveStock} />
        ))}
      </div>
       {filteredStocks.length === 0 && (
          <div className="col-span-1 md:col-span-2 lg:col-span-3 text-center text-muted-foreground py-10">
             {stocks.length === 0 && !isLoading ? (
               <div className="flex flex-1 items-start justify-center rounded-lg p-8">
                  <div className="h-16 w-16 animate-spin rounded-full border-4 border-dashed border-primary"></div>
               </div>
             ) : 'No stocks match the current filter.'}
          </div>
        )}
      <AddStockDialog
        open={isAddDialogOpen}
        onOpenChange={setAddDialogOpen}
        onAddStock={handleAddStock}
      />
    </div>
  );
}