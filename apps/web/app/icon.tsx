import { ImageResponse } from 'next/og';

/**
 * The favicon. There was no icon file at all, so every visit fetched /favicon.ico and got a 404,
 * and the tab showed the browser's default page glyph.
 */
export const runtime = 'edge';
export const size = { width: 32, height: 32 };
export const contentType = 'image/png';

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#010203',
          color: '#5b9dff',
          fontSize: 22,
          fontWeight: 700,
          fontFamily: 'sans-serif',
        }}
      >
        O
      </div>
    ),
    size,
  );
}
