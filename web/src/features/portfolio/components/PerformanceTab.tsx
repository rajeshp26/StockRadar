'use client';

import { PortfolioPerformanceChart } from './PortfolioPerformanceChart';

interface PerformanceTabProps {
    accountIds?: number[];
}

export function PerformanceTab({ accountIds }: PerformanceTabProps) {
    return (
        <div className="space-y-6">
            <PortfolioPerformanceChart />
        </div>
    );
}
