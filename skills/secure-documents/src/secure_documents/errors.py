class SecureDocumentError(RuntimeError):
    code = "secure_document_error"


class UnsupportedDocument(SecureDocumentError):
    code = "unsupported_document"


class UnlockNeedsReview(SecureDocumentError):
    code = "unlock_needs_review"


class ExtractionFailed(SecureDocumentError):
    code = "extraction_failed"
