import { addSourcesHref } from '../router'

// Command, the home page. Only the "New intake" entry point exists so far.
export default function CommandPage() {
  return (
    <section className="placeholder">
      <h1 className="visually-hidden">Command</h1>
      <a className="button button-primary" href={addSourcesHref()}>
        New intake
      </a>
    </section>
  )
}
