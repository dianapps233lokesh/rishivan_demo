"""The corpus catalogue. One row per physical edition we ingest."""

from enum import StrEnum

from sqlalchemy import Boolean, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CopyrightStatus(StrEnum):
    """Sanskrit originals are public domain; a translation of one is not.

    `unknown` is treated exactly as `restricted` everywhere it matters. An
    unclassified book must fail to the safe side, because the cost of being
    wrong is asymmetric: over-restricting loses a quotation, under-restricting
    republishes an author's prose.
    """

    public_domain = "public_domain"
    restricted = "restricted"
    unknown = "unknown"


RESTRICTED_STATUSES = frozenset({CopyrightStatus.restricted, CopyrightStatus.unknown})
"""What the verbatim guard and the Qdrant payload filter both treat as restricted."""

DEFAULT_VERBATIM_QUOTA_CHARS = 90


class Book(Base):
    __tablename__ = "book"

    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200))
    translator: Mapped[str | None] = mapped_column(String(200))
    edition: Mapped[str | None] = mapped_column(String(120))
    publisher: Mapped[str | None] = mapped_column(String(200))
    year: Mapped[int | None] = mapped_column(Integer)

    copyright_status: Mapped[CopyrightStatus] = mapped_column(
        String(20),
        nullable=False,
        default=CopyrightStatus.unknown,
        server_default=CopyrightStatus.unknown.value,
    )
    verbatim_quota_chars: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_VERBATIM_QUOTA_CHARS,
        server_default=text(str(DEFAULT_VERBATIM_QUOTA_CHARS)),
    )
    """Max verbatim characters quotable. Enforced by the 12-gram overlap check."""

    school: Mapped[str | None] = mapped_column(String(40))
    """parashari | jaimini | kp | lal_kitab | nadi | numerology | muhurta |
    prashna | matchmaking"""

    layer: Mapped[str] = mapped_column(String(30), nullable=False)
    """knowledge | prediction | timing | question | muhurta | remedies |
    numerology | matchmaking"""

    source_authority_tier: Mapped[str] = mapped_column(
        String(2), nullable=False, default="S0", server_default="S0"
    )
    """S0 primary classical text; S1 traditional commentary; S2 scholarly or
    critical edition; S3 established practitioner; S4 modern interpretation;
    S5 experimental or community material.

    An engineering category for evidence weighting, not a claim about spiritual
    authority. BPHS is S0."""

    domains: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default=text("100")
    )
    """Review-queue ordering. Lower sorts first."""

    page_count: Mapped[int | None] = mapped_column(Integer)
    source_uri: Mapped[str | None] = mapped_column(Text)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    has_text_layer: Mapped[bool | None] = mapped_column(Boolean)

    __table_args__ = (
        Index(
            "uq_book_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_book_priority", "priority"),
    )

    def __repr__(self) -> str:
        return f"<Book {self.slug!r}>"
