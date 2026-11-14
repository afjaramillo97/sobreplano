"""Unit tests for the extraction golden set: pages file, labels, local cache and S3 sync."""

import io
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sobreplano.domain.errors import ExtractionError
from sobreplano.domain.scraping import ExtractedProject, ExtractedUnitType, ExtractionResult
from sobreplano.evals.extraction import golden
from sobreplano.evals.extraction.golden import (
    ExpectedUnitType,
    ExtractionLabel,
    case_id,
    label_from_extraction,
    load_cache,
    merge_labels,
    read_pages,
    save_cache,
)
from sobreplano.evals.extraction.runner import run_extraction_evals
from sobreplano.evals.report import CostCap
from sobreplano.infrastructure.scraping import extraction_schema


def make_label(
    case: str = "londono-gomez-atlantica", sha: str = "a" * 64, reviewed: bool = True
) -> ExtractionLabel:
    return ExtractionLabel(
        case_id=case,
        url=f"https://example.com/{case}",
        developer="londono-gomez",
        text_sha256=sha,
        reviewed=reviewed,
        name="Atlántica",
        neighborhood=None,
        unit_types=[
            ExpectedUnitType(
                name="Tipo 1",
                price_cop=300_000_000,
                total_area_m2=50.0,
                private_area_m2=None,
                bedrooms=2,
                bathrooms=2,
            )
        ],
    )


def test_pages_file_has_16_urls_8_per_developer() -> None:
    urls = read_pages()
    assert len(urls) == len(set(urls)) == 16
    assert sum("londonogomez.com" in url for url in urls) == 8
    assert sum("constructoracapital.com" in url for url in urls) == 8


def test_read_pages_skips_comments_and_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "pages.txt"
    path.write_text("# comment\n\nhttps://a.com/x\n  https://a.com/y  \n", encoding="utf-8")
    assert read_pages(path) == ["https://a.com/x", "https://a.com/y"]


def test_case_id() -> None:
    assert (
        case_id("constructora-capital", "https://x.com/proyecto/1/envigado/262/axis/")
        == "constructora-capital-axis"
    )


def test_label_starts_from_the_stored_extraction_unreviewed() -> None:
    stored = extraction_schema.ExtractedProject.model_validate(
        {
            "name": "Axis",
            "neighborhood": "Las Vegas",
            "unit_types": [
                {
                    "name": "Tipo 04",
                    "price_cop": 710_200_000,
                    "total_area_m2": 60.01,
                    "private_area_m2": 54.06,
                    "bedrooms": 1,
                    "bathrooms": 2,
                }
            ],
        }
    )
    label = label_from_extraction(
        "constructora-capital-axis", "https://x", "constructora-capital", "b" * 64, stored
    )
    assert not label.reviewed
    assert label.unit_types[0].model_dump() == stored.unit_types[0].model_dump()


def test_merge_keeps_a_reviewed_label_while_its_text_is_unchanged() -> None:
    reviewed = make_label()
    rebuilt = make_label(reviewed=False)
    changed_text = make_label(sha="c" * 64, reviewed=False)
    assert merge_labels([reviewed], [rebuilt]) == [reviewed]
    assert merge_labels([reviewed], [changed_text]) == [changed_text]
    assert merge_labels([make_label(reviewed=False)], [rebuilt]) == [rebuilt]


def test_cache_round_trip(tmp_path: Path) -> None:
    save_cache([make_label()], {"londono-gomez-atlantica": "TIPO 1 Desde $300.000.000"}, tmp_path)
    labels, texts = load_cache(tmp_path)
    assert labels == [make_label()]
    assert texts == {"londono-gomez-atlantica": "TIPO 1 Desde $300.000.000"}
    assert load_cache(tmp_path / "missing") == ([], {})


class FakeS3:
    """In-memory bucket with the calls push and pull use."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[Key] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": io.BytesIO(self.objects[Key])}

    def get_paginator(self, name: str) -> "FakeS3":
        return self

    def paginate(self, *, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        return [{"Contents": [{"Key": k} for k in sorted(self.objects) if k.startswith(Prefix)]}]


def test_push_then_pull_restores_the_cache(tmp_path: Path) -> None:
    s3 = FakeS3()
    save_cache([make_label()], {"londono-gomez-atlantica": "texto"}, tmp_path / "a")
    assert golden.push(s3, "bucket", tmp_path / "a") == 2  # type: ignore[arg-type]
    assert sorted(s3.objects) == [
        "evals/extraction/v1/labels.json",
        "evals/extraction/v1/texts/londono-gomez-atlantica.txt",
    ]
    assert golden.pull(s3, "bucket", tmp_path / "b") == 2  # type: ignore[arg-type]
    assert load_cache(tmp_path / "b") == load_cache(tmp_path / "a")


class FakeExtractor:
    """Returns the label's own unit types, or fails for the cases told to."""

    model = "openai:gpt-6-luna"
    prompt_version = "6682e7fa8220"

    def __init__(self, failing: set[str] | None = None) -> None:
        self.failing = failing or set()

    def extract(self, page_text: str) -> ExtractionResult:
        if page_text in self.failing:
            raise ExtractionError("answer cut off")
        unit = ExtractedUnitType("Tipo 1", 300_000_000, Decimal("50.0"), None, 2, 2)
        return ExtractionResult(
            model=self.model,
            input_tokens=2000,
            output_tokens=200,
            project=ExtractedProject("Atlántica", None, (unit,)),
            prompt_version=self.prompt_version,
        )


def run(
    labels: list[ExtractionLabel],
    texts: dict[str, str],
    extractor: FakeExtractor,
    cap: str = "1",
    repeat: int = 1,
):  # type: ignore[no-untyped-def]
    return run_extraction_evals(
        labels, texts, extractor, commit=None, repeat=repeat, cost_cap=CostCap(Decimal(cap))
    )


def test_run_scores_every_page_with_cost_and_prompt_version() -> None:
    labels = [make_label("a"), make_label("b")]
    report = run(labels, {"a": "ta", "b": "tb"}, FakeExtractor(), repeat=2)
    assert len(report.pages) == 4
    assert report.metrics().perfect_pages == 4
    # 2000 * 0.10 + 200 * 0.50 per million tokens, 4 calls.
    assert report.usage.cost_usd == Decimal("0.001200")
    assert report.prompt_version == "6682e7fa8220"
    assert report.failures() == []
    assert "Eligible as extractor: **yes**" in report.to_markdown()


def test_failed_page_counts_as_nothing_found() -> None:
    report = run([make_label("a")], {"a": "ta"}, FakeExtractor(failing={"ta"}))
    [page] = report.pages
    assert page.call is None and page.score.error == "answer cut off"
    assert report.failures() == ["unit type recall 0.0% < 95%"]


def test_unreviewed_labels_are_refused() -> None:
    with pytest.raises(ValueError, match="not reviewed"):
        run([make_label(reviewed=False)], {"londono-gomez-atlantica": "t"}, FakeExtractor())


def test_cost_cap_stops_before_the_next_page() -> None:
    report = run(
        [make_label("a"), make_label("b")], {"a": "ta", "b": "tb"}, FakeExtractor(), cap="0.0002"
    )
    assert not report.complete and [p.score.case_id for p in report.pages] == ["a"]
