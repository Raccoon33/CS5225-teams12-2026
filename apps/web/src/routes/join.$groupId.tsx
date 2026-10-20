import { createFileRoute } from '@tanstack/react-router';
import { JoinRoutePage } from '@/features/groups/JoinGroupPage';
export const Route = createFileRoute('/join/$groupId')({
  component: JoinRoutePage,
});
