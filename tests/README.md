# Shared test data

All data is synthetic. Fixtures are function-scoped; database rows use the
existing isolated `*_test` database and file storage uses `tmp_path`.

- `demo_client`: one persisted client, unchanged for existing tests.
- `client_factory(name="Demo Client")`: create additional independent clients.
- `stored_document(data=..., filename=..., content_type=...)`: create a document
  for `demo_client` and save its bytes in temporary storage. Returns the model.
  This deliberately bypasses upload validation for service and legacy-file tests.
- `sample_profile`: a fresh dictionary with business name, industry, and goals.
  It is illustrative data only; this branch has no production profile model.
- `tests.sample_data.make_pdf(pages, password=None)`: generate real PDF bytes,
  including blank or encrypted samples. TXT and Markdown samples can be passed
  as bytes to `stored_document`.
- `tests.sample_data.invalid_upload_samples()`: reusable unsupported, invalid
  UTF-8, blank, malformed, and encrypted upload cases with expected statuses.

Existing extraction, upload-rejection, and client-isolation tests exercise these
helpers. Run the suite from the repository root with `pytest`.
