from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DateFormat = Literal["YYYYMMDD", "YYMMDD", "MMDD", "DDMM", "ROCYYYMMDD", "ROCYYMMDD"]
Separator = Literal["", "-", "_", ".", "/"]


class PasswordRulePart(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source: Literal["national_id", "birthday"]
    transform: Literal["full", "prefix", "suffix", "substring", "date_format"]
    start: int | None
    length: int | None
    date_format: DateFormat | None
    case: Literal["preserve", "upper", "lower"]

    @model_validator(mode="after")
    def validate_transform(self):
        if self.transform in {"prefix", "suffix"}:
            if self.source != "national_id" or self.length is None or self.length < 1 or self.length > 12:
                raise ValueError("prefix/suffix requires a national_id and a length from 1 to 12")
            if self.start is not None or self.date_format is not None:
                raise ValueError("prefix/suffix does not accept start or date_format")
        elif self.transform == "substring":
            if self.source != "national_id" or self.start is None or self.start < 0 or self.length is None or not 1 <= self.length <= 12:
                raise ValueError("substring requires national_id, a non-negative start, and a length from 1 to 12")
            if self.date_format is not None:
                raise ValueError("substring does not accept date_format")
        elif self.transform == "date_format":
            if self.source != "birthday" or self.date_format is None:
                raise ValueError("date_format requires birthday and an explicit supported date format")
            if self.start is not None or self.length is not None:
                raise ValueError("date_format does not accept start or length")
        elif self.start is not None or self.length is not None or self.date_format is not None:
            raise ValueError("full does not accept transform parameters")
        if self.source == "birthday" and self.transform != "date_format":
            raise ValueError("birthday must use an explicit date_format")
        if self.source == "national_id" and self.transform == "date_format":
            raise ValueError("date_format only applies to birthday")
        return self


class PasswordCandidateRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    parts: list[PasswordRulePart] = Field(min_length=1, max_length=6)
    separator: Separator


class PasswordRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    status: Literal["resolved", "ambiguous", "unsupported"]
    candidates: list[PasswordCandidateRule] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_status(self):
        if self.status == "resolved" and len(self.candidates) != 1:
            raise ValueError("resolved rules require exactly one candidate")
        if self.status == "ambiguous" and not 2 <= len(self.candidates) <= 3:
            raise ValueError("ambiguous rules require two or three candidates")
        if self.status == "unsupported" and self.candidates:
            raise ValueError("unsupported rules must not include candidates")
        return self
