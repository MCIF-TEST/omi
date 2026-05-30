import { describe, it, expect } from 'vitest';
import { _parse, ApiError } from './api';

// _parse is the heart of the typed client: it turns a fetch Response into
// either parsed data or a typed ApiError. These cases lock in the behavior
// that a 2xx-but-unparseable body (a truncated/timed-out gateway response)
// surfaces as an error instead of silently handing the UI an unrenderable
// string.

function res(body: string | null, init: ResponseInit): Response {
  return new Response(body, init);
}

describe('_parse', () => {
  it('returns parsed JSON on a 2xx response', async () => {
    const out = await _parse<{ a: number; b: string }>(
      res(JSON.stringify({ a: 1, b: 'x' }), { status: 200 }),
    );
    expect(out).toEqual({ a: 1, b: 'x' });
  });

  it('returns undefined for an empty 2xx body', async () => {
    const out = await _parse<undefined>(res('', { status: 200 }));
    expect(out).toBeUndefined();
  });

  it('throws ApiError with the server detail on a 4xx JSON error', async () => {
    await expect(
      _parse(res(JSON.stringify({ detail: 'Out of credits' }), { status: 402 })),
    ).rejects.toMatchObject({ status: 402, message: 'Out of credits' });
  });

  it('throws ApiError on a non-JSON error body and keeps the raw body', async () => {
    let err: unknown;
    try {
      await _parse(res('Not Found', { status: 404 }));
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).body).toBe('Not Found');
  });

  it('throws an incomplete-response error on a 2xx body that is not JSON', async () => {
    // A long scan that exceeds an upstream timeout can return 200 with the
    // connection cut mid-body — the JSON never closes.
    let err: unknown;
    try {
      await _parse(res('{"partial": tru', { status: 200 }));
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(200);
    expect((err as ApiError).message).toMatch(/incomplete response/i);
  });
});

describe('ApiError', () => {
  it('carries status, message, and the original body', () => {
    const e = new ApiError(500, 'boom', { detail: 'boom' });
    expect(e).toBeInstanceOf(Error);
    expect(e.status).toBe(500);
    expect(e.message).toBe('boom');
    expect(e.body).toEqual({ detail: 'boom' });
  });
});
