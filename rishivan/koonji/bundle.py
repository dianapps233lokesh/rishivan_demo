"""koonji.bundle - the deployable artifact.

The knowledge graph should be compiled into memory, not queried over the
network. Ontology, rules, sources and their relationships are on the order of
tens of thousands of nodes: not big data, a data structure, and one that is
read-only between releases. Paying a graph database five to twenty milliseconds
per traversal hop to answer what could be an array lookup is a cost with no
corresponding benefit, and it puts another service in the availability chain.

So the bundle is a single content-addressed file, built by CI, published once,
and loaded whole at worker start. Same move a database makes when it compiles a
query plan. The knowledge base is a program; compile it.

The payoff is reproducibility. Pin the bundle hash on an inference run and the
answer can be reconstructed years later, byte for byte: same rules, same
registry, same index, same evidence graph. That trace is the moat - any
competitor can wire a model to an ephemeris in a month, and none of them can
tell you why a rule fired in 2026.

Two guards matter more than the format:

  * the **registry fingerprint** is recorded, and loading a bundle against a
    different registry is refused. A predicate whose signature moved would
    silently change what every rule using it means.
  * the **content hash** covers the rules, not the timestamp, so rebuilding an
    unchanged corpus produces the same identity and a real change never hides.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from rishivan.koonji.facts import AtomTable
from rishivan.koonji.index import RuleIndex
from rishivan.koonji.registry import Registry
from rishivan.koonji.urf import FRAME_VERSION, AssertionKind, Rule

BUNDLE_FORMAT = 1


class BundleMismatch(RuntimeError):
    """The bundle was compiled against a different registry.

    Refused at load, loudly. A predicate whose signature moved changes the
    meaning of every rule that used it, and a rule store that means something
    different than it did is worse than one that fails to load.
    """


def _variant_domains(raw: Any) -> dict[str, float]:
    """Read a variant's domain tags, in either serialised shape.

    Variants used to store domains as a sorted list, having dropped the weights
    the rule declared. A bundle written before the weights were kept still loads
    - every tag reads as 1.0, which is what "no weight recorded" has to mean if
    a domain filter is not to start excluding rules it previously admitted.
    """
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items()}
    return {str(d): 1.0 for d in raw}


@dataclass(slots=True)
class Manifest:
    bundle_id: str
    format: int
    frame_version: str
    registry_version: str
    registry_fingerprint: str
    rule_count: int
    derivation_count: int
    variant_count: int
    atom_count: int
    built_at: str
    source_books: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "format": self.format,
            "frame_version": self.frame_version,
            "registry_version": self.registry_version,
            "registry_fingerprint": self.registry_fingerprint,
            "rule_count": self.rule_count,
            "derivation_count": self.derivation_count,
            "variant_count": self.variant_count,
            "atom_count": self.atom_count,
            "built_at": self.built_at,
            "source_books": self.source_books,
        }


@dataclass(slots=True)
class Bundle:
    manifest: Manifest
    rules: list[Rule]
    index: RuleIndex
    registry: Registry
    lineage: dict[str, list[str]] = field(default_factory=dict)
    """rule id -> the rules it restates. Drives the independence factor: three
    paraphrases of one verse are one piece of evidence, not three."""

    denied: frozenset[str] = frozenset()
    """Kill switch. A rule id here is skipped at query time without a rebuild or
    a deploy. You will need this at three in the morning at least once."""

    # -- construction ------------------------------------------------------

    @classmethod
    def build(
        cls,
        rules: Iterable[Rule],
        registry: Registry,
        index: Optional[RuleIndex] = None,
        *,
        built_at: Optional[datetime] = None,
    ) -> "Bundle":
        rules = list(rules)
        index = index if index is not None else RuleIndex.build(rules, registry)
        lineage = {
            r.rule_id: list(r.provenance.restates)
            for r in rules
            if r.provenance.restates
        }
        manifest = Manifest(
            bundle_id=cls._content_hash(rules, registry),
            format=BUNDLE_FORMAT,
            frame_version=FRAME_VERSION,
            registry_version=registry.version,
            registry_fingerprint=registry.fingerprint(),
            rule_count=len(rules),
            derivation_count=sum(
                1 for r in rules if r.assertion is AssertionKind.DERIVE_FACT
            ),
            variant_count=len(index.variants),
            atom_count=len(index.table),
            built_at=(built_at or datetime.now(timezone.utc)).isoformat(),
            source_books=sorted({r.provenance.book_id for r in rules if r.provenance.book_id}),
        )
        return cls(
            manifest=manifest, rules=rules, index=index,
            registry=registry, lineage=lineage,
        )

    @staticmethod
    def _content_hash(rules: Iterable[Rule], registry: Registry) -> str:
        """Identity is the corpus, not the clock.

        Rebuilding an unchanged corpus must produce the same id, or every build
        looks like a change and a real change stops being visible.
        """
        parts = [f"frame:{FRAME_VERSION}", f"registry:{registry.fingerprint()}"]
        for rule in sorted(rules, key=lambda r: r.rule_id):
            parts.append(f"{rule.rule_id}@{rule.version}#{rule.content_hash()}")
        digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
        return f"kb-{digest[:16]}"

    # -- serialisation -----------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "atoms": list(self.index.table.names()),
            "rules": [r.model_dump(mode="json") for r in self.rules],
            "variants": [
                {
                    "variant_id": v.variant_id,
                    "rule_id": v.rule_id,
                    "core": sorted(v.core),
                    "always": v.always,
                    "domains": {d: v.domains[d] for d in sorted(v.domains)},
                    "school": v.school,
                    "status": v.status,
                }
                for v in self.index.variants
            ],
            "lineage": self.lineage,
        }

    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(blob)
        return path

    @classmethod
    def load(cls, path: Path | str, registry: Registry) -> "Bundle":
        with gzip.open(Path(path), "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        return cls.from_payload(payload, registry)

    @classmethod
    def from_payload(cls, payload: dict[str, Any], registry: Registry) -> "Bundle":
        raw = payload["manifest"]
        manifest = Manifest(**raw)

        if manifest.format != BUNDLE_FORMAT:
            raise BundleMismatch(
                f"bundle format {manifest.format}, this build reads {BUNDLE_FORMAT}"
            )
        if manifest.registry_fingerprint != registry.fingerprint():
            raise BundleMismatch(
                f"bundle {manifest.bundle_id} was compiled against registry "
                f"{manifest.registry_fingerprint}, loaded against "
                f"{registry.fingerprint()}. A predicate signature has moved, so "
                f"every rule that used it now means something else."
            )
        if manifest.frame_version != FRAME_VERSION:
            raise BundleMismatch(
                f"bundle frame {manifest.frame_version}, this build is {FRAME_VERSION}"
            )

        from rishivan.koonji.index import Variant

        table = AtomTable(payload["atoms"])
        index = RuleIndex(table=table)
        for raw_variant in payload["variants"]:
            variant = Variant(
                variant_id=raw_variant["variant_id"],
                rule_id=raw_variant["rule_id"],
                core=frozenset(raw_variant["core"]),
                always=raw_variant["always"],
                domains=_variant_domains(raw_variant["domains"]),
                school=raw_variant["school"],
                status=raw_variant["status"],
            )
            index.variants.append(variant)
            if variant.always:
                index.always.add(variant.variant_id)
            for atom_id in variant.core:
                index.postings.setdefault(atom_id, set()).add(variant.variant_id)

        return cls(
            manifest=manifest,
            rules=[Rule.model_validate(r) for r in payload["rules"]],
            index=index,
            registry=registry,
            lineage=payload.get("lineage", {}),
        )

    # -- reads -------------------------------------------------------------

    def rule(self, rule_id: str) -> Optional[Rule]:
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None

    def by_id(self) -> dict[str, Rule]:
        return {r.rule_id: r for r in self.rules}

    def derivations(self) -> list[Rule]:
        return [r for r in self.rules if r.assertion is AssertionKind.DERIVE_FACT]

    def deny(self, *rule_ids: str) -> "Bundle":
        """Disable rules without a rebuild. Hot-reloadable in production."""
        self.denied = frozenset(self.denied | set(rule_ids))
        return self

    def __repr__(self) -> str:
        m = self.manifest
        return (
            f"<Bundle {m.bundle_id} rules={m.rule_count} "
            f"derivations={m.derivation_count} variants={m.variant_count} "
            f"atoms={m.atom_count}>"
        )
