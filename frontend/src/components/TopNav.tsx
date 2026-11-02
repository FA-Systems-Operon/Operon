export type Tab = 'command' | 'brain' | 'workforce' | 'reviews'

const TABS: { id: Tab; label: string; href: string }[] = [
  { id: 'command', label: 'Command', href: '#/' },
  { id: 'brain', label: 'Brain', href: '#/brain' },
  { id: 'workforce', label: 'Workforce', href: '#/workforce' },
]

type TopNavProps = {
  active: Tab | null
}

export default function TopNav({ active }: TopNavProps) {
  const current = (tab: Tab) => (active === tab ? 'page' : undefined)

  return (
    <header className="topnav">
      <div className="topnav-brand">
        <a className="brand" href="#/">
          <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
            <rect width="24" height="24" rx="6" />
            <circle cx="12" cy="12" r="4.5" />
            <path d="M4 12h16" />
          </svg>
          Operon
        </a>
        <span className="topnav-org">FA Systems</span>
      </div>

      <nav aria-label="Main">
        <ul className="tabs">
          {TABS.map((tab) => (
            <li key={tab.id}>
              <a className="tab" href={tab.href} aria-current={current(tab.id)}>
                {tab.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <a className="topnav-reviews" href="#/reviews" aria-current={current('reviews')}>
        Reviews
      </a>
    </header>
  )
}
