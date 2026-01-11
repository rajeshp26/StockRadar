'use client';

import React, { createContext, useContext, useMemo } from 'react';
import { api } from '@/lib/api';
import { WatchlistService } from '@/features/watchlists/services/watchlist.service';

interface ServiceContextType {
  watchlistService: WatchlistService;
}

const ServiceContext = createContext<ServiceContextType | null>(null);

export const ServiceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const services = useMemo(() => ({
    watchlistService: new WatchlistService(api),
  }), []);

  return (
    <ServiceContext.Provider value={services}>
      {children}
    </ServiceContext.Provider>
  );
};

export const useServices = () => {
  const context = useContext(ServiceContext);
  if (!context) {
    throw new Error('useServices must be used within a ServiceProvider');
  }
  return context;
};
