'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Gift } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input, Label } from '@/components/ui/input';
import { apiClient, ApiError } from '@/lib/api';

export function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [referralCode, setReferralCode] = useState('');
  const [showReferralInput, setShowReferralInput] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Pre-fill referral code from a ?ref= query param so shared links work
  // without the user typing anything. Persist across navigations too.
  useEffect(() => {
    const fromUrl = searchParams.get('ref');
    if (fromUrl) {
      setReferralCode(fromUrl.trim());
      setShowReferralInput(true);
      return;
    }
    const fromStorage = sessionStorage.getItem('omi_ref');
    if (fromStorage) {
      setReferralCode(fromStorage);
      setShowReferralInput(true);
    }
  }, [searchParams]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    setPending(true);
    try {
      await apiClient('/v1/auth/signup', {
        method: 'POST',
        body: JSON.stringify({
          email,
          password,
          referral_code: referralCode.trim() || undefined,
        }),
      });
      sessionStorage.removeItem('omi_ref');
      router.refresh();
      router.push('/dashboard');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Signup failed. Try again.');
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4" autoComplete="on">
      <div>
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div>
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          placeholder="At least 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>

      {showReferralInput ? (
        <div>
          <Label htmlFor="referral">
            <span className="inline-flex items-center gap-1.5">
              <Gift size={11} className="text-accent" />
              Referral code
            </span>
          </Label>
          <Input
            id="referral"
            type="text"
            autoComplete="off"
            maxLength={16}
            placeholder="Optional — get your friend an extra credit"
            value={referralCode}
            onChange={(e) => setReferralCode(e.target.value)}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowReferralInput(true)}
          className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-accent transition-colors"
        >
          <Gift size={11} /> Have a referral code?
        </button>
      )}

      {error && (
        <p className="text-xs text-danger bg-danger/10 border border-danger/40 rounded-sm px-3 py-2 font-mono">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" className="w-full" disabled={pending}>
        {pending ? 'Creating account…' : 'Create account'}
      </Button>
    </form>
  );
}
