
'use client';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { Stock } from '@/lib/types';
import { MoreHorizontal, TrendingDown, TrendingUp, Trash2, Edit } from 'lucide-react';
import { useEffect, useState } from 'react';

/**
 * Props for the StockCard component.
 */
type StockCardProps = {
  stock: Stock;
  onRemove: (stockId: string) => void;
};

/**
 * A card component that displays detailed information about a single stock
 * from the user's watchlist, including its price, daily change, and target prices.
 * It also provides options to edit or remove the stock.
 * @param {StockCardProps} props - The component props.
 * @returns {JSX.Element} The rendered stock card.
 */
export function StockCard({ stock, onRemove }: StockCardProps) {
  const [priceFlash, setPriceFlash] = useState('');

  // Creates a visual "flash" effect on the price when it updates.
  useEffect(() => {
    setPriceFlash(stock.change > 0 ? 'bg-green-500/20' : 'bg-red-500/20');
    const timer = setTimeout(() => setPriceFlash(''), 500);
    return () => clearTimeout(timer);
  }, [stock.price, stock.change]);

  const isPositiveChange = stock.change >= 0;

  return (
    <Card className="w-full">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className='flex flex-col'>
          <CardTitle className="text-2xl font-bold">{stock.symbol}</CardTitle>
          <CardDescription>{stock.name}</CardDescription>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem>
              <Edit className="mr-2 h-4 w-4" />
              Edit
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-destructive"
              onClick={() => onRemove(stock.id)}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            'text-3xl font-bold transition-colors duration-500 rounded-md px-2 py-1 -mx-2',
            priceFlash
          )}
        >
          ${stock.price.toFixed(2)}
        </div>
        <p
          className={cn(
            'text-xs text-muted-foreground flex items-center',
            isPositiveChange ? 'text-green-600' : 'text-red-600'
          )}
        >
          {isPositiveChange ? (
            <TrendingUp className="mr-1 h-4 w-4" />
          ) : (
            <TrendingDown className="mr-1 h-4 w-4" />
          )}
          {stock.change.toFixed(2)} ({stock.changePercent.toFixed(2)}%)
        </p>
        <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div>
                <p className="text-muted-foreground">Buy Target</p>
                <p className="font-medium">${stock.targetBuy ? stock.targetBuy.toFixed(2) : 'N/A'}</p>
            </div>
            <div>
                <p className="text-muted-foreground">Sell Target</p>
                <p className="font-medium">${stock.targetSell ? stock.targetSell.toFixed(2) : 'N/A'}</p>
            </div>
        </div>
      </CardContent>
    </Card>
  );
}
