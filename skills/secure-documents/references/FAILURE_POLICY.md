# Failure Policy

The core fails closed.

## verified

Use only when:

- source is a valid PDF,
- encrypted source was successfully unlocked locally,
- native extraction completed,
- the IR passed structural validation.

This says nothing about downstream semantic correctness.

## needs_review

Use when:

- encrypted PDF has no usable symbolic rule,
- required local credential reference/value is unavailable,
- all allowed candidates failed,
- extraction completed but warnings indicate insufficient quality for the requested downstream task.

Do not silently guess another password pattern.

## unsupported

Use when:

- source is not a PDF for the PDF adapter,
- PDF is malformed or uses unsupported encryption,
- the extractor cannot read it.

## Principle

A partially plausible extraction is not the same as a verified document. Preserve the original encrypted source so improved extractors can replay it later.
