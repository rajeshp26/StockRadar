'use client';
import { SignupForm } from '@/components/auth/signup-form';

export default function SignupPage() {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center p-4">
      {/* Soft radial glow behind the card */}
      <div
        className="pointer-events-none absolute inset-0 flex items-center justify-center"
        aria-hidden="true"
      >
        <div className="h-[600px] w-[600px] rounded-full bg-indigo-600/10 blur-[120px]" />
      </div>
      <SignupForm />
    </main>
  );
}