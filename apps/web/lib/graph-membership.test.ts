import { describe, expect, it } from 'vitest';
import {
  graphsAcceptingPlatform, isAddable, memberPayload, normalisePlatform, platformLabel,
} from './graph-membership';
import { type UserGraphOut } from './api';

const g = (id: number, platform: string, name = `g${id}`): UserGraphOut => ({
  id, name, platform, member_count: 0, created_at: '', updated_at: '',
});

describe('graphsAcceptingPlatform', () => {
  it('offers only graphs on the account’s own platform', () => {
    // The load-bearing test. A member is stored with the GRAPH's platform and the coordination-edge
    // query filters on that, so an X account in a YouTube graph is written down as a YouTube account
    // and can never draw an edge. It would sit there looking like a finding that failed to connect.
    const graphs = [g(1, 'youtube'), g(2, 'x'), g(3, 'youtube')];
    expect(graphsAcceptingPlatform(graphs, 'x').map((x) => x.id)).toEqual([2]);
    expect(graphsAcceptingPlatform(graphs, 'youtube').map((x) => x.id)).toEqual([1, 3]);
  });

  it('treats twitter and x as one platform', () => {
    expect(graphsAcceptingPlatform([g(1, 'twitter')], 'x').map((x) => x.id)).toEqual([1]);
    expect(graphsAcceptingPlatform([g(1, 'x')], 'twitter').map((x) => x.id)).toEqual([1]);
  });

  it('offers nothing when the platform is unknown', () => {
    // Rather than guessing. A wrong graph is worse than no graph: the member is mislabelled on the
    // way in and nothing downstream can tell.
    expect(graphsAcceptingPlatform([g(1, 'x'), g(2, 'youtube')], 'unknown')).toEqual([]);
    expect(graphsAcceptingPlatform([g(1, 'x')], undefined)).toEqual([]);
    expect(graphsAcceptingPlatform([g(1, 'x')], '')).toEqual([]);
  });

  it('keeps the order it was given, so the list does not reshuffle between opens', () => {
    const graphs = [g(3, 'x'), g(1, 'x'), g(2, 'x')];
    expect(graphsAcceptingPlatform(graphs, 'x').map((x) => x.id)).toEqual([3, 1, 2]);
  });
});

describe('normalisePlatform', () => {
  it('is case and whitespace insensitive', () => {
    expect(normalisePlatform('  YouTube ')).toBe('youtube');
    expect(normalisePlatform('X')).toBe('x');
  });
  it('maps every "we do not know" spelling to null', () => {
    expect(normalisePlatform('unknown')).toBeNull();
    expect(normalisePlatform(null)).toBeNull();
    expect(normalisePlatform('   ')).toBeNull();
  });
});

describe('platformLabel', () => {
  it('names the platform the way the product does', () => {
    expect(platformLabel('x')).toBe('X');
    expect(platformLabel('twitter')).toBe('X');
    expect(platformLabel('youtube')).toBe('YouTube');
  });
  it('degrades to a phrase that still reads as a sentence', () => {
    expect(platformLabel('unknown')).toBe('this platform');
  });
});

describe('isAddable', () => {
  it('needs an external_id, which is the identity a membership hangs off', () => {
    expect(isAddable({ external_id: '123', handle: 'a' }, 'x')).toBe(true);
    expect(isAddable({ handle: 'a' }, 'x')).toBe(false);
    expect(isAddable({ external_id: '   ', handle: 'a' }, 'x')).toBe(false);
  });

  it('needs a platform it can honour', () => {
    expect(isAddable({ external_id: '123' }, 'unknown')).toBe(false);
  });
});

describe('memberPayload', () => {
  it('sends the handle we already have rather than letting the id stand in for it', () => {
    // The API defaults `handle` to the external_id when it is empty, which renders a numeric id
    // where a name belongs in the graph.
    expect(memberPayload({ external_id: '1500000000', handle: 'quietfern012', suspicion_tier: 'low' }))
      .toEqual({ external_id: '1500000000', handle: 'quietfern012', tier: 'low' });
  });

  it('falls back to the id only when there is genuinely no handle', () => {
    expect(memberPayload({ external_id: '1500000000' }))
      .toEqual({ external_id: '1500000000', handle: '1500000000', tier: null });
  });

  it('trims, so a stray space cannot create a second membership for one account', () => {
    expect(memberPayload({ external_id: ' 42 ', handle: ' bob ' }))
      .toEqual({ external_id: '42', handle: 'bob', tier: null });
  });
});
