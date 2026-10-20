import { createFileRoute } from '@tanstack/react-router';
import { GroupRoutePage } from '@/features/groups/LiveGroupPage';
export const Route = createFileRoute('/groups/$groupId')({
  component: GroupRoutePage,
});
