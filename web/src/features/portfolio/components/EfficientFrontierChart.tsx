'use client';

import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    ResponsiveContainer,
    ZAxis,
    ReferenceLine,
    Legend,
} from 'recharts';
import type { EfficientFrontierResponse, EfficientFrontierPoint } from '../types/portfolio.types';

interface EfficientFrontierChartProps {
    data: EfficientFrontierResponse | undefined;
    isLoading: boolean;
    isError: boolean;
}

export function EfficientFrontierChart({ data, isLoading, isError }: EfficientFrontierChartProps) {
    if (isError) {
        return (
            <div className="glass-panel p-6">
                <h4 className="text-xs font-black text-white/60 uppercase tracking-widest mb-4">
                    Efficient Frontier
                </h4>
                <div className="h-[300px] flex items-center justify-center">
                    <p className="text-white/20 text-sm">Unable to load efficient frontier</p>
                </div>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="glass-panel p-6">
                <div className="h-5 w-32 rounded bg-white/5 animate-pulse mb-4" />
                <div className="h-[300px] rounded-xl bg-white/[0.02]" />
            </div>
        );
    }

    if (!data || !data.frontier || data.frontier.length === 0) {
        return (
            <div className="glass-panel p-6">
                <h4 className="text-xs font-black text-white/60 uppercase tracking-widest mb-4">
                    Efficient Frontier
                </h4>
                <div className="h-[300px] flex items-center justify-center">
                    <p className="text-white/20 text-sm">No frontier data available</p>
                </div>
            </div>
        );
    }

    const frontierData = data.frontier.map((p) => ({
        volatility: +(p.volatility * 100).toFixed(2),
        expectedReturn: +(p.expected_return * 100).toFixed(2),
    }));

    const msPoint = data.max_sharpe
        ? {
            volatility: +(data.max_sharpe.volatility * 100).toFixed(2),
            expectedReturn: +(data.max_sharpe.expected_return * 100).toFixed(2),
        }
        : null;

    const mvPoint = data.min_variance
        ? {
            volatility: +(data.min_variance.volatility * 100).toFixed(2),
            expectedReturn: +(data.min_variance.expected_return * 100).toFixed(2),
        }
        : null;

    return (
        <div className="glass-panel p-6">
            <h4 className="text-xs font-black text-white/60 uppercase tracking-widest mb-4">
                Efficient Frontier
            </h4>
            <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                        <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="rgba(255,255,255,0.06)"
                        />
                        <XAxis
                            type="number"
                            dataKey="volatility"
                            name="Volatility"
                            tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                            tickFormatter={(val: number) => `${val}%`}
                            label={{
                                value: 'Volatility',
                                position: 'bottom',
                                fill: 'rgba(255,255,255,0.3)',
                                fontSize: 11,
                                offset: -5,
                            }}
                        />
                        <YAxis
                            type="number"
                            dataKey="expectedReturn"
                            name="Expected Return"
                            tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                            tickFormatter={(val: number) => `${val}%`}
                            domain={['auto', 'auto']}
                            label={{
                                value: 'Expected Return',
                                angle: -90,
                                position: 'insideLeft',
                                fill: 'rgba(255,255,255,0.3)',
                                fontSize: 11,
                                offset: 10,
                            }}
                        />
                        <ZAxis range={[60, 60]} />
                        <ReferenceLine y={0} stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                        <Tooltip
                            contentStyle={{
                                background: 'rgba(12,15,28,0.95)',
                                border: '1px solid rgba(255,255,255,0.1)',
                                borderRadius: '12px',
                                backdropFilter: 'blur(20px)',
                            }}
                            labelStyle={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}
                            itemStyle={{ fontSize: 13 }}
                            formatter={(value: number, name: string) => [
                                `${value}%`,
                                name === 'Volatility' ? 'Volatility' : 'Expected Return',
                            ]}
                        />
                        <Legend
                            wrapperStyle={{ fontSize: 12, color: 'rgba(255,255,255,0.5)' }}
                        />
                        <Scatter
                            name="Frontier"
                            data={frontierData}
                            fill="#818cf8"
                            fillOpacity={0.6}
                            shape="circle"
                        />
                        {msPoint && (
                            <Scatter
                                name="Max Sharpe"
                                data={[msPoint]}
                                fill="#34d399"
                                shape="diamond"
                            />
                        )}
                        {mvPoint && (
                            <Scatter
                                name="Min Variance"
                                data={[mvPoint]}
                                fill="#f59e0b"
                                shape="triangle"
                            />
                        )}
                    </ScatterChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
