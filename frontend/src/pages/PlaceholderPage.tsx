type PlaceholderPageProps = {
  title: string
}

// An empty page for a menu item that isn't built yet. The title is only read by
// screen readers, so the page looks blank.
export default function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <section className="placeholder">
      <h1 className="visually-hidden">{title}</h1>
    </section>
  )
}
