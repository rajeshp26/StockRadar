'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { UserPlus, Mail, Lock, Eye, EyeOff, Chrome, Apple } from 'lucide-react';
import Link from 'next/link';
import { useAuth } from '@/providers/auth-provider';
import { useToast } from '@/hooks/use-toast';
import { PasswordStrength } from '@/components/auth/password-strength';
import { PasswordRequirements } from '@/components/auth/password-requirements';
import { cn } from '@/lib/utils';

const formSchema = z.object({
  firstName: z.string().min(1, 'First name is required'),
  lastName: z.string().min(1, 'Last name is required'),
  email: z.string().email('Please enter a valid email'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  terms: z.literal(true, { errorMap: () => ({ message: 'You must agree to the Terms of Service' }) }),
});

type FormValues = z.infer<typeof formSchema>;

interface StepCreateAccountProps {
  initialData: { firstName: string; lastName: string; email: string; password: string };
  onComplete: (data: { firstName: string; lastName: string; email: string; password: string }) => void;
}

export function StepCreateAccount({ initialData, onComplete }: StepCreateAccountProps) {
  const { toast } = useToast();
  const { signUpWithEmail, signInWithOAuth, status } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmPassword, setConfirmPassword] = useState('');
  const [oauthLoading, setOauthLoading] = useState<'google' | 'apple' | null>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      firstName: initialData.firstName,
      lastName: initialData.lastName,
      email: initialData.email,
      password: initialData.password,
      terms: false as unknown as true,
    },
  });

  const watchPassword = form.watch('password');
  const isSubmitting = form.formState.isSubmitting || status === 'pending_verification';

  async function onSubmit(values: FormValues) {
    try {
      await signUpWithEmail(values.email, values.password, values.firstName, values.lastName);
      onComplete({
        firstName: values.firstName,
        lastName: values.lastName,
        email: values.email,
        password: values.password,
      });
    } catch (error: any) {
      toast({
        title: 'Sign Up Failed',
        description: error?.message || 'An unknown error occurred.',
        variant: 'destructive',
      });
    }
  }

  async function handleOAuth(provider: 'google' | 'apple') {
    try {
      setOauthLoading(provider);
      await signInWithOAuth(provider);
    } catch (error: any) {
      toast({
        title: 'OAuth Sign Up Failed',
        description: error?.message || `Failed to sign in with ${provider}.`,
        variant: 'destructive',
      });
    } finally {
      setOauthLoading(null);
    }
  }

  const isGoogleLoading = oauthLoading === 'google';
  const isAppleLoading = oauthLoading === 'apple';

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
              Step 1 of 3 <span className="text-white/30 font-normal">/ Create Account</span>
            </span>
          </div>
          <div>
            <h1 className="text-xl font-black text-white tracking-tight">Create your account</h1>
            <p className="text-xs text-white/35 mt-1">Start your journey with StockerPro today</p>
          </div>
        </div>

        {/* Social OAuth Buttons */}
        <div className="flex gap-3">
          <button
            type="button"
            data-testid="google-oauth-btn"
            disabled={!!oauthLoading}
            onClick={() => handleOAuth('google')}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold',
              'bg-white/5 border border-white/10 text-white',
              'transition-all duration-150',
              isGoogleLoading
                ? 'opacity-50 cursor-not-allowed'
                : 'hover:bg-white/10 hover:border-white/20 active:scale-[0.98]'
            )}
          >
            {isGoogleLoading ? (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/20 border-t-white/60" />
            ) : (
              <Chrome className="h-4 w-4" />
            )}
            Google
          </button>
          <button
            type="button"
            data-testid="apple-oauth-btn"
            disabled={!!oauthLoading}
            onClick={() => handleOAuth('apple')}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold',
              'bg-white/5 border border-white/10 text-white',
              'transition-all duration-150',
              isAppleLoading
                ? 'opacity-50 cursor-not-allowed'
                : 'hover:bg-white/10 hover:border-white/20 active:scale-[0.98]'
            )}
          >
            {isAppleLoading ? (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/20 border-t-white/60" />
            ) : (
              <Apple className="h-4 w-4" />
            )}
            Apple
          </button>
        </div>

        {/* Divider */}
        <div className="flex items-center gap-3 text-white/20 text-xs">
          <div className="flex-1 h-px bg-white/10" />
          <span>or</span>
          <div className="flex-1 h-px bg-white/10" />
        </div>

        {/* Email/Password Form */}
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" data-testid="email-signup-form">
          {/* Name Row */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label htmlFor="firstName" className="text-[10px] font-black uppercase tracking-[0.18em] text-white/35">
                First name <span className="text-rose-400">*</span>
              </label>
              <div className="relative">
                <UserPlus className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30 pointer-events-none" />
                <input
                  id="firstName"
                  data-testid="first-name-input"
                  type="text"
                  placeholder="Sarah"
                  autoComplete="given-name"
                  className={cn(
                    'w-full pl-10 pr-4 py-3 rounded-xl text-sm font-medium',
                    'bg-white/5 border border-white/10 text-white',
                    'placeholder:text-white/20',
                    'focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15',
                    'transition-all duration-150',
                    form.formState.errors.firstName && 'border-rose-500/50 focus:border-rose-500/60 focus:ring-rose-500/15'
                  )}
                  {...form.register('firstName')}
                />
              </div>
              {form.formState.errors.firstName && (
                <p className="text-[10px] text-rose-400">{form.formState.errors.firstName.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <label htmlFor="lastName" className="text-[10px] font-black uppercase tracking-[0.18em] text-white/35">
                Last name <span className="text-rose-400">*</span>
              </label>
              <div className="relative">
                <UserPlus className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30 pointer-events-none" />
                <input
                  id="lastName"
                  data-testid="last-name-input"
                  type="text"
                  placeholder="Kim"
                  autoComplete="family-name"
                  className={cn(
                    'w-full pl-10 pr-4 py-3 rounded-xl text-sm font-medium',
                    'bg-white/5 border border-white/10 text-white',
                    'placeholder:text-white/20',
                    'focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15',
                    'transition-all duration-150',
                    form.formState.errors.lastName && 'border-rose-500/50 focus:border-rose-500/60 focus:ring-rose-500/15'
                  )}
                  {...form.register('lastName')}
                />
              </div>
              {form.formState.errors.lastName && (
                <p className="text-[10px] text-rose-400">{form.formState.errors.lastName.message}</p>
              )}
            </div>
          </div>

          {/* Email */}
          <div className="space-y-1.5">
            <label htmlFor="email" className="text-[10px] font-black uppercase tracking-[0.18em] text-white/35">
              Work email <span className="text-rose-400">*</span>
            </label>
            <div className="relative">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30 pointer-events-none" />
              <input
                id="email"
                data-testid="email-input"
                type="email"
                placeholder="sarah@company.com"
                autoComplete="email"
                className={cn(
                  'w-full pl-10 pr-4 py-3 rounded-xl text-sm font-medium',
                  'bg-white/5 border border-white/10 text-white',
                  'placeholder:text-white/20',
                  'focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15',
                  'transition-all duration-150',
                  form.formState.errors.email && 'border-rose-500/50 focus:border-rose-500/60 focus:ring-rose-500/15'
                )}
                {...form.register('email')}
              />
            </div>
            {form.formState.errors.email && (
              <p className="text-[10px] text-rose-400">{form.formState.errors.email.message}</p>
            )}
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label htmlFor="password" className="text-[10px] font-black uppercase tracking-[0.18em] text-white/35">
              Password <span className="text-rose-400">*</span>
            </label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30 pointer-events-none" />
              <input
                id="password"
                data-testid="password-input"
                type={showPassword ? 'text' : 'password'}
                placeholder="Create a strong password"
                autoComplete="new-password"
                className={cn(
                  'w-full pl-10 pr-12 py-3 rounded-xl text-sm font-medium',
                  'bg-white/5 border border-white/10 text-white',
                  'placeholder:text-white/20',
                  'focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15',
                  'transition-all duration-150',
                  form.formState.errors.password && 'border-rose-500/50 focus:border-rose-500/60 focus:ring-rose-500/15'
                )}
                {...form.register('password')}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/50 transition-colors p-1"
                tabIndex={-1}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <PasswordStrength password={watchPassword || ''} />
            <PasswordRequirements
              password={watchPassword || ''}
              confirmPassword={confirmPassword}
            />
            {form.formState.errors.password && (
              <p className="text-[10px] text-rose-400">{form.formState.errors.password.message}</p>
            )}
          </div>

          {/* Confirm Password */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-black uppercase tracking-[0.18em] text-white/35">
              Confirm password <span className="text-rose-400">*</span>
            </label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30 pointer-events-none" />
              <input
                id="confirmPassword"
                data-testid="confirm-password-input"
                type={showConfirm ? 'text' : 'password'}
                placeholder="Confirm your password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={cn(
                  'w-full pl-10 pr-12 py-3 rounded-xl text-sm font-medium',
                  'bg-white/5 border border-white/10 text-white',
                  'placeholder:text-white/20',
                  'focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15',
                  'transition-all duration-150',
                  confirmPassword && watchPassword !== confirmPassword && 'border-rose-500/50'
                )}
              />
              <button
                type="button"
                onClick={() => setShowConfirm(!showConfirm)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/50 transition-colors p-1"
                tabIndex={-1}
                aria-label={showConfirm ? 'Hide password' : 'Show password'}
              >
                {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* T&C Checkbox */}
          <div className="flex items-start gap-3">
            <input
              type="checkbox"
              id="terms"
              data-testid="terms-checkbox"
              className="mt-1 accent-indigo-500"
              {...form.register('terms')}
            />
            <label htmlFor="terms" className="text-xs text-white/40 leading-relaxed">
              I agree to the{' '}
              <Link href="/legal/terms" className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors">
                Terms of Service
              </Link>{' '}
              and{' '}
              <Link href="/legal/privacy" className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors">
                Privacy Policy
              </Link>
            </label>
          </div>
          {form.formState.errors.terms && (
            <p className="text-[10px] text-rose-400 -mt-2">{form.formState.errors.terms.message}</p>
          )}

          {/* Submit */}
          <button
            type="submit"
            data-testid="create-account-submit"
            disabled={isSubmitting}
            className={cn(
              'w-full py-3 rounded-xl text-xs font-black uppercase tracking-widest',
              'inline-flex items-center justify-center gap-2',
              'transition-all duration-150',
              isSubmitting
                ? 'bg-white/5 border border-white/8 text-white/25 cursor-not-allowed'
                : 'bg-indigo-600 border border-indigo-500/50 text-white shadow-[0_4px_16px_rgba(99,102,241,0.3)] hover:bg-indigo-500 hover:shadow-[0_6px_24px_rgba(99,102,241,0.45)] active:scale-[0.98]',
            )}
          >
            {isSubmitting ? (
              <>
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/20 border-t-white/60" />
                Creating account…
              </>
            ) : (
              <>
                <UserPlus className="h-3.5 w-3.5" />
                Create Account
              </>
            )}
          </button>
        </form>

        <p className="text-center text-xs text-white/30">
          Already have an account?{' '}
          <Link
            href="/login"
            className="font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
