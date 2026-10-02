from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    filename: str
    mime_type: str
    size_bytes: int = Field(ge=0)


class UnlockResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["not_needed", "unlocked"]
    was_encrypted: bool
    candidate_count: int = Field(ge=0, le=3)
    rule_fingerprint: str | None = None

    @model_validator(mode="after")
    def validate_state(self):
        if self.status == "not_needed" and self.was_encrypted:
            raise ValueError("encrypted source cannot have not_needed unlock status")
        if self.status == "unlocked" and not self.was_encrypted:
            raise ValueError("unencrypted source should use not_needed")
        return self


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    block_id: str
    text: str
    x: float | None = None
    y: float | None = None
    font_size: float | None = None


class PageIR(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_number: int = Field(ge=1)
    text: str
    blocks: tuple[TextBlock, ...] = ()


class ExtractionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    extractor: str
    extractor_version: str
    method: Literal["native_text", "native_layout"]
    warnings: tuple[str, ...] = ()


class DocumentIR(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ir_version: Literal["1"] = "1"
    document_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str
    page_count: int = Field(ge=1)
    unlock: UnlockResult
    extraction: ExtractionMetadata
    pages: tuple[PageIR, ...]

    @model_validator(mode="after")
    def validate_pages(self):
        if len(self.pages) != self.page_count:
            raise ValueError("page count does not match pages")
        if tuple(page.page_number for page in self.pages) != tuple(range(1, self.page_count + 1)):
            raise ValueError("pages must be contiguous and 1-based")
        return self


class LiteralSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["literal"]
    value: str = Field(min_length=1, max_length=64)


class SecretSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["secret"]
    secret: Literal["national_id", "birthday"]
    start: int | None = None
    end: int | None = None
    transform: Literal["none", "upper", "lower", "digits_only"] = "none"
    date_format: Literal["ISO", "YYYYMMDD", "YYMMDD", "MMDD"] | None = None


PasswordSegment = Annotated[LiteralSegment | SecretSegment, Field(discriminator="kind")]


class PasswordCandidateRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    segments: tuple[PasswordSegment, ...] = Field(min_length=1, max_length=8)


class PasswordRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["resolved", "ambiguous"]
    candidates: tuple[PasswordCandidateRule, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def status_matches_candidates(self):
        if self.status == "resolved" and len(self.candidates) != 1:
            raise ValueError("resolved rule requires exactly one candidate")
        return self


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_id: str
    page_number: int = Field(ge=1)
    block_ids: tuple[str, ...] = ()


class ExtractedFact(BaseModel):
    """Reserved downstream contract; not produced by the v0.1 extractor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    value: str | int | float | bool | None
    confidence: Literal["verified", "inferred", "needs_review"]
    evidence: tuple[EvidenceRef, ...] = ()
