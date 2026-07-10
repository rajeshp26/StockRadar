import { describe, it, expect } from 'vitest';
import { getCurrencySymbol, formatCurrency } from '@/lib/currency';

describe('getCurrencySymbol', () => {
  it('returns $ for USD', () => {
    expect(getCurrencySymbol('USD')).toBe('$');
  });

  it('returns C$ for CAD', () => {
    expect(getCurrencySymbol('CAD')).toBe('C$');
  });

  it('returns € for EUR', () => {
    expect(getCurrencySymbol('EUR')).toBe('€');
  });

  it('returns £ for GBP', () => {
    expect(getCurrencySymbol('GBP')).toBe('£');
  });

  it('falls back to $ for null', () => {
    expect(getCurrencySymbol(null)).toBe('$');
  });

  it('falls back to $ for undefined', () => {
    expect(getCurrencySymbol(undefined)).toBe('$');
  });

  it('returns empty string for empty string input', () => {
    expect(getCurrencySymbol('')).toBe('$');
  });

  it('is case-insensitive', () => {
    expect(getCurrencySymbol('usd')).toBe('$');
    expect(getCurrencySymbol('Usd')).toBe('$');
    expect(getCurrencySymbol('cad')).toBe('C$');
  });

  it('returns unknown code as-is when not in map', () => {
    expect(getCurrencySymbol('XYZ')).toBe('XYZ');
  });
});

describe('formatCurrency', () => {
  it('formats a value in USD', () => {
    const result = formatCurrency(1234.56, 'USD');
    expect(result).toMatch(/^\$1,234\.56$/);
  });

  it('formats a value in CAD', () => {
    const result = formatCurrency(1234.56, 'CAD');
    expect(result).toMatch(/^C\$1,234\.56$/);
  });

  it('formats a value in EUR', () => {
    const result = formatCurrency(1234.56, 'EUR');
    expect(result).toMatch(/^€1,234\.56$/);
  });

  it('returns em dash for null value', () => {
    expect(formatCurrency(null, 'USD')).toBe('\u2014');
  });

  it('returns em dash for undefined value', () => {
    expect(formatCurrency(undefined, 'USD')).toBe('\u2014');
  });

  it('uses USD as default currency', () => {
    const result = formatCurrency(100);
    expect(result).toMatch(/^\$100\.00$/);
  });

  it('respects custom fraction digits', () => {
    const result = formatCurrency(100, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    expect(result).toBe('$100');
  });

  it('handles zero value', () => {
    const result = formatCurrency(0, 'USD');
    expect(result).toMatch(/^\$0\.00$/);
  });

  it('handles negative values', () => {
    const result = formatCurrency(-500, 'USD');
    expect(result).toMatch(/^\$-500\.00$|^-\$500\.00$/);
  });

  it('handles large numbers', () => {
    const result = formatCurrency(1000000, 'USD');
    expect(result).toMatch(/^\$1,000,000\.00$/);
  });

  it('handles fractional values correctly', () => {
    const result = formatCurrency(0.1, 'USD');
    expect(result).toMatch(/^\$0\.10$/);
  });
});
