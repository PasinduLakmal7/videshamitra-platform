"""Source grounding: every finding must cite a document page, an SLBFE record or a rule row."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class DocumentCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["document"] = "document"
    document_id: UUID
    page: int = Field(ge=1)
    quote: str | None = Field(default=None, max_length=500)


class SlbfeCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["slbfe_record"] = "slbfe_record"
    record_id: str = Field(min_length=1, max_length=100)
    list_date: date


class RuleCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["rule"] = "rule"
    rule_id: str = Field(min_length=1, max_length=100)


Citation = Annotated[DocumentCitation | SlbfeCitation | RuleCitation, Field(discriminator="kind")]
Severity = Literal["info", "low", "medium", "high", "critical"]


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    severity: Severity = "medium"
    citation: Citation | None = None


@dataclass(frozen=True)
class GroundingContext:
    # Known documents and their page counts (None when the count is unknown).
    document_pages: Mapping[UUID, int | None] = field(default_factory=dict)
    rule_ids: frozenset[str] = frozenset()
    slbfe_record_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Grounded:
    findings: list[Finding]
    dropped: dict[str, int]

    @property
    def unable_to_verify(self) -> bool:
        return not self.findings


def _drop_reason(finding: Finding, ctx: GroundingContext) -> str | None:
    citation = finding.citation
    match citation:
        case None:
            return "uncited"
        case DocumentCitation(document_id=doc, page=page):
            if doc not in ctx.document_pages:
                return "unknown_document"
            pages = ctx.document_pages[doc]
            if pages is not None and page > pages:
                return "page_out_of_range"
        case SlbfeCitation(record_id=record):
            if record not in ctx.slbfe_record_ids:
                return "unknown_slbfe_record"
        case RuleCitation(rule_id=rule):
            if rule not in ctx.rule_ids:
                return "unknown_rule"
    return None


def ground(findings: Iterable[Finding], ctx: GroundingContext) -> Grounded:
    kept: list[Finding] = []
    dropped: Counter[str] = Counter()
    for finding in findings:
        reason = _drop_reason(finding, ctx)
        if reason is None:
            kept.append(finding)
        else:
            dropped[reason] += 1
    if dropped:
        logger.warning("findings_dropped", extra={"dropped": dict(dropped)})
    return Grounded(findings=kept, dropped=dict(dropped))
