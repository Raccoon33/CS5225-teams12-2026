import { useState } from 'react';
import { Link, useParams } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { Link2, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Field, FieldLabel, FieldDescription } from '@/components/ui/field';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { GroupShell } from './GroupShell';
import { SearchProgress } from './SearchProgress';
import { errorMessage, groupOptions } from './api';
import {
  inviteLink,
  membershipIsPersisted,
  readMembership,
  validId,
  type Membership,
} from './membership';

export function LiveGroupPage({ groupId }: { groupId: string }) {
  const membership = readMembership(groupId);
  if (!membership)
    return (
      <GroupShell>
        <section className="surface live-join">
          <h1>
            {validId(groupId)
              ? 'Reopen your shared group.'
              : 'This group link is invalid.'}
          </h1>
          <p>
            You need the membership saved in the browser where you created or
            joined this group. Otherwise, ask the organiser for the original
            invite link to join if there is space.
          </p>
          <Link to="/" search={{}} className="underline">
            Return home
          </Link>
        </section>
      </GroupShell>
    );
  return <MemberGroup membership={membership} />;
}
function MemberGroup({ membership }: { membership: Membership }) {
  const group = useQuery(groupOptions(membership));
  const [copyStatus, setCopyStatus] = useState('');
  const link = inviteLink(membership);
  const data = group.data;
  // Auth/expiry errors must not continue to show previously cached member data.
  const blocked =
    group.isError &&
    (!data ||
      ('status' in group.error &&
        [401, 403, 404].includes(Number(group.error.status))));
  return (
    <GroupShell>
      {!membershipIsPersisted(membership) && (
        <Alert role="alert">
          <AlertTitle>Keep this tab open</AlertTitle>
          <AlertDescription>
            This browser could not save your membership. Refreshing or closing
            the tab may lose your access. Allow browser storage before creating
            or joining another group.
          </AlertDescription>
        </Alert>
      )}
      {group.isPending && <p role="status">Opening your group…</p>}
      {group.isError && (
        <Alert role="alert" variant="destructive">
          <AlertTitle>Could not refresh your group</AlertTitle>
          <AlertDescription>
            {errorMessage(group.error)}
            <Button
              variant="outline"
              disabled={group.isFetching}
              onClick={() => {
                void group.refetch();
              }}
            >
              Try opening again
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {data && !blocked && (
        <>
          <div className="page-heading">
            <div>
              <h1>{data.groupName}</h1>
              <p className="lead">
                A place starts with people. Bring everyone’s needs to the table.
              </p>
            </div>
            <Badge variant="secondary">
              {data.readyCount} of {data.size} ready
            </Badge>
          </div>
          <div className="content-columns">
            <section className="surface" aria-labelledby="flatmates-heading">
              <div className="section-heading">
                <h2 id="flatmates-heading">Your flatmates</h2>
                <Users size={20} />
              </div>
              <ul className="member-list">
                {data.members.map((member, index) => (
                  <li className="member-row" key={member.memberId}>
                    <div className={`person-avatar member-color-${index}`}>
                      {member.name.slice(0, 1).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3>
                        {member.name}
                        {member.memberId === membership.memberId
                          ? ' · you'
                          : ''}
                        {member.isOrganiser ? ' · organiser' : ''}
                      </h3>
                      <p>
                        {member.ready && member.destination
                          ? `${member.destination.label} · S$${member.budget?.toLocaleString('en-SG')}/month · up to ${member.maxCommute} min`
                          : 'Preferences not submitted yet'}
                      </p>
                    </div>
                    <Badge variant={member.ready ? 'secondary' : 'outline'}>
                      {member.ready ? 'Ready' : 'Waiting'}
                    </Badge>
                  </li>
                ))}
              </ul>
              {data.members.length < data.size && (
                <p className="fine-print">
                  {data.size - data.members.length}{' '}
                  {data.size - data.members.length === 1 ? 'place' : 'places'}{' '}
                  still available.
                </p>
              )}
              <p className="fine-print">
                Only your own membership can save your preferences. Group
                expires {new Date(data.expiresAt).toLocaleDateString('en-SG')}.
              </p>
              <Button
                variant="outline"
                disabled={group.isFetching}
                onClick={() => {
                  void group.refetch();
                }}
              >
                {group.isFetching ? 'Refreshing…' : 'Refresh group'}
              </Button>
            </section>
            <aside className="surface live-invite">
              <h2>Bring your flatmates along.</h2>
              {link ? (
                <>
                  <Field>
                    <FieldLabel htmlFor="invite-link">
                      Your group’s invite link
                    </FieldLabel>
                    <Input
                      id="invite-link"
                      readOnly
                      value={link}
                      onFocus={(event) => event.currentTarget.select()}
                      aria-describedby="invite-help"
                    />
                    <FieldDescription id="invite-help">
                      Share this link only with your flatmates. It lets someone
                      join while there is space. Your personal membership stays
                      in this browser.
                    </FieldDescription>
                  </Field>
                  <Button
                    variant="outline"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(link);
                        setCopyStatus('Invite link copied.');
                      } catch {
                        setCopyStatus(
                          'Copy was unavailable. Select the invite link above and copy it manually.',
                        );
                      }
                    }}
                  >
                    <Link2 data-icon="inline-start" />
                    Copy invite link
                  </Button>
                  <p role="status" className="text-sm">
                    {copyStatus}
                  </p>
                </>
              ) : (
                <p className="muted">
                  The organiser keeps the original invite link. Ask them to
                  share it with anyone who still needs to join.
                </p>
              )}
              <p className="fine-print">
                Use this same browser to reopen your membership. There is no
                account login or token recovery; if the group is full, lost
                membership cannot be replaced.
              </p>
            </aside>
          </div>
          {!group.isError && (
            <SearchProgress
              group={data}
              membership={membership}
              groupUpdatedAt={group.dataUpdatedAt}
            />
          )}
        </>
      )}
    </GroupShell>
  );
}

export function GroupRoutePage() {
  const { groupId } = useParams({ from: '/groups/$groupId' });
  return <LiveGroupPage key={groupId} groupId={groupId} />;
}
