import type { Config } from 'tailwindcss';

export default {
  darkMode: ['class'],
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/features/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans:    ['Inter', 'sans-serif'],
        body:    ['Inter', 'sans-serif'],
        headline:['Inter', 'sans-serif'],
        code:    ['monospace'],
      },
      fontWeight: {
        black: '900',
      },
      colors: {
        // ── shadcn/ui semantic tokens (unchanged) ──────────────────────────
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT:    'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT:    'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT:    'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT:    'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT:    'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT:    'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT:    'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        border: 'hsl(var(--border))',
        input:  'hsl(var(--input))',
        ring:   'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))',
        },
        sidebar: {
          DEFAULT:              'hsl(var(--sidebar-background))',
          foreground:           'hsl(var(--sidebar-foreground))',
          primary:              'hsl(var(--sidebar-primary))',
          'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
          accent:               'hsl(var(--sidebar-accent))',
          'accent-foreground':  'hsl(var(--sidebar-accent-foreground))',
          border:               'hsl(var(--sidebar-border))',
          ring:                 'hsl(var(--sidebar-ring))',
        },

        // ── Glass UI palette ───────────────────────────────────────────────
        glass: {
          // Surfaces
          'surface-0':  'rgba(255,255,255,0.02)', // deepest / page bg tint
          'surface-1':  'rgba(255,255,255,0.05)', // panel
          'surface-2':  'rgba(255,255,255,0.08)', // card inside panel
          'surface-3':  'rgba(255,255,255,0.12)', // hover / active
          // Borders
          'border':     'rgba(255,255,255,0.07)',
          'border-hi':  'rgba(255,255,255,0.14)',
          // Text
          'text-1':     'rgba(255,255,255,1.00)',
          'text-2':     'rgba(255,255,255,0.60)',
          'text-3':     'rgba(255,255,255,0.35)',
          'text-4':     'rgba(255,255,255,0.18)',
        },

        // ── Semantic accent palette ────────────────────────────────────────
        indigo: {
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
        emerald: {
          400: '#34d399',
          500: '#10b981',
        },
        rose: {
          400: '#fb7185',
          500: '#f43f5e',
        },
        amber: {
          400: '#fbbf24',
          500: '#f59e0b',
        },
        violet: {
          400: '#a78bfa',
          500: '#8b5cf6',
        },

        // ── Apple-UI semantic layer (super-investors dashboard) ────────────
        au: {
          'bg-deep':     'var(--au-bg-deep)',
          'bg':          'var(--au-bg)',
          'bg-elevated': 'var(--au-bg-elevated)',
          'glass-bg':    'var(--au-glass-bg)',
          'glass-bg-strong': 'var(--au-glass-bg-strong)',
          'glass-border':    'var(--au-glass-border)',
          'text':           'var(--au-text)',
          'text-secondary': 'var(--au-text-secondary)',
          'text-tertiary':  'var(--au-text-tertiary)',
          'text-faint':     'var(--au-text-faint)',
          'accent-400':  'var(--au-accent-400)',
          'accent-500':  'var(--au-accent-500)',
          'accent-600':  'var(--au-accent-600)',
          'accent-soft': 'var(--au-accent-soft)',
          'border':      'var(--au-border)',
          'border-strong': 'var(--au-border-strong)',
        },
        financial: {
          'up':            'var(--financial-up)',
          'down':          'var(--financial-down)',
          'up-muted':      'var(--positive-text-muted)',
          'down-muted':    'var(--negative-text-muted)',
          'up-bg':         'var(--positive-bg)',
          'up-bg-strong':  'var(--positive-bg-strong)',
          'up-border':     'var(--positive-border)',
          'down-bg':       'var(--negative-bg)',
          'down-bg-strong':'var(--negative-bg-strong)',
          'down-border':   'var(--negative-border)',
          'neutral':       'var(--neutral-text)',
          'neutral-bg':    'var(--neutral-bg)',
          'warn':          'var(--au-warning)',
          'warn-bg':       'var(--au-warning-bg)',
          'warn-border':   'var(--au-warning-border)',
        },
      },

      // ── Border radius scale ──────────────────────────────────────────────
      borderRadius: {
        sm:    'calc(var(--radius) - 4px)',  // 0.75rem
        md:    'calc(var(--radius) - 2px)',  // 0.875rem
        lg:    'var(--radius)',              // 1rem
        xl:    'calc(var(--radius) + 4px)',  // 1.25rem
        '2xl': 'calc(var(--radius) + 8px)', // 1.5rem
        '3xl': 'calc(var(--radius) + 16px)',// 2rem
        '4xl': 'calc(var(--radius) + 24px)',// 2.5rem
      },

      // ── Backdrop blur ────────────────────────────────────────────────────
      backdropBlur: {
        xs:  '4px',
        sm:  '8px',
        md:  '14px',
        lg:  '20px',
        xl:  '30px',
        '2xl': '50px',
      },

      // ── Box shadows ──────────────────────────────────────────────────────
      boxShadow: {
        'glass-sm': '0 4px 16px rgba(0,0,0,0.3)',
        'glass':    '0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)',
        'glass-lg': '0 20px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08)',
        'glass-xl': '0 32px 80px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.10)',
        'glow-indigo': '0 0 0 1px rgba(99,102,241,0.15), 0 0 30px rgba(99,102,241,0.15)',
        'glow-emerald': '0 0 0 1px rgba(52,211,153,0.15), 0 0 24px rgba(52,211,153,0.12)',
        'glow-rose':    '0 0 0 1px rgba(251,113,133,0.15), 0 0 24px rgba(251,113,133,0.12)',
      },

      // ── Keyframes & animations ───────────────────────────────────────────
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to:   { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to:   { height: '0' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-down': {
          from: { opacity: '0', transform: 'translateY(-8px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.95)' },
          to:   { opacity: '1', transform: 'scale(1)' },
        },
        'shimmer': {
          from: { backgroundPosition: '-200% center' },
          to:   { backgroundPosition: '200% center' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.5' },
        },
        'spin-slow': {
          from: { transform: 'rotate(0deg)' },
          to:   { transform: 'rotate(360deg)' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up':   'accordion-up 0.2s ease-out',
        'fade-in':        'fade-in 0.4s ease-out',
        'fade-up':        'fade-up 0.5s ease-out',
        'fade-down':      'fade-down 0.3s ease-out',
        'scale-in':       'scale-in 0.3s ease-out',
        'shimmer':        'shimmer 2.5s linear infinite',
        'pulse-glow':     'pulse-glow 2s ease-in-out infinite',
        'spin-slow':      'spin-slow 8s linear infinite',
      },

      // ── Spacing extras ───────────────────────────────────────────────────
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config;