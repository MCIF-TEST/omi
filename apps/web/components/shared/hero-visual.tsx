// OmiSphere hero, a wireframe globe under an authenticity scan.
//
// The story it tells: a real post's engagement is a mix of genuine people (calm green nodes,
// scattered, each wired straight to the post) and BOUGHT accounts that move together. Tight pods of
// red/orange nodes linked to each other by dashed "coordination" edges, all converging on the same
// post. A blue OMI sweep rotates over the globe, flagging the bought pods as it passes. Pure SVG + CSS
// keyframes (hv-*), all GPU transform/opacity, and the keyframes are disabled under reduced-motion
// (see globals.css), so nothing moves for users who ask it not to.
export function HeroVisual() {
  return (
    <div
      className="relative w-full aspect-square max-w-[520px] mx-auto select-none pointer-events-none"
      aria-hidden
    >
      {/* Ambient depth behind the sphere. Blue identity + a whisper of the purple AI layer. */}
      <div className="absolute inset-[6%]  rounded-full bg-accent/[0.14] blur-[76px]" />
      <div className="absolute inset-[26%] rounded-full bg-violet/[0.12] blur-[52px]" />

      <svg viewBox="0 0 440 440" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
        <defs>
          <radialGradient id="hv-globe" cx="38%" cy="32%" r="72%">
            <stop offset="0%"   stopColor="#18263d" />
            <stop offset="62%"  stopColor="#0e1728" />
            <stop offset="100%" stopColor="#070d18" />
          </radialGradient>
          <linearGradient id="hv-rim" x1="20" y1="220" x2="420" y2="220" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#3b82f6" stopOpacity="0.06" />
            <stop offset="42%"  stopColor="#5b9dff" stopOpacity="0.30" />
            <stop offset="60%"  stopColor="#8f7bf0" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#8f7bf0" stopOpacity="0.05" />
          </linearGradient>
          <linearGradient id="hv-sweep" x1="220" y1="220" x2="420" y2="220" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#5b9dff" stopOpacity="0.26" />
            <stop offset="100%" stopColor="#5b9dff" stopOpacity="0" />
          </linearGradient>
          <filter id="hv-glow-hub">
            <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="hv-glow-node">
            <feGaussianBlur in="SourceGraphic" stdDeviation="2.4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <clipPath id="hv-clip"><circle cx="220" cy="220" r="198" /></clipPath>
        </defs>

        {/* Globe body + rim */}
        <circle cx="220" cy="220" r="200" fill="url(#hv-globe)" />
        <circle cx="220" cy="220" r="200" stroke="url(#hv-rim)" strokeWidth="1.5" />

        {/* Wireframe sphere. Meridians + parallels in faint blue */}
        <g clipPath="url(#hv-clip)" stroke="#5b9dff" fill="none">
          <g strokeOpacity="0.10" strokeWidth="0.7">
            {[55, 110, 165].map((r) => <ellipse key={`m${r}`} cx="220" cy="220" rx={r} ry="200" />)}
            {[55, 110, 165].map((r) => <ellipse key={`p${r}`} cx="220" cy="220" rx="200" ry={r} />)}
          </g>
          <circle cx="220" cy="220" r="128" strokeOpacity="0.10" strokeWidth="0.6" strokeDasharray="3 6" />
          <circle cx="220" cy="220" r="188" strokeOpacity="0.07" strokeWidth="0.6" strokeDasharray="4 8" />
        </g>

        {/* OMI scan sweep. Rotates over the globe */}
        <g clipPath="url(#hv-clip)" style={{ transformOrigin: '220px 220px', animation: 'hv-radar 9s linear infinite' }}>
          <path d="M220,220 L420,220 A200,200 0 0,0 220,20 Z" fill="url(#hv-sweep)" />
          <line x1="220" y1="220" x2="420" y2="220" stroke="#5b9dff" strokeWidth="1.4" strokeOpacity="0.5" />
        </g>

        {/* ── Coordination edges (dashed amber/red). Bought pods acting together ── */}
        <g strokeLinecap="round">
          {/* pod A (top-left) */}
          <line x1="120" y1="95"  x2="95"  y2="146" stroke="#ef4444" strokeWidth="0.9" strokeOpacity="0.45" strokeDasharray="3 4" />
          <line x1="120" y1="95"  x2="158" y2="122" stroke="#f97316" strokeWidth="0.8" strokeOpacity="0.38" strokeDasharray="3 5" />
          <line x1="95"  y1="146" x2="158" y2="122" stroke="#ef4444" strokeWidth="0.8" strokeOpacity="0.36" strokeDasharray="3 4" />
          {/* pod B (right) */}
          <line x1="332" y1="150" x2="356" y2="206" stroke="#ef4444" strokeWidth="0.9" strokeOpacity="0.45" strokeDasharray="3 4" />
          <line x1="332" y1="150" x2="318" y2="108" stroke="#f97316" strokeWidth="0.8" strokeOpacity="0.36" strokeDasharray="3 5" />
          {/* pod C (bottom) */}
          <line x1="255" y1="350" x2="304" y2="324" stroke="#f97316" strokeWidth="0.8" strokeOpacity="0.40" strokeDasharray="3 4" />
          <line x1="255" y1="350" x2="205" y2="360" stroke="#f59e0b" strokeWidth="0.7" strokeOpacity="0.30" strokeDasharray="3 6" />
        </g>

        {/* ── Spokes to the post (hub) ── bought pods (warm) + genuine accounts (blue) ── */}
        <g strokeLinecap="round">
          <line x1="220" y1="220" x2="158" y2="122" stroke="#f97316" strokeWidth="0.9" strokeOpacity="0.34" strokeDasharray="3 4" />
          <line x1="220" y1="220" x2="332" y2="150" stroke="#ef4444" strokeWidth="0.9" strokeOpacity="0.34" strokeDasharray="3 4" />
          <line x1="220" y1="220" x2="255" y2="350" stroke="#f97316" strokeWidth="0.8" strokeOpacity="0.30" strokeDasharray="3 5" />
          {/* genuine. Solid, quiet blue */}
          <line x1="220" y1="220" x2="185" y2="150" stroke="#3b82f6" strokeWidth="0.8" strokeOpacity="0.40" />
          <line x1="220" y1="220" x2="286" y2="212" stroke="#3b82f6" strokeWidth="0.8" strokeOpacity="0.40" />
          <line x1="220" y1="220" x2="160" y2="266" stroke="#3b82f6" strokeWidth="0.7" strokeOpacity="0.32" />
          <line x1="220" y1="220" x2="300" y2="284" stroke="#3b82f6" strokeWidth="0.7" strokeOpacity="0.28" />
        </g>

        {/* ── Ripple rings on the strongest bought accounts ── */}
        <circle cx="120" cy="95"  r="12" stroke="#ef4444" strokeWidth="1" fill="none"
          style={{ transformOrigin: '120px 95px',  animation: 'hv-ripple 2.1s ease-out infinite' }} />
        <circle cx="332" cy="150" r="12" stroke="#ef4444" strokeWidth="1" fill="none"
          style={{ transformOrigin: '332px 150px', animation: 'hv-ripple 1.9s ease-out infinite', animationDelay: '0.6s' }} />
        <circle cx="255" cy="350" r="11" stroke="#f97316" strokeWidth="1" fill="none"
          style={{ transformOrigin: '255px 350px', animation: 'hv-ripple 2.3s ease-out infinite', animationDelay: '1.1s' }} />

        {/* ── BOUGHT / HIGH nodes (red) ── */}
        <g filter="url(#hv-glow-node)">
          <circle cx="120" cy="95"  r="7" fill="#ef4444" style={{ animation: 'hv-node-pulse 2.1s ease-in-out infinite' }} />
          <circle cx="332" cy="150" r="6.5" fill="#ef4444" style={{ animation: 'hv-node-pulse 1.9s ease-in-out infinite', animationDelay: '0.6s' }} />
          <circle cx="95"  cy="146" r="5" fill="#ef4444" style={{ animation: 'hv-node-pulse 2.5s ease-in-out infinite', animationDelay: '0.3s' }} />
        </g>

        {/* ── ELEVATED nodes (orange) ── */}
        <g filter="url(#hv-glow-node)" opacity="0.92">
          <circle cx="158" cy="122" r="5" fill="#f97316" style={{ animation: 'hv-node-pulse 2.4s ease-in-out infinite', animationDelay: '0.9s' }} />
          <circle cx="356" cy="206" r="5" fill="#f97316" style={{ animation: 'hv-node-pulse 2.0s ease-in-out infinite', animationDelay: '1.4s' }} />
          <circle cx="255" cy="350" r="5.5" fill="#f97316" style={{ animation: 'hv-node-pulse 2.3s ease-in-out infinite', animationDelay: '0.5s' }} />
          <circle cx="304" cy="324" r="4.5" fill="#f97316" style={{ animation: 'hv-node-pulse 2.6s ease-in-out infinite', animationDelay: '1.7s' }} />
        </g>

        {/* ── SUSPECT nodes (amber) ── */}
        <g opacity="0.82">
          <circle cx="318" cy="108" r="4"   fill="#f59e0b" />
          <circle cx="205" cy="360" r="4"   fill="#f59e0b" />
          <circle cx="380" cy="238" r="3.5" fill="#f59e0b" />
        </g>

        {/* ── GENUINE / LOW nodes (green) ── scattered, unclustered ── */}
        <g opacity="0.72">
          <circle cx="185" cy="150" r="3.4" fill="#22c55e" />
          <circle cx="286" cy="212" r="3.4" fill="#22c55e" />
          <circle cx="160" cy="266" r="3.2" fill="#22c55e" />
          <circle cx="300" cy="284" r="3.2" fill="#22c55e" />
          <circle cx="228" cy="330" r="3"   fill="#22c55e" />
          <circle cx="132" cy="200" r="3"   fill="#22c55e" />
        </g>

        {/* ── The post being scanned (hub) ── */}
        <circle cx="220" cy="220" r="15" fill="#09111f" />
        <circle cx="220" cy="220" r="10" fill="#3b82f6" filter="url(#hv-glow-hub)"
          style={{ animation: 'hv-node-pulse 3s ease-in-out infinite' }} />
        <circle cx="220" cy="220" r="18" stroke="#5b9dff" strokeWidth="1.4" strokeOpacity="0.32" fill="none"
          style={{ transformOrigin: '220px 220px', animation: 'hv-ripple 3s ease-out infinite' }} />

        <circle cx="220" cy="220" r="202" stroke="url(#hv-rim)" strokeWidth="1" />
      </svg>

      {/* Floating verdict chips, the read the scan produced */}
      <div
        className="absolute top-[13%] left-[13%] flex items-center gap-1.5 font-mono text-[0.6rem] tracking-[0.16em] uppercase text-tier-high bg-tier-high/10 border border-tier-high/35 px-2.5 py-1 rounded-full"
        style={{ animation: 'hv-chip-in 0.45s cubic-bezier(0.16,1,0.3,1) both', animationDelay: '0.7s' }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-tier-high animate-pulse-dot" />
        Bought · 7
      </div>
      <div
        className="absolute top-[45%] right-[2%] flex items-center gap-1.5 font-mono text-[0.6rem] tracking-[0.16em] uppercase text-tier-elevated bg-tier-elevated/10 border border-tier-elevated/35 px-2.5 py-1 rounded-full"
        style={{ animation: 'hv-chip-in 0.45s cubic-bezier(0.16,1,0.3,1) both', animationDelay: '1.0s' }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-tier-elevated" />
        Coordinated
      </div>
      <div
        className="absolute bottom-[12%] left-[8%] flex items-center gap-1.5 font-mono text-[0.6rem] tracking-[0.16em] uppercase text-tier-low bg-tier-low/10 border border-tier-low/35 px-2.5 py-1 rounded-full"
        style={{ animation: 'hv-chip-in 0.45s cubic-bezier(0.16,1,0.3,1) both', animationDelay: '1.3s' }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-tier-low" />
        Genuine · 6
      </div>
    </div>
  );
}
