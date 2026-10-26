import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from '@tanstack/react-router';
import { ArrowUpRight, House, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export function GroupShell({
  children,
  step = 'Your group',
}: {
  children: ReactNode;
  step?: string;
}) {
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    const heading = main.current?.querySelector('h1');
    if (heading) heading.tabIndex = -1;
    (heading ?? main.current)?.focus({ preventScroll: true });
  }, []);
  return (
    <>
      <header className="app-header live-header">
        <Link to="/" search={{}} className="brand" aria-label="FlatSplit home">
          <span className="brand-icon">
            <House size={20} />
          </span>
          FlatSplit<span className="brand-period">.</span>
        </Link>
        <div className="header-context">A better move, together.</div>
        <Link to="/" search={{ review: 'results' }} className="live-demo-link">
          Explore the demo <ArrowUpRight size={14} aria-hidden="true" />
        </Link>
      </header>
      <main
        id="main-content"
        ref={main}
        tabIndex={-1}
        className="workspace live-workspace"
      >
        <div className="workspace-breadcrumb">
          <Users size={16} aria-hidden="true" />
          <span>Your home search</span>
          <span>/</span>
          <strong>{step}</strong>
          <Badge variant="outline" className="ml-auto">
            Shared group
          </Badge>
        </div>
        {children}
        <footer className="workspace-footer">
          <span>2–5 flatmates. One shared decision.</span>
          <span>Historical rent estimates · Station-to-station commutes</span>
        </footer>
      </main>
    </>
  );
}
