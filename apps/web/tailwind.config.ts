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
        'coral':       'var(--violet)',
        'coral-2':     'var(--violet-2)',
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
        sans:    ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Space Grotesk', 'Inter', 'ui-sans-serif', 'sans-serif'],
        mono:    ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        DEFAULT: '9px',
        sm: '6px',
        md: '10px',
        lg: '14px',
        xl: '18px',
        '2xl': '24px',
        '3xl': '30px',
        full: '9999px',
      },
      boxShadow: {
        'glow':       '0 0 22px rgba(139,123,255,0.18), 0 0 44px rgba(139,123,255,0.06)',
        'glow-sm':    '0 0 10px rgba(139,123,255,0.3)',
        'glow-lg':    '0 0 44px rgba(139,123,255,0.24), 0 0 88px rgba(139,123,255,0.08)',
        'glow-coral': '0 0 26px rgba(255,122,92,0.24)',
        'glow-danger':'0 0 22px rgba(251,59,107,0.24)',
        'card':       '0 6px 28px rgba(0,0,0,0.4)',
        'card-lg':    '0 12px 56px rgba(0,0,0,0.55), 0 2px 10px rgba(0,0,0,0.4)',
        'inner-top':  'inset 0 1px 0 rgba(255,255,255,0.05)',
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, #ab9dff 0%, #8b7bff 50%, #ff7a5c 120%)',
        'accent-radial':   'radial-gradient(circle at center, rgba(139,123,255,0.14), transparent 70%)',
        'brand-gradient':  'linear-gradient(118deg, #ab9dff 0%, #8b7bff 42%, #ff7a5c 100%)',
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
          '33%':       { transform: 'translate(34px, -22px) scale(1.05)' },
          '66%':       { transform: 'translate(-22px, 16px) scale(0.96)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':       { transform: 'translateY(-9px)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition: '200% center' },
        },
        'shimmer-sweep': {
          '0%':   { transform: 'translateX(-120%)' },
          '60%, 100%': { transform: 'translateX(240%)' },
        },
        'glow-pulse': {
          '0%, 100%': { boxShadow: '0 0 8px rgba(139,123,255,0.12)' },
          '50%':       { boxShadow: '0 0 30px rgba(139,123,255,0.4)' },
        },
        'border-flow': {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%':       { backgroundPosition: '100% 50%' },
        },
      },
      animation: {
        'fade-up':    'fade-up 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-up-lg': 'fade-up-lg 520ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'pulse-dot':  'pulse_dot 2s ease-in-out infinite',
        'drift':      'drift 24s ease-in-out infinite',
        'drift-slow': 'drift 34s ease-in-out infinite reverse',
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
