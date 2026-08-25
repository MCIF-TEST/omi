import { ImageResponse } from 'next/og';

/**
 * The link preview card.
 *
 * `twitter.card` was already declared as `summary_large_image` with no image anywhere in the app,
 * which renders as a blank or degraded card. That matters more here than on most products: the
 * thing customers do with this app is post a report link into a comment section, so the preview
 * card is the first impression the product makes on an audience that has never heard of it.
 *
 * Generated rather than committed, so it cannot drift from the name and the positioning, and no
 * binary lands in the repo. Deliberately plain: the design language forbids glow and gradient
 * fills, and a card is read at thumbnail size where anything else turns to mud.
 */
export const runtime = 'edge';
export const alt = 'OMISPHERE. Social authenticity intelligence.';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: '#010203',
          padding: 72,
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ width: 10, height: 10, background: '#3b82f6' }} />
          <div
            style={{
              color: '#7c8796',
              fontSize: 22,
              letterSpacing: 6,
              textTransform: 'uppercase',
            }}
          >
            Social authenticity intelligence
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <div style={{ color: '#f4f6f8', fontSize: 104, fontWeight: 800, letterSpacing: -2 }}>
            OMISPHERE
          </div>
          <div style={{ color: '#9aa5b1', fontSize: 34, lineHeight: 1.3, maxWidth: 900 }}>
            Detect bots, bought engagement and AI-written replies in any comment section.
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 28 }}>
          <div style={{ height: 1, width: 120, background: '#22282f' }} />
          <div style={{ color: '#5b6673', fontSize: 24, letterSpacing: 2 }}>omisphere.online</div>
        </div>
      </div>
    ),
    size,
  );
}
