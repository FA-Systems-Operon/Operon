import { Fragment } from 'react'
import './DraftSourceView.css'
import { mapSourceReferences, ONBOARDING_FIELDS, type DraftField, type SourceLinkedDraft } from './draftSources'

type DraftSourceViewProps = {
  draft: Partial<SourceLinkedDraft>
  // The review page (#57) decides where a source link points.
  getSourceHref: (documentId: string, quote: string) => string
  // Use document metadata from the host page; never infer kind from quote text.
  getSourceLabel?: (documentId: string) => string | undefined
}

const GROUPS = [
  { key: 'name', label: 'Name', empty: 'Not extracted' },
  { key: 'needs', label: 'Needs', empty: 'None extracted' },
  { key: 'goals', label: 'Goals', empty: 'None extracted' },
  ...ONBOARDING_FIELDS.map((field) => ({ ...field, empty: 'Not extracted' })),
]

export default function DraftSourceView({ draft, getSourceHref, getSourceLabel }: DraftSourceViewProps) {
  const fields = mapSourceReferences(draft)
  const assessment = draft.assessment
  const assessed = assessment?.rules_version === 1
  const conflicts = draft.conflicts ?? []
  const knownKeys = new Set([...GROUPS.map((group) => group.key), ...fields.map((field) => field.key)])
  const unsupported = conflicts.some((conflict) => !knownKeys.has(conflict.field))
    || (assessment?.missing_fields ?? []).some((field) => !ONBOARDING_FIELDS.some(({ key }) => key === field))

  const documentIds = [...new Set([
    ...(draft.source_references ?? []).map((reference) => reference.document_id),
    ...conflicts.flatMap((conflict) => conflict.alternatives.map((alternative) => alternative.document_id)),
  ])]
  const sourceLabel = (id: string) => getSourceLabel?.(id) || `Source ${documentIds.indexOf(id) + 1}`
  const rowClass = (key: string) => `draft-source-view__row${conflicts.some((conflict) => conflict.field === key)
    ? ' draft-source-view__row--conflict'
    : assessed && assessment.missing_fields.includes(key) ? ' draft-source-view__row--missing' : ''}`

  function renderWarnings(key: string, label: string) {
    return (
      <>
        {assessed && assessment.missing_fields.includes(key) && (
          <p><strong><span aria-hidden="true">◌ </span>Missing information:</strong> {label} was not extracted from the supplied sources.</p>
        )}
        {conflicts.filter((conflict) => conflict.field === key).map((conflict, index) => (
          <section key={index} aria-label={`Potential conflict for ${label}`}>
            <p><strong><span aria-hidden="true">▲ </span>Potential conflict:</strong> {conflict.explanation}</p>
            <p>Both claims are preserved for review. Neither source has been selected.</p>
            <ul>
              {conflict.alternatives.map((alternative, alternativeIndex) => (
                <li key={alternativeIndex}>
                  <span className="draft-source-view__source-label">{sourceLabel(alternative.document_id)}</span>
                  <strong>{alternative.value}</strong> — <q>{alternative.quote}</q>{' '}
                  <a
                    href={getSourceHref(alternative.document_id, alternative.quote)}
                    aria-label={`View conflict source ${alternativeIndex + 1} for ${label}`}
                  >View source</a>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </>
    )
  }

  function renderField(field: DraftField) {
    return (
      <div key={field.key} className={rowClass(field.key)}>
        <dt>{field.label}</dt>
        <dd>
          <span className="draft-source-view__value">{field.value}</span>
          {renderWarnings(field.key, field.label)}
          {field.references.length === 0 ? (
            <p>No source linked</p>
          ) : (
            <ul>
              {field.references.map((reference, index) => (
                <li key={index}>
                  <span className="draft-source-view__source-label">{sourceLabel(reference.document_id)}</span>
                  <q>{reference.quote}</q>{' '}
                  <a
                    href={getSourceHref(reference.document_id, reference.quote)}
                    aria-label={`View source for ${field.label}`}
                  >View source</a>
                </li>
              ))}
            </ul>
          )}
        </dd>
      </div>
    )
  }

  return (
    <section className="draft-source-view" aria-label="Draft profile">
      {!assessed && <p>Information checks were not recorded for this draft.</p>}
      {unsupported && <p>Some information warnings could not be displayed. Review the saved draft data.</p>}
      {assessed && !unsupported && assessment.missing_fields.length === 0 && conflicts.length === 0 && (
        <p>No missing information or potential conflicts were recorded.</p>
      )}
      <dl>
        {GROUPS.map((group) => {
          const rows = fields.filter((field) => field.key.split('/')[0] === group.key)
          const groupConflict = conflicts.some((conflict) => conflict.field === group.key)
          // Assessed drafts show all required fields, including absent ones.
          if (!assessed && rows.length === 0 && !groupConflict
            && ONBOARDING_FIELDS.some(({ key }) => key === group.key)) return null
          return rows.length > 0 ? (
            <Fragment key={group.key}>
              {groupConflict && (group.key === 'needs' || group.key === 'goals') && (
                <div className={rowClass(group.key)}><dt>{group.label}</dt><dd>{renderWarnings(group.key, group.label)}</dd></div>
              )}
              {rows.map(renderField)}
            </Fragment>
          ) : (
            <div key={group.key} className={rowClass(group.key)}>
              <dt>{group.label}</dt>
              <dd><span className="draft-source-view__empty">{groupConflict ? 'Conflicting values' : group.empty}</span>{renderWarnings(group.key, group.label)}</dd>
            </div>
          )
        })}
      </dl>
    </section>
  )
}
