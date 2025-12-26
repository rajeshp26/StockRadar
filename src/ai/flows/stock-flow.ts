'use server';
/**
 * @fileOverview A flow for retrieving simulated stock data.
 *
 * - getStockData - A function that returns simulated data for a list of stock symbols.
 * - StockDataInput - The input type for the getStockData function.
 * - StockDataOutput - The return type for the getStockData function.
 */

import { ai } from '@/ai/genkit';
import { z } from 'zod';

// Mock database of stock information
const stockDatabase: Record<string, { name: string; basePrice: number }> = {
  AAPL: { name: 'Apple Inc.', basePrice: 172.25 },
  GOOGL: { name: 'Alphabet Inc.', basePrice: 139.74 },
  MSFT: { name: 'Microsoft Corp.', basePrice: 335.94 },
  AMZN: { name: 'Amazon.com, Inc.', basePrice: 134.25 },
  TSLA: { name: 'Tesla, Inc.', basePrice: 263.62 },
  NFLX: { name: 'Netflix, Inc.', basePrice: 440.50 },
  NVDA: { name: 'NVIDIA Corporation', basePrice: 475.69 },
  META: { name: 'Meta Platforms, Inc.', basePrice: 310.86 },
};


const StockDataInputSchema = z.object({
  symbols: z.array(z.string()).describe('An array of stock ticker symbols.'),
});
export type StockDataInput = z.infer<typeof StockDataInputSchema>;

const StockDataSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  price: z.number(),
  change: z.number(),
  changePercent: z.number(),
});

const StockDataOutputSchema = z.array(StockDataSchema);

export type StockData = z.infer<typeof StockDataSchema>;
export type StockDataOutput = z.infer<typeof StockDataOutputSchema>;

export async function getStockData(input: StockDataInput): Promise<StockDataOutput> {
  return getStockDataFlow(input);
}

const getStockDataFlow = ai.defineFlow(
  {
    name: 'getStockDataFlow',
    inputSchema: StockDataInputSchema,
    outputSchema: StockDataOutputSchema,
  },
  async ({ symbols }) => {
    const stockData = symbols
      .map((symbol) => {
        const stockInfo = stockDatabase[symbol.toUpperCase()];
        if (!stockInfo) {
          return null;
        }

        // Simulate price fluctuation
        const fluctuation = (Math.random() - 0.5) * 0.1; // Fluctuate by up to 5%
        const newPrice = stockInfo.basePrice * (1 + fluctuation);
        const change = newPrice - stockInfo.basePrice;
        const changePercent = (change / stockInfo.basePrice) * 100;

        return {
          symbol: symbol.toUpperCase(),
          name: stockInfo.name,
          price: newPrice,
          change,
          changePercent,
        };
      })
      .filter((data): data is StockData => data !== null);

    return stockData;
  }
);
