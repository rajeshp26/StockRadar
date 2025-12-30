
'use client';

import { LoginForm } from '@/components/auth/login-form';
import { AuthProvider } from '@/components/auth/auth-provider';

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4">
      <AuthProvider>
        <LoginForm />
      </AuthProvider>
    </main>
  );
}
