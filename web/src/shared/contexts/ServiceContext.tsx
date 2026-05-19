'use client';

import { createContext, useContext } from 'react';
import { WatchlistService, watchlistService } from '@/features/watchlists/services/watchlist.service';
import { PortfolioService, portfolioService } from '@/features/portfolio/services/portfolio.service';

interface ServiceContextType {
  watchlistService: WatchlistService;
  portfolioService: PortfolioService;
}

const ServiceContext = createContext<ServiceContextType | null>(null);

export function ServiceProvider({ children }: { children: React.ReactNode }) {
  return (
    <ServiceContext.Provider
      value={{
        watchlistService,
        portfolioService,
      }}
    >
      {children}
    </ServiceContext.Provider>
  );
}

export const useServices = () => {
  const context = useContext(ServiceContext);
  if (!context) {
    throw new Error('useServices must be used within a ServiceProvider');
  }
  return context;
};