# Draft profile view (#41, #44)

`DraftSourceView` renders the source-linked draft stored in a profile version's
`data`. Pass `draft={version.data}` and a `getSourceHref(documentId, quote)`
callback supplied by the review page. It renders required onboarding fields,
server-recorded missing information, potential conflicts with both alternatives,
and exact evidence quotes/links. Warnings use visible text rather than color;
links are keyboard accessible and source text is escaped by React.

Historical drafts without `assessment.rules_version === 1` say checks were not
recorded. Unknown field paths produce a warning rather than a clean assessment.
`assessment` is computed by the backend, not by this component. It does not
establish model accuracy or implement conflict resolution/approval controls.

The full review page and its source navigation are tracked in #57. Tests here
verify the reusable component, not a complete browser workflow. The production
App does not mount this component yet; #57 must supply the saved version and
client-scoped source-link destination. Generic draft edits must invalidate or
recompute completeness before presenting a current assessment.
