'use client';

interface GoalProgressCardProps {
    monthlyIncome: number;
    monthlyGoal: number | null;
    onSetGoal?: () => void;
}

export function GoalProgressCard({ monthlyIncome, monthlyGoal, onSetGoal }: GoalProgressCardProps) {
    const pct = monthlyGoal && monthlyGoal > 0 ? Math.min(100, (monthlyIncome / monthlyGoal) * 100) : 0;

    return (
        <div className="glass-panel rounded-lg p-4">
            <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-2">Goal Progress</p>
            {monthlyGoal ? (
                <>
                    <div className="flex items-center justify-between text-sm mb-1.5">
                        <span className="text-white font-bold">${monthlyIncome.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                        <span className="text-white/40">/ ${monthlyGoal.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                    </div>
                    <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-500"
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                    <p className="text-xs text-white/30 mt-1">{pct.toFixed(1)}% of monthly goal</p>
                </>
            ) : (
                <>
                    <p className="text-lg font-bold text-white">${monthlyIncome.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
                    <p className="text-xs text-white/30 mt-1">Set a monthly income goal to track progress.</p>
                    {onSetGoal && (
                        <button onClick={onSetGoal} className="text-xs text-blue-400 hover:text-blue-300 mt-1">
                            Set goal
                        </button>
                    )}
                </>
            )}
        </div>
    );
}
