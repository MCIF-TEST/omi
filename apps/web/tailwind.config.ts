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
        'bg-elev-3':   'var(--bg-elev-3)',
        'bg-inset':    'var(--bg-inset)',
        'bg-sidebar':  'var(--bg-sidebar)',
        'border-1':    'var(--border)',
        'border-2':    'var(--border-2)',
        'border-hot':  'var(--border-hot)',
        'divider':     'var(--divider)',
        'fg':          'var(--text)',
        'fg-dim':      'var(--text-dim)',
        'fg-mute':     'var(--text-mute)',
        'fg-faint':    'var(--text-faint)',
        'accent':      'var(--accent)',
        'accent-2':    'var(--accent-2)',
        'accent-text': 'var(--accent-text)',
        'accent-dim':  'var(--accent-dim)',
        'accent-soft': 'var(--accent-soft)',
        'violet':      'var(--violet)',
        'violet-2':    'var(--violet-2)',
        'violet-dim':  'var(--violet-dim)',
        'violet-solid':   'var(--violet-solid)',
        'violet-solid-2': 'var(--violet-solid-2)',
        'violet-soft':    'var(--violet-soft)',
        'unknown':     'var(--unknown)',
        'coral':       'var(--violet)',
        'coral-2':     'var(--violet-2)',
        'tier-low':      'var(--tier-low)',
        'tier-moderate': 'var(--tier-moderate)',
        'tier-elevated': 'var(--tier-elevated)',
        'tier-high':     'var(--tier-high)',
        'ok':          'var(--ok)',
        'warn':        'var(--warn)',
        'danger':      'var(--danger)',
        'confidence-strong': 'var(--confidence-strong)',
        'confidence-medium': 'var(--confidence-medium)',
        'confidence-weak':   'var(--confidence-weak)',
        'cluster-1':   'var(--cluster-1)',
        'cluster-2':   'var(--cluster-2)',
        'cluster-3':   'var(--cluster-3)',
        'cluster-4':   'var(--cluster-4)',
        'cluster-5':   'var(--cluster-5)',
        'cluster-6':   'var(--cluster-6)',
        'cluster-7':   'var(--cluster-7)',
        'cluster-8':   'var(--cluster-8)',
        'ev-string':   'var(--ev-string)',
        'ev-key':      'var(--ev-key)',
        'ev-number':   'var(--ev-number)',
        'ev-keyword':  'var(--ev-keyword)',
        'ev-error':    'var(--ev-error)',
        'ev-meta':     'var(--ev-meta)',
      },
      fontFamily: {
        // CSS variables injected by next/font on <html> (self-hosted, no CDN CSS).
        sans:    ['var(--font-inter)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['var(--font-inter)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono:    ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        // Pre-login display voice only. Falls back to Inter so stray usage degrades rather than
        // breaking; see the note in app/layout.tsx for why the app itself does not use it.
        hero:    ['var(--font-archivo)', 'var(--font-inter)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        'display-alt': ['var(--font-display-alt)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
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
        // No glow, ever. Elevation is tone + hairline; these are quiet depth cues only.
        'glow':      'none',
        'glow-sm':   'none',
        'card':      '0 1px 2px rgba(0,0,0,0.4)',
        'card-lg':   '0 8px 30px -12px rgba(0,0,0,0.6)',
        'inner-top': 'inset 0 1px 0 rgba(255,255,255,0.03)',
        'glow-danger': 'none',
        'glow-violet': 'none',
        'glow-brand':  'inset 0 0 0 1px var(--border-2)',
        'overlay':   '0 16px 50px -12px rgba(0,0,0,0.7), 0 0 0 1px var(--border-2)',
        'hairline':  'inset 0 0 0 1px var(--border)',
        'pop':       '0 8px 30px -12px rgba(0,0,0,0.6), 0 0 0 1px var(--border-2)',
      },
      backgroundImage: {
        // The suspicion spectrum (authentic→highly-suspicious) as a DATA legend
        // for probability meters, never a brand mark, never blue+purple.
        'brand-gradient': 'linear-gradient(90deg, #22c55e 0%, #f59e0b 40%, #f97316 68%, #ef4444 100%)',
      },
      transitionTimingFunction: {
        'omi': 'cubic-bezier(0.16, 1, 0.3, 1)',
        'mech': 'cubic-bezier(0.4, 0, 0.2, 1)',
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
