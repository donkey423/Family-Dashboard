# DocumentIR v1

`DocumentIR` is deliberately neutral about document meaning.

## Top-level fields

- `ir_version`: contract version.
- `document_id`: stable identifier for this source object.
- `source_sha256`: hash of original bytes.
- `mime_type`: source MIME type.
- `page_count`: number of PDF pages.
- `unlock`: metadata about whether the source was encrypted and whether it was unlocked; never contains the password.
- `extraction`: extractor name/version/method and warning codes.
- `pages`: page-local text and blocks.

## Page

Each page contains:

- `page_number`
- `text`
- `blocks[]`

A text block contains:

- stable block ID within this extraction run
- text
- optional x/y coordinates
- optional font size

Tables/images are planned extensions and should be added as new IR fields without changing domain parsers into PDF parsers.

## Evidence

Downstream facts should point to `document_id`, `page_number`, and block IDs. A fact without evidence should not be treated as strongly verified simply because an LLM produced it.
