import { useState } from 'react';
import type { GroupView } from '@flatsplit/contracts/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
  errorMessage,
  groupKey,
  searchKey,
  searchOptions,
  startSearch,
} from './api';
import type { Membership } from './membership';

export function SearchProgress({
  group,
  membership,
  groupUpdatedAt,
}: {
  group: GroupView;
  membership: Membership;
  groupUpdatedAt: number;
}) {
  const queryClient = useQueryClient();
  const [submittedSearch, setSubmittedSearch] = useState<{
    searchId: string;
    groupRevision: number;
    groupUpdatedAt: number;
  }>();
  // A successful POST is newer evidence than the group snapshot used to submit
  // it. Give its ID priority only until the next successful group refresh.
  const awaitingGroupRefresh =
    submittedSearch &&
    submittedSearch.groupRevision === group.revision &&
    groupUpdatedAt <= submittedSearch.groupUpdatedAt;
  const searchId =
    (awaitingGroupRefresh
      ? submittedSearch.searchId
      : group.latestSearch?.searchId) ??
    submittedSearch?.searchId ??
    '';
  const status = useQuery({
    ...searchOptions(membership, searchId),
    enabled: !!searchId,
  });
  const submission = useMutation({
    mutationFn: () => startSearch(membership),
    retry: false,
    onSuccess: (search) => {
      queryClient.setQueryData(searchKey(membership, search.searchId), search);
      setSubmittedSearch({
        searchId: search.searchId,
        groupRevision: search.groupRevision,
        groupUpdatedAt,
      });
      void queryClient.invalidateQueries({ queryKey: groupKey(membership) });
    },
  });
  const search = status.data;
  const stale =
    (!awaitingGroupRefresh && group.latestSearch?.status === 'stale') ||
    (search &&
      (search.status === 'stale' || search.groupRevision !== group.revision));
  const pending = !stale && search?.status === 'pending';
  const complete = !stale && search?.status === 'complete' && !status.isError;
  const ownMember = group.members.find(
    (member) => member.memberId === membership.memberId,
  );
  const canSearch = group.allReady && ownMember?.ready;
  return (
    <section className="surface live-search" aria-labelledby="search-heading">
      <div className="section-heading">
        <h2 id="search-heading">Find your middle ground</h2>
        <Badge variant="outline">
          {stale
            ? 'Needs a new search'
            : complete
              ? 'Ready'
              : pending
                ? search.progress.resolved > search.progress.unavailable
                  ? 'Checking routes'
                  : 'Queued'
                : 'Your shortlist'}
        </Badge>
      </div>
      <p className="muted">
        Every flatmate’s budget and commute limit is a hard requirement. Rent
        assumes an equal split of a whole flat, excluding bills.
      </p>
      {!group.allReady && (
        <p role="status">
          Waiting for {group.size - group.readyCount}{' '}
          {group.size - group.readyCount === 1 ? 'flatmate' : 'flatmates'} to
          join and submit preferences.
        </p>
      )}
      {submission.isError && (
        <Alert role="alert" variant="destructive">
          <AlertTitle>Could not start the search</AlertTitle>
          <AlertDescription>{errorMessage(submission.error)}</AlertDescription>
        </Alert>
      )}
      {searchId && status.isPending && (
        <p role="status">Loading your latest search…</p>
      )}
      {status.isError && (
        <Alert role="alert" variant="destructive">
          <AlertTitle>Could not check search progress</AlertTitle>
          <AlertDescription>
            {errorMessage(status.error)} Your group inputs are saved.
            <Button
              variant="outline"
              disabled={status.isFetching}
              onClick={() => {
                void status.refetch();
              }}
            >
              Check progress again
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {stale && (
        <Alert role="status">
          <AlertTitle>Your group has changed</AlertTitle>
          <AlertDescription>
            The previous comparison is out of date. Once everyone is ready,
            start a new search using the latest preferences.
          </AlertDescription>
        </Alert>
      )}
      {pending && !status.isError && (
        <div className="flex flex-col gap-4" role="status" aria-live="polite">
          <h3>
            {search.progress.resolved === search.progress.unavailable
              ? 'Your route checks are queued.'
              : 'Checking your group’s commutes.'}
          </h3>
          <Progress
            value={
              search.progress.total
                ? (search.progress.resolved / search.progress.total) * 100
                : 0
            }
            aria-label="Commute routes checked"
          />
          <p>
            {search.progress.resolved} of {search.progress.total} routes checked
            {search.progress.unavailable
              ? ` · ${search.progress.unavailable} unavailable`
              : ''}
            .
          </p>
          <p className="muted">
            New routes can take a while. You can leave and reopen this group
            later; your inputs and search are saved. We’ll show a comparison
            once all routes have been checked.
          </p>
        </div>
      )}
      {complete && (
        <div className="flex flex-col gap-4" role="status">
          <h3>
            {search.ranked.length
              ? `${search.ranked.length} neighbourhoods meet everyone’s limits.`
              : 'No neighbourhood meets all your current limits.'}
          </h3>
          <p className="muted">
            Rent period: {search.data.rentPeriod}. {search.data.commuteBasis}.
          </p>
          {search.ranked.length > 0 && (
            <ul className="live-town-list">
              {search.ranked.map((area) => (
                <li key={area.town}>
                  <strong>{area.displayName}</strong>
                  <span>
                    {area.rentPerPerson === null
                      ? 'Rent unavailable'
                      : `S$${area.rentPerPerson.toLocaleString('en-SG')} per person/month`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {search.progress.unavailable > 0 && (
            <Alert>
              <AlertTitle>Some routes were unavailable</AlertTitle>
              <AlertDescription>
                {search.progress.unavailable}{' '}
                {search.progress.unavailable === 1
                  ? 'route could'
                  : 'routes could'}{' '}
                not be calculated. Affected towns are excluded; unknown commute
                times are never treated as zero. You can request a retry after
                the service’s retry delay.
              </AlertDescription>
            </Alert>
          )}
          {!search.ranked.length && (
            <p>
              Review the group’s budgets and commute limits together before
              changing any preference. Missing or low-confidence rent and
              unavailable routes also exclude towns.
            </p>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <Button
          disabled={!canSearch || submission.isPending || !!pending}
          onClick={() => submission.mutate()}
        >
          {submission.isPending
            ? 'Submitting search…'
            : stale
              ? 'Search with latest preferences'
              : search
                ? 'Search again / retry unavailable routes'
                : 'Find our neighbourhoods'}
        </Button>
        {pending && (
          <Button
            variant="outline"
            disabled={status.isFetching}
            onClick={() => {
              void status.refetch();
            }}
          >
            {status.isFetching ? 'Checking…' : 'Check progress now'}
          </Button>
        )}
      </div>
    </section>
  );
}
