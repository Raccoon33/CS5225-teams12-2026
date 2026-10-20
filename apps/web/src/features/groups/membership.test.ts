// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createdFixture, groupFixture, membership } from './test-fixtures';

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState(null, '', '/');
});
describe('browser membership and invitation capabilities', () => {
  it('persists creator membership across a module reload without storing group preferences', async () => {
    const storage = await import('./membership');
    expect(storage.saveMembership(createdFixture()).persisted).toBe(true);
    vi.resetModules();
    const reloaded = await import('./membership');
    expect(reloaded.readMembership(membership.groupId)).toEqual(membership);
    expect(
      localStorage.getItem(`flatsplit:membership:${membership.groupId}`),
    ).not.toContain('budget');
    expect(reloaded.savedMemberships()).toEqual([membership]);
  });
  it('never grants a joining member an organiser invite capability', async () => {
    const storage = await import('./membership');
    const response = createdFixture();
    const group = groupFixture();
    const joined = storage.saveMembership({ ...response, group }).membership;
    expect(storage.inviteLink(joined, 'https://flatsplit.test')).toBeNull();
    expect(joined).not.toHaveProperty('inviteToken');
  });
  it('places only the invite token in the URL fragment and consumes it safely across StrictMode/reloads', async () => {
    const storage = await import('./membership');
    const link = storage.inviteLink(membership, window.location.origin)!;
    expect(link).not.toContain(membership.memberToken);
    window.history.replaceState(null, '', link);
    expect(storage.captureInvite(membership.groupId)).toBe(
      membership.inviteToken,
    );
    expect(window.location.hash).toBe('');
    expect(window.location.search).toBe('');
    expect(storage.captureInvite(membership.groupId)).toBe(
      membership.inviteToken,
    );
    vi.resetModules();
    expect(
      (await import('./membership')).captureInvite(membership.groupId),
    ).toBe(membership.inviteToken);
    storage.clearInvite(membership.groupId);
    expect(storage.captureInvite(membership.groupId)).toBeNull();
  });
  it('uses the fresh invite when storage still contains an older token and the write is blocked', async () => {
    const storage = await import('./membership');
    sessionStorage.setItem(
      `flatsplit:invite:${membership.groupId}`,
      'X'.repeat(43),
    );
    window.history.replaceState(
      null,
      '',
      `/join/${membership.groupId}#${membership.inviteToken}`,
    );
    const blocked = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new DOMException('Quota exceeded');
      });
    try {
      expect(storage.captureInvite(membership.groupId)).toBe(
        membership.inviteToken,
      );
      expect(storage.captureInvite(membership.groupId)).toBe(
        membership.inviteToken,
      );
      expect(window.location.hash).toBe('');
    } finally {
      blocked.mockRestore();
    }
  });
  it('rejects an invalid new fragment rather than falling back to an older invitation', async () => {
    const storage = await import('./membership');
    window.history.replaceState(
      null,
      '',
      `/join/${membership.groupId}#${membership.inviteToken}`,
    );
    storage.captureInvite(membership.groupId);
    window.history.replaceState(
      null,
      '',
      `/join/${membership.groupId}#invalid`,
    );
    expect(storage.captureInvite(membership.groupId)).toBeNull();
    expect(window.location.hash).toBe('');
  });
  it('rejects malformed, expired and cross-group persisted memberships', async () => {
    const storage = await import('./membership');
    const key = `flatsplit:membership:${membership.groupId}`;
    for (const value of [
      'broken',
      JSON.stringify({ ...membership, expiresAt: '2000-01-01T00:00:00Z' }),
      JSON.stringify({ ...membership, memberToken: 'short' }),
      JSON.stringify({ ...membership, groupId: 'X'.repeat(22) }),
    ]) {
      localStorage.setItem(key, value);
      expect(storage.readMembership(membership.groupId)).toBeNull();
    }
  });
  it('preserves access in memory and reports a blocked persistence write', async () => {
    const storage = await import('./membership');
    const blocked = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new DOMException('Blocked');
      });
    const result = storage.saveMembership(createdFixture());
    expect(result.persisted).toBe(false);
    expect(storage.readMembership(membership.groupId)).toEqual(membership);
    expect(storage.membershipIsPersisted(membership)).toBe(false);
    blocked.mockRestore();
  });
});
