import { useMutation } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { CreateGroup } from '@/features/wireframes/GroupViews';
import { GroupShell } from './GroupShell';
import { createGroup, errorMessage } from './api';
import { saveMembership, savedMemberships } from './membership';

export function CreateGroupPage() {
  const navigate = useNavigate();
  const groups = savedMemberships();
  const creation = useMutation({
    mutationFn: async (body: {
      groupName: string;
      name: string;
      size: number;
    }) => {
      const response = await createGroup(body);
      saveMembership(response);
      return response.group.groupId;
    },
    retry: false,
    onSuccess: (groupId) => {
      void navigate({ to: '/groups/$groupId', params: { groupId } });
    },
  });
  return (
    <GroupShell>
      {groups.length > 0 && (
        <section className="live-saved-groups" aria-label="Your saved groups">
          <h2>Pick up where you left off</h2>
          <ul>
            {groups.map((group) => (
              <li key={group.groupId}>
                <Link to="/groups/$groupId" params={{ groupId: group.groupId }}>
                  {group.groupName}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
      <CreateGroup
        live
        pending={creation.isPending}
        errorMessage={
          creation.isError ? errorMessage(creation.error) : undefined
        }
        onCreate={(group) =>
          creation.mutate({
            groupName: group.name,
            size: group.size,
            name: group.members[0]!.name,
          })
        }
        onDemo={() => {
          void navigate({ to: '/', search: { review: 'results' } });
        }}
      />
    </GroupShell>
  );
}
