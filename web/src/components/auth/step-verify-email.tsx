'use client';

import { useState, useEffect, useCallback } from 'react';
import { Mail, ArrowLeft, RefreshCw } from 'lucide-react';
import Link from 'next/link';
import { createClient } from '@/lib/supabase';
import { cn } from '@/lib/utils';

const supabase = createClient();

interface StepVerifyEmailProps {
  email: string;
  onVerified: () => void;
  onBack: () => void;
}

export function StepVerifyEmail({ email, onVerified, onBack }: StepVerifyEmailProps) {
  const [countdown, setCountdown] = useState(60);
  const [canResend, setCanResend] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (countdown <= 0) {
      setCanResend(true);
      return;
    }

    const timer = setInterval(() => {
      setCountdown((prev) => prev - 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [countdown]);

  const checkSession = useCallback(async () => {
    const { data } = await supabase.auth.getSession();
    if (data.session?.user.email_confirmed_at) {
      onVerified();
    }
  }, [onVerified]);

  useEffect(() => {
    const interval = setInterval(checkSession, 5000);
    return () => clearInterval(interval);
  }, [checkSession]);

  async function handleResend() {
    try {
      setIsResending(true);
      setError(null);

      const { error: resendError } = await supabase.auth.resend({
        type: 'signup',
        email,
      });

      if (resendError) throw resendError;

      setCountdown(60);
      setCanResend(false);
    } catch (err: any) {
      setError(err?.message || 'Failed to resend verification email.');
    } finally {
      setIsResending(false);
    }
  }

  return (
    <div className="glass-panel w-full p-0 overflow-hidden animate-fade-up">
      <div
        className="h-px w-full"
        style={{
          background:
            'linear-gradient(90deg, transparent, rgba(99,102,241,0.7) 40%, rgba(139,92,246,0.4) 70%, transparent)',
        }}
        aria-hidden="true"
      />
      <div className="px-8 pt-8 pb-10 space-y-6">
        <div className="flex flex-col items-center text-center gap-3">
          <div className="flex h-10 items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20">
            <span className="text-[10px] font-bold text-indigo-300">
              Step 2 of 3 <span className="text-white/30 font-normal">/ Verify Email</span>
            </span>
          </div>
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-600/20 border border-indigo-500/30">
            <Mail className="h-7 w-7 text-indigo-300" />
          </div>
          <div>
            <h1 className="text-xl font-black text-white tracking-tight">Check your inbox</h1>
            <p className="text-xs text-white/35 mt-1">
              We sent a confirmation link to{' '}
              <strong className="text-indigo-300 font-semibold">{email}</strong>
            </p>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20" role="alert">
            <p className="text-xs text-rose-300">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-white/5 border border-white/10 text-center">
            <p className="text-sm text-white/60">
              Click the link in the email to verify your account.
            </p>
            <p className="text-xs text-white/30 mt-2">
              Didn&apos;t receive it? Check your spam folder or resend below.
            </p>
          </div>

          <button
            type="button"
            data-testid="resend-btn"
            disabled={!canResend || isResending}
            onClick={handleResend}
            className={cn(
              'w-full py-3 rounded-xl text-xs font-black uppercase tracking-widest',
              'inline-flex items-center justify-center gap-2',
              'transition-all duration-150',
              canResend && !isResending
                ? 'bg-white/5 border border-white/10 text-white hover:bg-white/10 active:scale-[0.98]'
                : 'bg-white/5 border border-white/8 text-white/25 cursor-not-allowed'
            )}
          >
            {isResending ? (
              <>
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/20 border-t-white/60" />
                Sending…
              </>
            ) : (
              <>
                <RefreshCw className="h-3.5 w-3.5" />
                {canResend ? 'Resend Verification Email' : `Resend in ${countdown}s`}
              </>
            )}
          </button>

          <button
            type="button"
            onClick={checkSession}
            className="w-full py-2.5 rounded-xl text-xs font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            I&apos;ve confirmed — continue
          </button>
        </div>

        <button
          type="button"
          onClick={onBack}
          className="flex items-center justify-center gap-1.5 text-xs text-white/30 hover:text-white/50 transition-colors mx-auto"
        >
          <ArrowLeft className="h-3 w-3" />
          Back to sign up
        </button>
      </div>
    </div>
  );
}
