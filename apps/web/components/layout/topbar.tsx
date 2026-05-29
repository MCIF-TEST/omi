"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { LogOut, CreditCard, User as UserIcon, Command, ChevronDown } from "lucide-react";

export function Topbar({
  user,
}: {
  user: { email: string; credits: number; isAdmin: boolean } | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function logout() {
    await fetch("/api/v1/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between border-b border-border bg-background/70 px-6 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <button
          onClick={() => {
            const e = new KeyboardEvent("keydown", { key: "k", metaKey: true });
            window.dispatchEvent(e);
          }}
          className="flex items-center gap-2 rounded-lg border border-border bg-card/40 px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          <Command size={14} />
          <span className="hidden sm:inline">Quick search</span>
          <kbd className="hidden rounded bg-muted px-1.5 font-mono text-2xs sm:inline">⌘K</kbd>
        </button>
      </div>

      <div className="flex items-center gap-3">
        {user ? (
          <>
            {user.isAdmin && (
              <span className="hidden rounded-full border border-secondary/30 bg-secondary/10 px-2.5 py-1 text-2xs font-semibold uppercase tracking-wider text-secondary sm:inline">
                Admin
              </span>
            )}
            <Link
              href="/settings"
              className="flex items-center gap-1.5 rounded-lg border border-border bg-card/40 px-3 py-1.5 text-sm transition-colors hover:border-accent/40 hover:bg-card"
            >
              <CreditCard size={14} className="text-accent" />
              <span className="font-mono font-semibold">{user.credits}</span>
              <span className="hidden text-muted-foreground sm:inline">credits</span>
            </Link>
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setOpen(!open)}
                className="flex items-center gap-1.5 rounded-lg p-1 pr-2 text-sm transition-colors hover:bg-muted"
              >
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-gradient text-xs font-bold text-primary-foreground shadow-glow">
                  {user.email[0]?.toUpperCase()}
                </div>
                <ChevronDown
                  size={14}
                  className={`text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
                />
              </button>
              {open && (
                <div className="absolute right-0 top-full mt-2 w-52 overflow-hidden rounded-xl glass py-1 shadow-card animate-fade-in">
                  <div className="border-b border-border px-3 py-2.5">
                    <div className="truncate text-sm font-medium">{user.email}</div>
                    <div className="text-2xs text-muted-foreground">
                      {user.credits} credits remaining
                    </div>
                  </div>
                  <Link
                    href="/settings"
                    className="flex items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted"
                  >
                    <UserIcon size={14} /> Settings
                  </Link>
                  <button
                    onClick={logout}
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive transition-colors hover:bg-muted"
                  >
                    <LogOut size={14} /> Logout
                  </button>
                </div>
              )}
            </div>
          </>
        ) : (
          <Link href="/login" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
            Login
          </Link>
        )}
      </div>
    </header>
  );
}
