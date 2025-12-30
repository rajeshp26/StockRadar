
'use client';

import type { Stock } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, X } from 'lucide-react';

interface StockCardProps {
  stock: Stock;
  onRemove: (stockId: number) => void; // Changed to number
}

export function StockCard({ stock, onRemove }: StockCardProps) {
  const isPositiveChange = stock.change >= 0;

  return (
    <Card className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-2 right-2 h-6 w-6"
        onClick={() => onRemove(stock.id)} // stock.id is now a number
      >
        <X className="h-4 w-4" />
        <span className="sr-only">Remove stock</span>
      </Button>
      <CardHeader>
        <CardTitle className="text-xl">{stock.symbol}</CardTitle>
        <CardDescription className="truncate">{stock.name}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        <div className="text-3xl font-bold">${stock.price.toFixed(2)}</div>
        <div className={cn('flex items-center gap-1 text-sm', isPositiveChange ? 'text-green-500' : 'text-red-500')}>
          {isPositiveChange ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
          <span>
            {stock.change.toFixed(2)} ({stock.changePercent.toFixed(2)}%)
          </span>
        </div>
         {(stock.targetBuy || stock.targetSell) && (
            <div className="text-xs text-muted-foreground pt-2 border-t mt-2">
              {stock.targetBuy && <p>Buy Target: ${stock.targetBuy.toFixed(2)}</p>}
              {stock.targetSell && <p>Sell Target: ${stock.targetSell.toFixed(2)}</p>}
            </div>
          )}
      </CardContent>
    </Card>
  );
}
