import { mapSourceReferences, type DraftField, type SourceLinkedDraft } from './draftSources'

type DraftSourceViewProps = {
  draft: Partial<SourceLinkedDraft>
  // The review page (#57) decides where a source link points.
  getSourceHref: (documentId: string, quote: string) => string
}

const GROUPS = [
  { key: 'name', label: 'Name', empty: 'Not extracted' },
  { key: 'needs', label: 'Needs', empty: 'None extracted' },
  { key: 'goals', label: 'Goals', empty: 'None extracted' },
]

export default function DraftSourceView({ draft, getSourceHref }: DraftSourceViewProps) {
  const fields = mapSourceReferences(draft)

  function renderField(field: DraftField) {
    return (
      <div key={field.key}>
        <dt>{field.label}</dt>
        <dd>
          {field.value}
          {field.references.length === 0 ? (
            <p>No source linked</p>
          ) : (
            <ul>
              {field.references.map((reference, index) => (
                <li key={index}>
                  <q>{reference.quote}</q>{' '}
                  <a
                    href={getSourceHref(reference.document_id, reference.quote)}
                    aria-label={`View source for ${field.label}`}
                  >
                    View source
                  </a>
                </li>
              ))}
            </ul>
          )}
        </dd>
      </div>
    )
  }

  return (
    <dl>
      {GROUPS.map((group) => {
        const rows = fields.filter((field) => field.key.split('/')[0] === group.key)
        return rows.length > 0 ? (
          rows.map(renderField)
        ) : (
          <div key={group.key}>
            <dt>{group.label}</dt>
            <dd>{group.empty}</dd>
          </div>
        )
      })}
    </dl>
  )
}
