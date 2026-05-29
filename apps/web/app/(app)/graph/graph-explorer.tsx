'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input, Label } from '@/components/ui/input';

interface Props {
  initialFocal: string;
  platform: string;
}

export function GraphExplorer({ initialFocal, platform }: Props) {
  const router = useRouter();
  const [focal, setFocal] = useState(initialFocal);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const v = focal.trim();
    if (!v) return;
    router.push(`/graph?focal=${encodeURIComponent(v)}&platform=${platform}`);
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-3">
      <div className="flex-1 relative">
        <Label htmlFor="focal" className="sr-only">Channel ID</Label>
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none" />
        <Input
          id="focal"
          value={focal}
          onChange={(e) => setFocal(e.target.value)}
          placeholder="UC… (YouTube channel ID)"
          className="pl-9"
        />
      </div>
      <Button type="submit">
        <Search size={14} />
        Explore
      </Button>
    </form>
  );
}
