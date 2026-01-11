'use client';

import { useEffect, useState } from 'react';
import { perf } from '@/lib/performance';

// Mock API function to simulate fetching data
async function getWatchlistItems() {
  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, Math.random() * 400 + 100)); 
  return [
    { id: 1, name: 'Bitcoin', ticker: 'BTC' },
    { id: 2, name: 'Ethereum', ticker: 'ETH' },
    { id: 3, name: 'Cardano', ticker: 'ADA' },
  ];
}

export default function WatchlistPage() {
  const [items, setItems] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      perf.mark('watchlist-data-start'); // Total client-side processing start
      
      try {
        perf.mark('watchlist-api-start'); // API request start
        const data = await getWatchlistItems();
        perf.mark('watchlist-api-end'); // API request end
        perf.measure('API Request: Watchlist Items', 'watchlist-api-start', 'watchlist-api-end');
        
        // Simulate some client-side processing/rendering time
        await new Promise(resolve => setTimeout(resolve, 50));
        
        setItems(data);
      } catch (error) {
        console.error("Failed to fetch watchlist items:", error);
      } finally {
        setIsLoading(false);
        perf.mark('watchlist-data-end'); // Total client-side processing end
        perf.measure('Total Data Load: Watchlist', 'watchlist-data-start', 'watchlist-data-end');
      }
    };
    
    fetchData();
  }, []);

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">My Watchlist</h1>
      {isLoading ? (
        <p>Loading watchlist...</p>
      ) : (
        <ul className="divide-y divide-gray-200">
          {items.map(item => (
            <li key={item.id} className="py-2">
              <span className="font-bold">{item.name}</span> ({item.ticker})
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
