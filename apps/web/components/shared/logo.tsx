import { ShieldCheck } from "lucide-react";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <div className={`group flex items-center gap-2.5 ${className}`}>
      <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-brand-gradient shadow-glow transition-transform duration-300 group-hover:scale-105">
        <ShieldCheck size={18} className="text-primary-foreground" />
        <div className="pointer-events-none absolute inset-0 rounded-lg bg-white/10 opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
      <span className="font-mono text-lg font-bold tracking-tight">
        OMI<span className="text-gradient">SPHERE</span>
      </span>
    </div>
  );
}
