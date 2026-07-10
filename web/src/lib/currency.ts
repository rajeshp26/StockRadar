const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  CAD: 'C$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  AUD: 'A$',
  CHF: 'Fr',
  CNY: '¥',
  HKD: 'HK$',
  SGD: 'S$',
  INR: '₹',
  MXN: 'Mex$',
  NZD: 'NZ$',
  SEK: 'kr',
  NOK: 'kr',
  DKK: 'kr',
  KRW: '₩',
  BRL: 'R$',
  ZAR: 'R',
};

export function getCurrencySymbol(currency: string | null | undefined): string {
  if (!currency) return '$';
  return CURRENCY_SYMBOLS[currency.toUpperCase()] ?? currency;
}

export function formatCurrency(
  value: number | null | undefined,
  currency: string | null | undefined = 'USD',
  options?: { minimumFractionDigits?: number; maximumFractionDigits?: number },
): string {
  if (value == null) return '\u2014';
  const symbol = getCurrencySymbol(currency);
  const formatted = value.toLocaleString(undefined, {
    minimumFractionDigits: options?.minimumFractionDigits ?? 2,
    maximumFractionDigits: options?.maximumFractionDigits ?? 2,
  });
  return `${symbol}${formatted}`;
}
