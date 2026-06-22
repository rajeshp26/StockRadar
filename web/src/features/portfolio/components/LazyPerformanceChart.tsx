'use client';

import { useEffect, useRef, useState } from 'react';
import { PortfolioPerformanceChart } from './PortfolioPerformanceChart';

export function LazyPerformanceChart() {
    const ref = useRef<HTMLDivElement>(null);
    const [inView, setInView] = useState(false);

    useEffect(() => {
        const el = ref.current;
        if (!el) return;

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setInView(true);
                    observer.disconnect();
                }
            },
            { rootMargin: '200px', threshold: 0 }
        );

        observer.observe(el);
        return () => observer.disconnect();
    }, []);

    return (
        <div ref={ref} className="lg:col-span-2 min-h-[200px]">
            {inView ? (
                <PortfolioPerformanceChart />
            ) : (
                <div className="glass-panel p-6">
                    <div className="h-[300px] rounded-xl bg-white/[0.02]" />
                </div>
            )}
        </div>
    );
}
