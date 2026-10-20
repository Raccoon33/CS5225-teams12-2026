import { useSearch } from '@tanstack/react-router';
import { CreateGroupPage } from '@/features/groups/CreateGroupPage';
import { WireframeApp } from '@/features/wireframes/WireframeApp';

export function HomePage() {
  const { review } = useSearch({ from: '/' });
  return review ? (
    <WireframeApp key={review} initialPreview={review} />
  ) : (
    <CreateGroupPage />
  );
}
