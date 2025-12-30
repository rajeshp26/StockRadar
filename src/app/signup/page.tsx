import { SignupForm } from '@/components/auth/signup-form';
import { AuthProvider } from '@/components/auth/auth-provider';

export default function SignupPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4">
      <AuthProvider>
        <SignupForm />
      </AuthProvider>
    </main>
  );
}
