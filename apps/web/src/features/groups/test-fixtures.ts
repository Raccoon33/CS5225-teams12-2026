import type {
  CreatedGroupResponse,
  GroupView,
  SearchView,
} from '@flatsplit/contracts/api';
import type { Membership } from './membership';

export const membership: Membership = {
  version: 1,
  groupId: 'G'.repeat(22),
  groupName: 'Our next chapter',
  memberId: 'M'.repeat(22),
  memberToken: 'T'.repeat(43),
  inviteToken: 'I'.repeat(43),
  expiresAt: '2099-01-01T00:00:00Z',
};
export function groupFixture(): GroupView {
  return {
    groupId: membership.groupId,
    groupName: membership.groupName,
    size: 2,
    revision: 3,
    members: [
      {
        memberId: membership.memberId,
        name: 'Alex',
        isOrganiser: true,
        ready: true,
        destination: null,
        budget: 1600,
        maxCommute: 45,
      },
      {
        memberId: 'J'.repeat(22),
        name: 'Jamie',
        isOrganiser: false,
        ready: true,
        destination: null,
        budget: 1500,
        maxCommute: 40,
      },
    ],
    readyCount: 2,
    allReady: true,
    latestSearch: null,
    createdAt: '2026-10-20T00:00:00Z',
    expiresAt: membership.expiresAt,
  };
}
export function createdFixture(): CreatedGroupResponse {
  return {
    group: { ...groupFixture(), inviteToken: membership.inviteToken! },
    memberId: membership.memberId,
    memberToken: membership.memberToken,
  };
}
export function searchFixture(
  status: SearchView['status'] = 'pending',
): SearchView {
  return {
    searchId: 'S'.repeat(22),
    groupRevision: 3,
    status,
    progress: { total: 52, resolved: 0, unavailable: 0 },
    priority: 'balanced',
    weights: { rent: 0.35, averageCommute: 0.35, commuteGap: 0.3 },
    data: {
      rentPeriod: '2025-10/2026-09',
      rentSource: 'HDB rental approvals (data.gov.sg)',
      flatType: '3-ROOM',
      commuteBasis:
        'Public transport, weekday 08:30 departure; station-to-station',
    },
    ranked: [],
    excluded: [],
  };
}
