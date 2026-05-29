// Animated network-analysis visualization for the hero.
// Pure SVG + CSS keyframes — no JS after mount. Server-renderable.

export function HeroVisual() {
  return (
    <div
      className="relative w-full aspect-square max-w-[520px] mx-auto select-none pointer-events-none"
      aria-hidden
    >
      {/* Ambient glow layers behind the sphere */}
      <div className="absolute inset-[8%]  rounded-full bg-accent/[0.13] blur-[70px]" />
      <div className="absolute inset-[24%] rounded-full bg-violet/[0.11] blur-[48px]" />

      <svg viewBox="0 0 440 440" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
        <defs>
          <radialGradient id="hv-globe" cx="40%" cy="35%" r="65%">
            <stop offset="0%"   stopColor="#101828" />
            <stop offset="100%" stopColor="#040509" />
          </radialGradient>
          <linearGradient id="hv-ring-grad" x1="20" y1="220" x2="420" y2="220" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#3b8eff" stopOpacity="0.05" />
            <stop offset="40%"  stopColor="#3b8eff" stopOpacity="0.22" />
            <stop offset="60%"  stopColor="#8b5cf6" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.05" />
          </linearGradient>
          <linearGradient id="hv-sweep" x1="220" y1="220" x2="420" y2="220" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#3b8eff" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#3b8eff" stopOpacity="0" />
          </linearGradient>
          <filter id="hv-glow-hub">
            <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="hv-glow-node">
            <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="hv-glow-xs">
            <feGaussianBlur in="SourceGraphic" stdDeviation="1.4" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <clipPath id="hv-clip">
            <circle cx="220" cy="220" r="198"/>
          </clipPath>
        </defs>

        {/* Globe base */}
        <circle cx="220" cy="220" r="200" fill="url(#hv-globe)" />
        <circle cx="220" cy="220" r="200" stroke="url(#hv-ring-grad)" strokeWidth="1.5" />

        {/* Coordinate grid */}
        <g clipPath="url(#hv-clip)" stroke="#3b8eff" strokeWidth="0.4" opacity="0.09">
          {[60,100,140,180,220,260,300,340,380].map(v => (
            <g key={v}>
              <line x1={v} y1="20"  x2={v} y2="420" />
              <line x1="20"  y1={v} x2="420" y2={v} />
            </g>
          ))}
        </g>

        {/* Concentric dotted rings */}
        <circle cx="220" cy="220" r="68"  stroke="#3b8eff" strokeWidth="0.6" strokeOpacity="0.13" strokeDasharray="3 5"  fill="none"/>
        <circle cx="220" cy="220" r="128" stroke="#3b8eff" strokeWidth="0.6" strokeOpacity="0.09" strokeDasharray="4 7"  fill="none"/>
        <circle cx="220" cy="220" r="188" stroke="#3b8eff" strokeWidth="0.6" strokeOpacity="0.06" strokeDasharray="5 9"  fill="none"/>

        {/* Radar sweep — rotates clockwise */}
        <g clipPath="url(#hv-clip)" style={{ transformOrigin: '220px 220px', animation: 'hv-radar 9s linear infinite' }}>
          <path d="M220,220 L420,220 A200,200 0 0,0 220,20 Z" fill="url(#hv-sweep)" />
          <line x1="220" y1="220" x2="420" y2="220" stroke="#3b8eff" strokeWidth="1.5" strokeOpacity="0.55" />
        </g>

        {/* ── Edges ───────────────────────────────────────────── */}
        {/* HIGH-risk cluster */}
        <line x1="138" y1="88"  x2="68"  y2="155" stroke="#fb3b6b" strokeWidth="0.8" strokeOpacity="0.40" strokeDasharray="4 5"/>
        <line x1="138" y1="88"  x2="310" y2="100" stroke="#fb8c3c" strokeWidth="0.8" strokeOpacity="0.35" strokeDasharray="3 4"/>
        <line x1="310" y1="100" x2="340" y2="172" stroke="#fb3b6b" strokeWidth="0.9" strokeOpacity="0.45"/>
        <line x1="68"  y1="155" x2="95"  y2="305" stroke="#fb8c3c" strokeWidth="0.7" strokeOpacity="0.30" strokeDasharray="3 5"/>
        {/* h3 cluster */}
        <line x1="288" y1="358" x2="382" y2="290" stroke="#fb3b6b" strokeWidth="0.9" strokeOpacity="0.40"/>
        <line x1="288" y1="358" x2="175" y2="368" stroke="#fb8c3c" strokeWidth="0.7" strokeOpacity="0.30" strokeDasharray="4 6"/>
        <line x1="382" y1="290" x2="400" y2="215" stroke="#f5b62f" strokeWidth="0.7" strokeOpacity="0.28" strokeDasharray="3 5"/>
        {/* Hub spokes */}
        <line x1="220" y1="220" x2="195" y2="148" stroke="#3b8eff" strokeWidth="1.0" strokeOpacity="0.48"/>
        <line x1="220" y1="220" x2="282" y2="210" stroke="#3b8eff" strokeWidth="1.0" strokeOpacity="0.48"/>
        <line x1="220" y1="220" x2="158" y2="258" stroke="#3b8eff" strokeWidth="0.8" strokeOpacity="0.38"/>
        <line x1="220" y1="220" x2="108" y2="198" stroke="#3b8eff" strokeWidth="0.7" strokeOpacity="0.28" strokeDasharray="3 4"/>
        <line x1="220" y1="220" x2="248" y2="52"  stroke="#3b8eff" strokeWidth="0.7" strokeOpacity="0.22" strokeDasharray="3 5"/>
        {/* Secondary cross-edges */}
        <line x1="195" y1="148" x2="138" y2="88"  stroke="#6ba9ff" strokeWidth="0.6" strokeOpacity="0.28" strokeDasharray="3 5"/>
        <line x1="282" y1="210" x2="340" y2="172" stroke="#6ba9ff" strokeWidth="0.6" strokeOpacity="0.28" strokeDasharray="3 5"/>
        <line x1="158" y1="258" x2="95"  y2="305" stroke="#6ba9ff" strokeWidth="0.5" strokeOpacity="0.22" strokeDasharray="3 6"/>
        <line x1="324" y1="298" x2="288" y2="358" stroke="#6ba9ff" strokeWidth="0.6" strokeOpacity="0.28" strokeDasharray="3 5"/>

        {/* ── Ripple rings for HIGH nodes ── */}
        <circle cx="138" cy="88"  r="12" stroke="#fb3b6b" strokeWidth="1" fill="none"
          style={{ transformOrigin:'138px 88px',  animation:'hv-ripple 2.1s ease-out infinite' }}/>
        <circle cx="340" cy="172" r="11" stroke="#fb3b6b" strokeWidth="1" fill="none"
          style={{ transformOrigin:'340px 172px', animation:'hv-ripple 1.8s ease-out infinite', animationDelay:'0.5s' }}/>
        <circle cx="288" cy="358" r="12" stroke="#fb3b6b" strokeWidth="1" fill="none"
          style={{ transformOrigin:'288px 358px', animation:'hv-ripple 2.3s ease-out infinite', animationDelay:'1.1s' }}/>

        {/* ── HIGH risk nodes (red) ── */}
        <g filter="url(#hv-glow-node)">
          <circle cx="138" cy="88"  r="7" fill="#fb3b6b" style={{ animation:'hv-node-pulse 2.1s ease-in-out infinite' }}/>
          <circle cx="340" cy="172" r="6" fill="#fb3b6b" style={{ animation:'hv-node-pulse 1.8s ease-in-out infinite', animationDelay:'0.5s' }}/>
          <circle cx="288" cy="358" r="7" fill="#fb3b6b" style={{ animation:'hv-node-pulse 2.3s ease-in-out infinite', animationDelay:'1.1s' }}/>
        </g>

        {/* ── ELEVATED nodes (orange) ── */}
        <g filter="url(#hv-glow-xs)">
          <circle cx="68"  cy="155" r="5" fill="#fb8c3c" style={{ animation:'hv-node-pulse 2.4s ease-in-out infinite', animationDelay:'0.3s' }}/>
          <circle cx="382" cy="290" r="5" fill="#fb8c3c" style={{ animation:'hv-node-pulse 2.0s ease-in-out infinite', animationDelay:'0.9s' }}/>
          <circle cx="310" cy="100" r="5" fill="#fb8c3c" style={{ animation:'hv-node-pulse 2.6s ease-in-out infinite', animationDelay:'1.5s' }}/>
          <circle cx="175" cy="368" r="4" fill="#fb8c3c" style={{ animation:'hv-node-pulse 1.9s ease-in-out infinite', animationDelay:'0.7s' }}/>
        </g>

        {/* ── MODERATE nodes (yellow) ── */}
        <g opacity="0.80">
          <circle cx="95"  cy="305" r="4"   fill="#f5b62f"/>
          <circle cx="248" cy="52"  r="4"   fill="#f5b62f"/>
          <circle cx="400" cy="215" r="4"   fill="#f5b62f"/>
          <circle cx="324" cy="298" r="3.5" fill="#f5b62f"/>
        </g>

        {/* ── LOW / clean nodes (teal) ── */}
        <g opacity="0.60">
          <circle cx="195" cy="148" r="3" fill="#22d3a8"/>
          <circle cx="282" cy="210" r="3" fill="#22d3a8"/>
          <circle cx="158" cy="258" r="3" fill="#22d3a8"/>
          <circle cx="108" cy="198" r="3" fill="#22d3a8"/>
          <circle cx="258" cy="372" r="3" fill="#22d3a8"/>
        </g>

        {/* ── Hub (center) ── */}
        <circle cx="220" cy="220" r="14" fill="#080f1e"/>
        <circle cx="220" cy="220" r="10" fill="#3b8eff" filter="url(#hv-glow-hub)"
          style={{ animation:'hv-node-pulse 3s ease-in-out infinite' }}/>
        <circle cx="220" cy="220" r="17" stroke="#3b8eff" strokeWidth="1.5" strokeOpacity="0.30" fill="none"
          style={{ transformOrigin:'220px 220px', animation:'hv-ripple 3s ease-out infinite' }}/>

        {/* Outer decorative arc */}
        <circle cx="220" cy="220" r="202" stroke="url(#hv-ring-grad)" strokeWidth="1"/>
      </svg>

      {/* Floating metric chips */}
      <div
        className="absolute top-[15%] left-[16%] flex items-center gap-1.5 font-mono text-[0.6rem] tracking-[0.16em] uppercase text-tier-high bg-tier-high/10 border border-tier-high/35 px-2.5 py-1 rounded-full shadow-glow-danger"
        style={{ animation: 'hv-chip-in 0.45s cubic-bezier(0.16,1,0.3,1) both', animationDelay: '0.7s' }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-tier-high animate-pulse-dot" />
        High risk · 3
      </div>
      <div
        className="absolute top-[36%] right-[4%] flex items-center gap-1.5 font-mono text-[0.6rem] tracking-[0.16em] uppercase text-tier-elevated bg-tier-elevated/10 border border-tier-elevated/35 px-2.5 py-1 rounded-full"
        style={{ animation: 'hv-chip-in 0.45s cubic-bezier(0.16,1,0.3,1) both', animationDelay: '1.0s' }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-tier-elevated" />
        Elevated · 4
      </div>
      <div
        className="absolute bottom-[20%] left-[5%] flex items-center gap-1.5 font-mono text-[0.6rem] tracking-[0.16em] uppercase text-accent-2 bg-accent/10 border border-accent/35 px-2.5 py-1 rounded-full shadow-glow-sm"
        style={{ animation: 'hv-chip-in 0.45s cubic-bezier(0.16,1,0.3,1) both', animationDelay: '1.3s' }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-dot" />
        Coordinated network
      </div>
    </div>
  );
}
