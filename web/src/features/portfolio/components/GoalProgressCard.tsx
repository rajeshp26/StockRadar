'use client';

interface GoalProgressCardProps {
    monthlyIncome: number;
    monthlyGoal: number | null;
    onSetGoal?: () => void;
}

export function GoalProgressCard({ monthlyIncome, monthlyGoal, onSetGoal }: GoalProgressCardProps) {
    const pct = monthlyGoal && monthlyGoal > 0 ? Math.min(100, (monthlyIncome / monthlyGoal) * 100) : 0;

    return (
        <div className="glass-stat">
            <p className="glass-overline">Goal Progress</p>
            {monthlyGoal ? (
                <>
                    <div className="flex items-center justify-between text-sm mb-1.5">
                        <span className="text-white font-black text-lg">${monthlyIncome.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                        <span className="text-white/40">/ ${monthlyGoal.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                    </div>
                    <div className="w-full h-1.5 bg-white/8 rounded-full overflow-hidden mt-2">
                        <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                                width: `${pct}%`,
                                background: "linear-gradient(90deg, #34d399, #6366f1)",
                            }}
                        />
                    </div>
                    <p className="text-[10px] text-white/30 mt-1.5">{pct.toFixed(1)}% of monthly goal</p>
                </>
            ) : (
                <>
                    <p className="text-2xl font-black tracking-tighter text-white">${monthlyIncome.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
                    <p className="text-[10px] text-white/30 mt-1">Set a monthly income goal to track progress.</p>
                    {onSetGoal && (
                        <button onClick={onSetGoal} className="text-[10px] text-indigo-400 font-black uppercase tracking-widest hover:text-indigo-300 mt-1">
                            Set goal
                        </button>
                    )}
                </>
            )}
        </div>
    );
}
