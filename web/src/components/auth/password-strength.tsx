'use client';

import { useMemo } from 'react';

interface PasswordStrengthProps {
  password: string;
}

type StrengthLevel = 'empty' | 'weak' | 'fair' | 'good' | 'strong';

const STRENGTH_CONFIG: Record<StrengthLevel, { width: string; color: string; label: string }> = {
  empty: { width: '0%', color: 'bg-gray-600', label: '—' },
  weak: { width: '25%', color: 'bg-red-500', label: 'Weak' },
  fair: { width: '50%', color: 'bg-yellow-500', label: 'Fair' },
  good: { width: '75%', color: 'bg-blue-500', label: 'Good' },
  strong: { width: '100%', color: 'bg-green-500', label: 'Strong' },
};

function calculateStrength(pw: string): StrengthLevel {
  if (!pw) return 'empty';

  const checks = [
    pw.length >= 12,
    /[A-Z]/.test(pw),
    /[a-z]/.test(pw),
    /[0-9]/.test(pw),
    /[^A-Za-z0-9]/.test(pw),
  ];

  const count = checks.filter(Boolean).length;

  if (count <= 1) return 'weak';
  if (count === 2) return 'fair';
  if (count <= 4) return 'good';
  return 'strong';
}

export function PasswordStrength({ password }: PasswordStrengthProps) {
  const level = useMemo(() => calculateStrength(password), [password]);
  const config = STRENGTH_CONFIG[level];

  return (
    <div className="space-y-1">
      <div className="h-1 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className={`h-full rounded-full transition-all duration-400 ${config.color}`}
          style={{ width: config.width }}
        />
      </div>
      <div className="flex justify-between text-xs">
        <span className={`font-semibold ${
          level === 'weak' ? 'text-red-400' :
          level === 'fair' ? 'text-yellow-400' :
          level === 'good' ? 'text-blue-400' :
          level === 'strong' ? 'text-green-400' :
          'text-muted-foreground'
        }`}>
          {config.label}
        </span>
        <span className="text-muted-foreground">Use 12+ characters with mixed characters</span>
      </div>
    </div>
  );
}
