'use client';

import { useAuth } from '@/providers/auth-provider';
import { updateUserProfile } from '@/features/auth/services/auth.service';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';

const SUPPORTED_CURRENCIES = [
  { code: 'USD', label: 'USD — US Dollar', symbol: '$' },
  { code: 'CAD', label: 'CAD — Canadian Dollar', symbol: 'C$' },
  { code: 'EUR', label: 'EUR — Euro', symbol: '€' },
  { code: 'GBP', label: 'GBP — British Pound', symbol: '£' },
  { code: 'JPY', label: 'JPY — Japanese Yen', symbol: '¥' },
  { code: 'AUD', label: 'AUD — Australian Dollar', symbol: 'A$' },
  { code: 'CHF', label: 'CHF — Swiss Franc', symbol: 'Fr' },
  { code: 'CNY', label: 'CNY — Chinese Yuan', symbol: '¥' },
  { code: 'HKD', label: 'HKD — Hong Kong Dollar', symbol: 'HK$' },
  { code: 'SGD', label: 'SGD — Singapore Dollar', symbol: 'S$' },
  { code: 'INR', label: 'INR — Indian Rupee', symbol: '₹' },
  { code: 'MXN', label: 'MXN — Mexican Peso', symbol: 'Mex$' },
];

export default function SettingsPage() {
  const { user, syncWithBackend } = useAuth();
  const { toast } = useToast();

  const handleCurrencyChange = async (value: string) => {
    try {
      await updateUserProfile({ preferred_currency: value });
      await syncWithBackend();
      toast({
        title: 'Display currency updated',
        description: `Your portfolio will now show values in ${value}.`,
      });
    } catch {
      toast({
        title: 'Failed to update currency',
        description: 'Please try again later.',
        variant: 'destructive',
      });
    }
  };

  if (!user) {
    return null;
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Manage your account preferences.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Display Currency</CardTitle>
          <CardDescription>
            All portfolio values will be converted to your preferred currency.
            Exchange rates are updated daily from market data.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label htmlFor="currency-select">Currency</Label>
            <Select
              value={user.preferred_currency}
              onValueChange={handleCurrencyChange}
            >
              <SelectTrigger id="currency-select" className="w-[280px]">
                <SelectValue placeholder="Select currency" />
              </SelectTrigger>
              <SelectContent>
                {SUPPORTED_CURRENCIES.map((c) => (
                  <SelectItem key={c.code} value={c.code}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
