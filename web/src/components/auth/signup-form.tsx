'use client';

import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { KeyRound, LogIn, TrendingUp } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useAuth } from '@/providers/auth-provider';
import { useToast } from '@/hooks/use-toast';
import { signInWithEmailAndPassword } from 'firebase/auth';
import { initializeFirebase } from '@/firebase';
import { perf } from '@/lib/performance';
import { cn } from '@/lib/utils';

/* ── Validation schema (unchanged) ─────────────────────────── */
const formSchema = z.object({
  email:    z.string().email({ message: 'Please enter a valid email.' }),
  password: z.string().min(8, { message: 'Password must be at least 8 characters.' }),
});

/* ── Glass field wrapper ────────────────────────────────────── */
function GlassInput({
  id,
  type = 'text',
  placeholder,
  field,
}: {
  id:           string;
  type?:        string;
  placeholder?: string;
  field:        React.InputHTMLAttributes<HTMLInputElement>;
}) {
  return (
    <input
      id={id}
      type={type}
      placeholder={placeholder}
      autoComplete={type === 'password' ? 'current-password' : 'email'}
      className={cn(
        'w-full px-4 py-3 rounded-xl text-sm font-medium',
        'bg-white/5 border border-white/10 text-white',
        'placeholder:text-white/20',
        'focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15',
        'transition-all duration-150',
        'disabled:opacity-50 disabled:cursor-not-allowed',
      )}
      {...field}
    />
  );
}

/* ── Main component ─────────────────────────────────────────── */
export function LoginForm() {
  const router       = useRouter();
  const { toast }    = useToast();
  const { status }   = useAuth();
  const { auth }     = initializeFirebase();

  /* ── react-hook-form (logic unchanged) ───────────────────── */
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: { email: '', password: '' },
  });

  const isSubmitting = form.formState.isSubmitting;

  /* ── Handlers (logic unchanged) ──────────────────────────── */
  async function onSubmit(values: z.infer<typeof formSchema>) {
    perf.mark('login-start');
    try {
      await signInWithEmailAndPassword(auth, values.email, values.password);
      toast({ title: 'Login Successful', description: 'You are now being redirected...' });
      router.push('/dashboard');
    } catch (error: any) {
      toast({
        title:       'Login Failed',
        description: error.message || 'An unknown error occurred.',
        variant:     'destructive',
      });
    }
  }

  async function handlePasskeySignIn() {
    toast({ title: 'Coming Soon!', description: 'Passkey support is not yet implemented.' });
  }

  /* ── Render ──────────────────────────────────────────────── */
  return (
    /* Outer glass card */
    <div className="glass-panel w-full max-w-sm p-0 overflow-hidden animate-fade-up">

      {/* Top accent gradient */}
      <div
        className="h-px w-full"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(99,102,241,0.7) 40%, rgba(139,92,246,0.4) 70%, transparent)' }}
        aria-hidden="true"
      />

      <div className="px-8 pt-8 pb-10 space-y-7">

        {/* ── Header ────────────────────────────────────── */}
        <div className="flex flex-col items-center text-center gap-3">
          {/* Logo mark */}
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600/80 border border-indigo-500/40 shadow-[0_4px_20px_rgba(99,102,241,0.35)]">
            <TrendingUp className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-black text-white tracking-tight">Welcome back</h1>
            <p className="text-xs text-white/35 mt-1">Sign in to your StockerPro account</p>
          </div>
        </div>

        {/* ── Form (react-hook-form wrappers preserved) ─ */}
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">

            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem className="space-y-1.5">
                  <FormLabel className="text-[10px] font-black uppercase tracking-[0.18em] text-white/35">
                    Email
                  </FormLabel>
                  <FormControl>
                    <GlassInput
                      id="email"
                      type="email"
                      placeholder="you@example.com"
                      field={field}
                    />
                  </FormControl>
                  <FormMessage className="text-[10px] text-rose-400" />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem className="space-y-1.5">
                  <FormLabel className="text-[10px] font-black uppercase tracking-[0.18em] text-white/35">
                    Password
                  </FormLabel>
                  <FormControl>
                    <GlassInput
                      id="password"
                      type="password"
                      placeholder="••••••••"
                      field={field}
                    />
                  </FormControl>
                  <FormMessage className="text-[10px] text-rose-400" />
                </FormItem>
              )}
            />

            {/* Submit */}
            <button
              type="submit"
              disabled={status === 'initializing' || isSubmitting}
              className={cn(
                'w-full py-3 rounded-xl text-xs font-black uppercase tracking-widest',
                'inline-flex items-center justify-center gap-2',
                'transition-all duration-150',
                status === 'initializing' || isSubmitting
                  ? 'bg-white/5 border border-white/8 text-white/25 cursor-not-allowed'
                  : 'bg-indigo-600 border border-indigo-500/50 text-white shadow-[0_4px_16px_rgba(99,102,241,0.3)] hover:bg-indigo-500 hover:shadow-[0_6px_24px_rgba(99,102,241,0.45)] active:scale-[0.98]',
              )}
            >
              {status === 'initializing' || isSubmitting ? (
                <>
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/20 border-t-white/60" />
                  Authenticating…
                </>
              ) : (
                <>
                  <LogIn className="h-3.5 w-3.5" />
                  Sign In
                </>
              )}
            </button>
          </form>
        </Form>

        {/* ── Divider ───────────────────────────────────── */}
        <div className="flex items-center gap-3">
          <div className="flex-1 glass-divider" />
          <span className="text-[10px] font-black uppercase tracking-widest text-white/20">
            or
          </span>
          <div className="flex-1 glass-divider" />
        </div>

        {/* ── Passkey button ────────────────────────────── */}
        <button
          type="button"
          onClick={handlePasskeySignIn}
          className={cn(
            'w-full py-3 rounded-xl text-[10px] font-black uppercase tracking-widest',
            'inline-flex items-center justify-center gap-2',
            'bg-white/5 border border-white/8 text-white/40',
            'hover:bg-white/10 hover:text-white/70',
            'transition-all duration-150',
          )}
        >
          <KeyRound className="h-3.5 w-3.5" />
          Sign in with Passkey
        </button>

        {/* ── Footer link ───────────────────────────────── */}
        <p className="text-center text-xs text-white/30">
          Don&apos;t have an account?{' '}
          <Link
            href="/signup"
            className="font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            Sign up
          </Link>
        </p>

      </div>
    </div>
  );
}