'use client';

import { useMemo } from 'react';
import { Check, X } from 'lucide-react';

interface PasswordRequirementsProps {
  password: string;
  confirmPassword: string;
}

interface Requirement {
  key: string;
  label: string;
  met: boolean;
}

export function PasswordRequirements({ password, confirmPassword }: PasswordRequirementsProps) {
  const requirements = useMemo<Requirement[]>(() => [
    { key: 'length', label: '12+ characters', met: password.length >= 12 },
    { key: 'upper', label: 'Uppercase letter', met: /[A-Z]/.test(password) },
    { key: 'lower', label: 'Lowercase letter', met: /[a-z]/.test(password) },
    { key: 'number', label: 'Number', met: /[0-9]/.test(password) },
    { key: 'special', label: 'Special character', met: /[^A-Za-z0-9]/.test(password) },
    { key: 'match', label: 'Passwords match', met: password.length > 0 && password === confirmPassword },
  ], [password, confirmPassword]);

  if (!password && !confirmPassword) return null;

  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1">
      {requirements.map((req) => (
        <div
          key={req.key}
          className={`flex items-center gap-2 text-xs transition-colors duration-200 ${
            req.met ? 'text-green-400' : 'text-muted-foreground'
          }`}
        >
          {req.met ? (
            <Check className="h-3 w-3 shrink-0" />
          ) : (
            <div className="h-3 w-3 shrink-0 rounded-full border border-muted-foreground/40" />
          )}
          {req.label}
        </div>
      ))}
    </div>
  );
}
