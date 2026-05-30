'use client';

import { cn } from '@/lib/utils';
import { TAB_DEFINITIONS, type TabId } from '../types/portfolio.types';
import {
    LayoutDashboard,
    TrendingUp,
    PieChart,
    DollarSign,
    Receipt,
    Shield,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

const ICON_MAP: Record<string, LucideIcon> = {
    LayoutDashboard,
    TrendingUp,
    PieChart,
    DollarSign,
    Receipt,
    Shield,
};

interface TabBarProps {
    activeTab: TabId;
    onTabChange: (tab: TabId) => void;
    showTransactions?: boolean;
}

export function TabBar({ activeTab, onTabChange, showTransactions = true }: TabBarProps) {
    const visibleTabs = showTransactions
        ? TAB_DEFINITIONS
        : TAB_DEFINITIONS.filter((t) => t.id !== 'transactions');

    return (
        <div className="flex items-center gap-1 overflow-x-auto border-b border-white/10">
            {visibleTabs.map((tab) => {
                const Icon = ICON_MAP[tab.icon] || LayoutDashboard;
                const isActive = activeTab === tab.id;

                return (
                    <button
                        key={tab.id}
                        onClick={() => onTabChange(tab.id)}
                        className={cn(
                            'flex items-center gap-2 px-4 py-3 text-xs font-bold transition-all whitespace-nowrap border-b-2 -mb-px',
                            isActive
                                ? 'text-blue-400 border-blue-400'
                                : 'text-white/40 border-transparent hover:text-white/60 hover:border-white/20'
                        )}
                    >
                        <Icon className="h-3.5 w-3.5" />
                        {tab.label}
                    </button>
                );
            })}
        </div>
    );
}
