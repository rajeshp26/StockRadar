'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/providers/auth-provider';
import { StepCreateAccount } from '@/components/auth/step-create-account';
import { StepVerifyEmail } from '@/components/auth/step-verify-email';
import { StepSuccess } from '@/components/auth/step-success';

type SignupStep = 1 | 2 | 3;

interface FormData {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
}

export function SignupFlow() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status, session } = useAuth();

  const stepFromUrl = parseInt(searchParams.get('step') || '1', 10) as SignupStep;
  const verifiedParam = searchParams.get('verified') === 'true';

  const [currentStep, setCurrentStep] = useState<SignupStep>(
    verifiedParam && status === 'pending_verification' ? 2 :
    stepFromUrl >= 1 && stepFromUrl <= 3 ? stepFromUrl : 1
  );

  const emailFromUrl = searchParams.get('email') || '';

  const [formData, setFormData] = useState<FormData>(() => {
    if (emailFromUrl) {
      return { firstName: '', lastName: '', email: emailFromUrl, password: '' };
    }
    if (typeof window !== 'undefined') {
      const saved = sessionStorage.getItem('signupFormData');
      if (saved) {
        try { return JSON.parse(saved); } catch { /* ignore */ }
      }
    }
    return { firstName: '', lastName: '', email: '', password: '' };
  });

  useEffect(() => {
    if (emailFromUrl) {
      setFormData((prev) => ({ ...prev, email: emailFromUrl }));
    }
  }, [emailFromUrl]);

  const goToStep = useCallback((step: SignupStep) => {
    setCurrentStep(step);
    router.replace(`/signup?step=${step}`, { scroll: false });
  }, [router]);

  useEffect(() => {
    if (verifiedParam && currentStep === 1) {
      goToStep(2);
    }
  }, [verifiedParam, currentStep, goToStep]);

  useEffect(() => {
    if (session && status === 'authenticated' && currentStep !== 3) {
      const isOAuth = session.user.app_metadata?.provider !== 'email';
      if (isOAuth || session.user.email_confirmed_at) {
        goToStep(3);
      }
    }
  }, [session, status, currentStep, goToStep]);

  const handleStepComplete = (data: FormData) => {
    setFormData(data);
    try {
      sessionStorage.setItem('signupFormData', JSON.stringify(data));
    } catch { /* ignore */ }
    goToStep(2);
  };

  const handleVerificationComplete = () => {
    goToStep(3);
  };

  const handleBackToStep1 = () => {
    goToStep(1);
  };

  const stepTitles = ['Create Account', 'Verify Email', "You're All Set!"];
  const stepDescriptions = [
    'Enter your name, email, and a strong password',
    'Check your inbox for the confirmation link',
    'Welcome to StockerPro!',
  ];

  return (
    <div className="flex w-full max-w-4xl gap-10">
      {/* Left Panel — Step Indicator (hidden on mobile) */}
      <div className="hidden md:flex md:w-64 shrink-0 flex-col pt-12">
        <div className="space-y-0">
          {stepTitles.map((title, i) => {
            const stepNum = (i + 1) as SignupStep;
            const isActive = currentStep === stepNum;
            const isCompleted = currentStep > stepNum;

            return (
              <div key={stepNum} className="flex items-start gap-4 pb-8 relative">
                {i < stepTitles.length - 1 && (
                  <div
                    className={`absolute left-[19px] top-10 w-0.5 h-[calc(100%-2.5rem)] transition-colors duration-500 ${
                      isCompleted ? 'bg-indigo-500' : 'bg-white/10'
                    }`}
                  />
                )}
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 text-sm font-bold border-2 transition-all duration-400 z-10 ${
                    isActive
                      ? 'border-indigo-500 bg-indigo-500 text-white shadow-[0_0_0_4px_rgba(99,102,241,0.2)]'
                      : isCompleted
                      ? 'border-green-500 bg-green-500 text-white'
                      : 'border-white/10 bg-transparent text-white/40'
                  }`}
                >
                  {isCompleted ? (
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    stepNum
                  )}
                </div>
                <div className="pt-1.5">
                  <p className={`text-sm font-bold transition-colors duration-300 ${
                    isActive ? 'text-white' : isCompleted ? 'text-green-400' : 'text-white/40'
                  }`}>
                    {title}
                  </p>
                  <p className="text-xs text-white/30 mt-0.5">{stepDescriptions[i]}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right Panel — Active Step */}
      <div className="flex-1 min-w-0">
        {currentStep === 1 && (
          <StepCreateAccount
            initialData={formData}
            onComplete={handleStepComplete}
          />
        )}
        {currentStep === 2 && (
          <StepVerifyEmail
            email={formData.email}
            onVerified={handleVerificationComplete}
            onBack={handleBackToStep1}
          />
        )}
        {currentStep === 3 && (
          <StepSuccess fallbackEmail={formData.email} />
        )}
      </div>
    </div>
  );
}
