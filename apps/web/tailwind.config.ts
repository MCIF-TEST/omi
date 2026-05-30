import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-deep':     'var(--bg-deep)',
        'bg':          'var(--bg)',
        'bg-elev':     'var(--bg-elev)',
        'bg-elev-2':   'var(--bg-elev-2)',
        'border-1':    'var(--border)',
        'border-2':    'var(--border-2)',
        'border-hot':  'var(--border-hot)',
        'fg':          'var(--text)',
        'fg-dim':      'var(--text-dim)',
        'fg-mute':     'var(--text-mute)',
        'fg-faint':    'var(--text-faint)',
        'accent':      'var(--accent)',
        'accent-2':    'var(--accent-2)',
        'accent-dim':  'var(--accent-dim)',
        'violet':      'var(--violet)',
        'violet-2':    'var(--violet-2)',
        'coral':       'var(--violet)',
        'coral-2':     'var(--violet-2)',
        'tier-low':      'var(--tier-low)',
        'tier-moderate': 'var(--tier-moderate)',
        'tier-elevated': 'var(--tier-elevated)',
        'tier-high':     'var(--tier-high)',
        'ok':          'var(--ok)',
        'warn':        'var(--warn)',
        'danger':      'var(--danger)',
      },
      fontFamily: {
        sans:    ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Space Grotesk', 'Inter', 'ui-sans-serif', 'sans-serif'],
        mono:    ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        DEFAULT: '4px',
        sm:  '3px',
        md:  '6px',
        lg:  '8px',
        xl:  '12px',
        '2xl': '16px',
        '3xl': '20px',
        full: '9999px',
      },
      boxShadow: {
        'glow':      '0 0 16px rgba(59,142,255,0.1), 0 0 32px rgba(59,142,255,0.04)',
        'glow-sm':   '0 0 8px rgba(59,142,255,0.22)',
        'card':      '0 4px 20px rgba(0,0,0,0.4)',
        'card-lg':   '0 8px 40px rgba(0,0,0,0.55)',
        'inner-top': 'inset 0 1px 0 rgba(255,255,255,0.04)',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(118deg, #6ba9ff 0%, #3b8eff 44%, #8b5cf6 100%)',
      },
      transitionTimingFunction: {
        'omi': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(5px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-up-lg': {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        pulse_dot: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
        'shimmer-sweep': {
          '0%':        { transform: 'translateX(-120%)' },
          '60%, 100%': { transform: 'translateX(240%)' },
        },
      },
      animation: {
        'fade-up':    'fade-up 220ms cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-up-lg': 'fade-up-lg 480ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'pulse-dot':  'pulse_dot 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};

export default config;
