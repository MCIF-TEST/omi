import { describe, it, expect } from 'vitest';
import { resolveScanPlatform, accountScanEndpoint } from './scan-platform';

describe('resolveScanPlatform. Deep-scan routing (X/YouTube fall-through defect)', () => {
  it('Case A: investigation X + commenter platform missing → routes to X', () => {
    expect(resolveScanPlatform('x', undefined)).toBe('x');
    expect(resolveScanPlatform('x', null)).toBe('x');
    expect(resolveScanPlatform('x', '')).toBe('x');
    expect(resolveScanPlatform('twitter', undefined)).toBe('x');
    expect(accountScanEndpoint(resolveScanPlatform('x', undefined))).toBe('/v1/scan/twitter/account');
  });

  it('Case B: investigation YouTube + commenter platform missing → routes to YouTube', () => {
    expect(resolveScanPlatform('youtube', undefined)).toBe('youtube');
    expect(accountScanEndpoint(resolveScanPlatform('youtube', undefined))).toBe('/v1/scan/youtube/account');
  });

  it('Case C: platform unknown everywhere → unknown (no endpoint → caller refuses to scan)', () => {
    expect(resolveScanPlatform(undefined, undefined)).toBe('unknown');
    expect(resolveScanPlatform('unknown', 'unknown')).toBe('unknown');
    expect(resolveScanPlatform('', '')).toBe('unknown');
    expect(accountScanEndpoint(resolveScanPlatform(undefined, undefined))).toBeNull();
  });

  it('investigation platform is authoritative. Commenter platform never silently overrides it', () => {
    expect(resolveScanPlatform('youtube', 'x')).toBe('youtube');
    expect(resolveScanPlatform('x', 'youtube')).toBe('x');
  });

  it('falls back to a KNOWN commenter platform only when the investigation platform is unavailable', () => {
    expect(resolveScanPlatform(undefined, 'x')).toBe('x');
    expect(resolveScanPlatform('unknown', 'youtube')).toBe('youtube');
  });

  it('never assumes YouTube for an unrecognized value', () => {
    expect(resolveScanPlatform('reddit', undefined)).toBe('unknown');
    expect(accountScanEndpoint('unknown')).toBeNull();
  });
});
