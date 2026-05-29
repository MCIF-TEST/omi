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
        'violet':      'var(--violet)',
        'violet-2':    'var(--violet-2)',
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
        xl: '12px',
        '2xl': '16px',
        '3xl': '24px',
        full: '9999px',
      },
      boxShadow: {
        'glow':       '0 0 20px rgba(34,211,238,0.15), 0 0 40px rgba(34,211,238,0.05)',
        'glow-sm':    '0 0 8px rgba(34,211,238,0.25)',
        'glow-lg':    '0 0 40px rgba(34,211,238,0.2), 0 0 80px rgba(34,211,238,0.06)',
        'glow-violet':'0 0 24px rgba(139,92,246,0.2)',
        'glow-danger':'0 0 20px rgba(239,68,68,0.2)',
        'card':       '0 4px 24px rgba(0,0,0,0.35)',
        'card-lg':    '0 8px 48px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.3)',
        'inner-top':  'inset 0 1px 0 rgba(255,255,255,0.04)',
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, #67e8f9 0%, #22d3ee 50%, #38bdf8 100%)',
        'accent-radial':   'radial-gradient(circle at center, rgba(34,211,238,0.12), transparent 70%)',
        'brand-gradient':  'linear-gradient(120deg, #67e8f9 0%, #22d3ee 45%, #8b5cf6 100%)',
      },
      transitionTimingFunction: {
        'omi': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-up-lg': {
          from: { opacity: '0', transform: 'translateY(18px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        pulse_dot: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
        drift: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%':       { transform: 'translate(30px, -20px) scale(1.04)' },
          '66%':       { transform: 'translate(-20px, 15px) scale(0.97)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':       { transform: 'translateY(-8px)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition: '200% center' },
        },
        'shimmer-sweep': {
          '0%':   { transform: 'translateX(-120%)' },
          '60%, 100%': { transform: 'translateX(220%)' },
        },
        'glow-pulse': {
          '0%, 100%': { boxShadow: '0 0 8px rgba(34,211,238,0.1)' },
          '50%':       { boxShadow: '0 0 28px rgba(34,211,238,0.35)' },
        },
        'border-flow': {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%':       { backgroundPosition: '100% 50%' },
        },
        'count-glow': {
          '0%':   { textShadow: '0 0 0 rgba(34,211,238,0)' },
          '50%':  { textShadow: '0 0 16px rgba(34,211,238,0.5)' },
          '100%': { textShadow: '0 0 0 rgba(34,211,238,0)' },
        },
      },
      animation: {
        'fade-up':    'fade-up 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-up-lg': 'fade-up-lg 500ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'pulse-dot':  'pulse_dot 2s ease-in-out infinite',
        'drift':      'drift 22s ease-in-out infinite',
        'drift-slow': 'drift 32s ease-in-out infinite reverse',
        'float':      'float 6s ease-in-out infinite',
        'shimmer':    'shimmer 2.4s ease-in-out infinite',
        'glow-pulse': 'glow-pulse 3s ease-in-out infinite',
        'border-flow':'border-flow 6s ease infinite',
      },
    },
  },
  plugins: [],
};

export default config;
