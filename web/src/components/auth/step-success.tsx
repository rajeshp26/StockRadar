'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CheckCircle, ArrowRight, Shield } from 'lucide-react';
import { useAuth } from '@/providers/auth-provider';

interface StepSuccessProps {
  fallbackEmail?: string;
}

export function StepSuccess({ fallbackEmail }: StepSuccessProps) {
  const router = useRouter();
  const { user } = useAuth();
  const [countdown, setCountdown] = useState(5);

  const email = user?.email ?? fallbackEmail ?? '';

  useEffect(() => {
    if (countdown <= 0) {
      router.push('/dashboard');
      return;
    }

    const timer = setInterval(() => {
      setCountdown((prev) => prev - 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [countdown, router]);

  return (
    <div className="glass-panel w-full p-0 overflow-hidden animate-fade-up">
      <div
        className="h-px w-full"
        style={{
          background:
            'linear-gradient(90deg, transparent, rgba(34,197,94,0.7) 40%, rgba(34,197,94,0.4) 70%, transparent)',
        }}
        aria-hidden="true"
      />
      <div className="px-8 pt-8 pb-10 space-y-6 text-center">
        <div className="flex justify-center">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-green-500/10 border-2 border-green-500/25 animate-[popIn_0.5s_cubic-bezier(0.175,0.885,0.32,1.275)]">
            <CheckCircle className="h-9 w-9 text-green-400" />
          </div>
        </div>

        <div>
          <h1 className="text-2xl font-black text-white tracking-tight">You&apos;re all set!</h1>
          <p className="text-sm text-white/40 mt-2">
            Your account has been created. Welcome to StockerPro.
          </p>
        </div>

        <div className="flex items-center gap-3 p-4 rounded-xl bg-white/5 border border-white/10 text-left">
          <CheckCircle className="h-5 w-5 text-indigo-400 shrink-0" />
          <div>
            <p className="text-sm text-white/70">
              Signed in as <strong className="text-white font-bold">{email || 'Loading...'}</strong>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 p-4 rounded-xl bg-green-500/5 border border-green-500/15 text-left">
          <Shield className="h-5 w-5 text-green-400 shrink-0" />
          <div>
            <p className="text-sm text-white/70">
              Two-factor authentication is <strong className="text-green-400 font-bold">coming soon</strong>
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => router.push('/dashboard')}
          className="w-full py-3 rounded-xl text-xs font-black uppercase tracking-widest inline-flex items-center justify-center gap-2 transition-all duration-150 bg-indigo-600 border border-indigo-500/50 text-white shadow-[0_4px_16px_rgba(99,102,241,0.3)] hover:bg-indigo-500 hover:shadow-[0_6px_24px_rgba(99,102,241,0.45)] active:scale-[0.98]"
        >
          Go to Dashboard
          <ArrowRight className="h-3.5 w-3.5" />
        </button>

        <p className="text-xs text-white/25">
          Redirecting in {countdown}s…
        </p>
      </div>
    </div>
  );
}
