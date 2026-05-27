import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces
        'bg-deep':     'var(--bg-deep)',
        'bg':          'var(--bg)',
        'bg-elev':     'var(--bg-elev)',
        'bg-elev-2':   'var(--bg-elev-2)',
        // Borders
        'border-1':    'var(--border)',
        'border-2':    'var(--border-2)',
        'border-hot':  'var(--border-hot)',
        // Text
        'fg':          'var(--text)',
        'fg-dim':      'var(--text-dim)',
        'fg-mute':     'var(--text-mute)',
        'fg-faint':    'var(--text-faint)',
        // Accents
        'accent':      'var(--accent)',
        'accent-2':    'var(--accent-2)',
        'accent-dim':  'var(--accent-dim)',
        // Status
        'tier-low':      'var(--tier-low)',
        'tier-moderate': 'var(--tier-moderate)',
        'tier-elevated': 'var(--tier-elevated)',
        'tier-high':     'var(--tier-high)',
        'ok':          'var(--ok)',
        'warn':        'var(--warn)',
        'danger':      'var(--danger)',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        DEFAULT: '4px',
        sm: '2px',
        md: '4px',
        lg: '8px',
      },
      transitionTimingFunction: {
        'omi': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        pulse_dot: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
      },
      animation: {
        'fade-up': 'fade-up 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'pulse-dot': 'pulse_dot 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};

export default config;
