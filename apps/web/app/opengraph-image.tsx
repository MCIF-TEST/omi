import { ImageResponse } from 'next/og';
import { SITE_TAGLINE } from '@/lib/seo';

export const alt = 'OMISPHERE — Social Authenticity Intelligence';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

/**
 * Default OG/Twitter-card image for every page that doesn't declare its own. Generated at request
 * time via Satori rather than a static PNG in `public/` so the wordmark can never drift from the
 * brand colors defined in `logo.tsx` / `globals.css` — there is exactly one place those live.
 */
export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#09111f',
          backgroundImage:
            'radial-gradient(circle at 22% 20%, rgba(91,157,255,0.16), transparent 55%), ' +
            'radial-gradient(circle at 82% 78%, rgba(112,82,240,0.14), transparent 55%)',
        }}
      >
        <svg width="120" height="120" viewBox="0 0 40 40" fill="none">
          <path
            d="M31.5 10 A15 15 0 1 0 34 22.5"
            stroke="#5b9dff"
            strokeWidth="2.5"
            strokeLinecap="round"
            fill="none"
          />
          <circle cx="13" cy="16" r="1.5" fill="#5b9dff" />
          <circle cx="22" cy="12.5" r="1.5" fill="#7052f0" />
          <circle cx="27" cy="20" r="1.5" fill="#5b9dff" />
          <circle cx="20" cy="27.5" r="1.5" fill="#5b9dff" />
          <circle cx="20" cy="20" r="2.6" fill="#3b82f6" />
        </svg>

        <div
          style={{
            display: 'flex',
            marginTop: 36,
            fontSize: 88,
            fontWeight: 700,
            letterSpacing: '-0.02em',
          }}
        >
          <span style={{ color: '#5b9dff' }}>OMI</span>
          <span style={{ color: '#e7ebf3' }}>SPHERE</span>
        </div>

        <div
          style={{
            display: 'flex',
            marginTop: 18,
            fontSize: 34,
            color: '#8892a6',
            letterSpacing: '0.01em',
          }}
        >
          {SITE_TAGLINE}
        </div>

        <div
          style={{
            display: 'flex',
            marginTop: 28,
            fontSize: 24,
            color: '#5b9dff',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          Bot detection · coordinated behavior · X and YouTube
        </div>
      </div>
    ),
    { ...size },
  );
}
