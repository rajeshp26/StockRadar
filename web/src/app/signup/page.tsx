'use client';
import { Suspense } from 'react';
import { SignupFlow } from '@/components/auth/signup-flow';

function SignupContent() {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center p-4">
      <div
        className="pointer-events-none absolute inset-0 flex items-center justify-center"
        aria-hidden="true"
      >
        <div className="h-[600px] w-[600px] rounded-full bg-indigo-600/10 blur-[120px]" />
      </div>
      <SignupFlow />
    </main>
  );
}

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupContent />
    </Suspense>
  );
}