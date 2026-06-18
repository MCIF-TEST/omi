import { describe, it, expect } from 'vitest';
import { isAnonymizedMember, hasAnonymizedMembers } from './campaign-identity';

describe('isAnonymizedMember', () => {
  it('flags disclosure hashes (handle == hashed external_id)', () => {
    const h = '135AEY00MOP1tH7YCuKyQx2xM0hG1vsl7l+0QPTliyM=';
    expect(isAnonymizedMember(h, h)).toBe(true);          // featured GRU/Xinjiang shape
    expect(isAnonymizedMember(null, h)).toBe(true);       // null handle + hash id
    expect(isAnonymizedMember('6nDcSemH7EpMzxlBrA8G5QRpuoEj4Bl2drKLTQnWE=', '6nDcSemH7EpMzxlBrA8G5QRpuoEj4Bl2drKLTQnWE=')).toBe(true);
  });

  it('NEVER hides a real handle, even when handle == external_id', () => {
    expect(isAnonymizedMember('elonmusk', 'elonmusk')).toBe(false);   // X uses handle as id
    expect(isAnonymizedMember('BBCNews', 'BBCNews')).toBe(false);
  });

  it('does not flag a distinct human handle', () => {
    expect(isAnonymizedMember('@creator', 'UCabcdefghijklmnopqrstuv')).toBe(false);
    expect(isAnonymizedMember('Real Name', '1234567890')).toBe(false);
  });

  it('does not flag YouTube channel ids or numeric ids (merely unnamed, not hashed)', () => {
    expect(isAnonymizedMember(null, 'UCabcdefghijklmnopqrstuv')).toBe(false); // 24 chars, no base64 chars
    expect(isAnonymizedMember('UCabcdefghijklmnopqrstuv', 'UCabcdefghijklmnopqrstuv')).toBe(false);
    expect(isAnonymizedMember(null, '1234567890123456789')).toBe(false);      // numeric X id
  });

  it('flags implausibly long opaque identifiers', () => {
    expect(isAnonymizedMember(null, 'a'.repeat(40))).toBe(true);
  });
});

describe('hasAnonymizedMembers', () => {
  it('detects any anonymized member in a list', () => {
    expect(hasAnonymizedMembers([
      { handle: '@real', account_external_id: 'UCxyz' },
      { handle: 'abc+def/ghi=', account_external_id: 'abc+def/ghi=' },
    ])).toBe(true);
    expect(hasAnonymizedMembers([
      { handle: '@real', account_external_id: 'UCxyz' },
      { handle: 'elonmusk', account_external_id: 'elonmusk' },
    ])).toBe(false);
  });
});
