import { useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from '@tanstack/react-router';
import { skipToken, useMutation, useQuery } from '@tanstack/react-query';
import { zJoinGroupBody } from '@flatsplit/contracts/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
  FieldError,
} from '@/components/ui/field';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { GroupShell } from './GroupShell';
import { ApiError, groupKey, readGroup, joinGroup, errorMessage } from './api';
import {
  captureInvite,
  clearInvite,
  readMembership,
  saveMembership,
  validId,
} from './membership';

export function JoinGroupPage({ groupId }: { groupId: string }) {
  const [token] = useState(() => captureInvite(groupId));
  const [nameError, setNameError] = useState('');
  const membership = readMembership(groupId);
  const navigate = useNavigate();
  const access = useQuery({
    queryKey: membership ? groupKey(membership) : ['join-access', groupId],
    queryFn: membership
      ? ({ signal }) => readGroup(membership, signal)
      : skipToken,
    staleTime: 0,
    retry: false,
    refetchInterval: false,
  });
  const invalidMembership =
    access.error instanceof ApiError &&
    [401, 403].includes(access.error.status);
  const join = useMutation({
    mutationFn: async (name: string) => {
      const response = await joinGroup(groupId, token!, name);
      saveMembership(response);
      clearInvite(groupId);
      return response.group.groupId;
    },
    retry: false,
    onSuccess: (id) => {
      void navigate({
        to: '/groups/$groupId',
        params: { groupId: id },
        replace: true,
      });
    },
  });
  if (membership && access.isSuccess && access.isFetchedAfterMount)
    return <Navigate to="/groups/$groupId" params={{ groupId }} replace />;
  // Only a confirmed permission failure permits rejoining. A transient outage
  // must not spend another group slot for an existing member.
  if (membership && !invalidMembership)
    return (
      <GroupShell>
        <section className="surface live-join">
          <h1>Reopening your membership.</h1>
          {access.isPending || access.isFetching ? (
            <p role="status">Checking this browser’s saved membership…</p>
          ) : (
            <Alert role="alert" variant="destructive">
              <AlertTitle>Could not verify your membership</AlertTitle>
              <AlertDescription>{errorMessage(access.error)}</AlertDescription>
            </Alert>
          )}
          <Button
            disabled={access.isFetching}
            onClick={() => {
              void access.refetch();
            }}
          >
            Check membership again
          </Button>
          <Link to="/groups/$groupId" params={{ groupId }}>
            Open saved group
          </Link>
        </section>
      </GroupShell>
    );
  return (
    <GroupShell>
      <section className="surface live-join">
        <h1>Make room for your next chapter.</h1>
        {!validId(groupId) || !token ? (
          <Alert role="alert">
            <AlertTitle>This invite is incomplete</AlertTitle>
            <AlertDescription>
              Ask the organiser to send the full original invite link. If you
              already joined, reopen your group in the browser you used before.
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <p className="lead">
              Join your flatmates with your first name. Your membership will be
              saved in this browser.
            </p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (join.isPending) return;
                const name = String(
                  new FormData(event.currentTarget).get('name') ?? '',
                ).trim();
                if (!zJoinGroupBody.safeParse({ name }).success) {
                  setNameError('Enter a name from 1 to 30 characters.');
                  return;
                }
                setNameError('');
                join.mutate(name);
              }}
            >
              <FieldGroup>
                <Field data-invalid={!!nameError}>
                  <FieldLabel htmlFor="join-name">Your first name</FieldLabel>
                  <Input
                    id="join-name"
                    name="name"
                    autoComplete="given-name"
                    maxLength={30}
                    required
                    disabled={join.isPending}
                    aria-invalid={!!nameError}
                    aria-describedby={
                      nameError ? 'join-name-error' : 'join-name-help'
                    }
                  />
                  <FieldDescription id="join-name-help">
                    Choose a name your flatmates recognise. Names must be unique
                    in this group.
                  </FieldDescription>
                  {nameError && (
                    <FieldError id="join-name-error">{nameError}</FieldError>
                  )}
                </Field>
                <Alert>
                  <AlertDescription>
                    Your flatmates can see your name and any destination area,
                    budget and commute limit you later submit. Groups expire 30
                    days after creation. Keep your membership in this browser;
                    lost access cannot be recovered when the group is full.
                  </AlertDescription>
                </Alert>
                {join.isError && (
                  <Alert role="alert" variant="destructive">
                    <AlertTitle>Could not join the group</AlertTitle>
                    <AlertDescription>
                      {errorMessage(join.error)}
                    </AlertDescription>
                  </Alert>
                )}
                <Button type="submit" disabled={join.isPending}>
                  {join.isPending ? 'Joining…' : 'Join the group'}
                </Button>
              </FieldGroup>
            </form>
          </>
        )}
        <Link to="/" search={{}} className="text-sm underline">
          Return home
        </Link>
      </section>
    </GroupShell>
  );
}

export function JoinRoutePage() {
  const { groupId } = useParams({ from: '/join/$groupId' });
  return <JoinGroupPage key={groupId} groupId={groupId} />;
}
