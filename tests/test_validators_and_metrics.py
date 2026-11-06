import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


from services import evidence_extractor
from services.quality_metrics import (
    calculate_precision,
    calculate_recall,
    meets_precision_target,
    meets_recall_target,
    meets_teacher_time_target,
    teacher_active_time_seconds,
)
from services.validators import is_institutional_email


@pytest.mark.parametrize(
    "email",
    [
        "alumno@unmsm.edu.pe",
        "DOCENTE@UNMSM.EDU.PE",
        "  investigador@unmsm.edu.pe  ",
    ],
)
def test_accepts_exact_unmsm_email_domain(email):
    assert is_institutional_email(email)


@pytest.mark.parametrize(
    "email",
    [
        "alumno@gmail.com",
        "alumno@fisi.unmsm.edu.pe",
        "alumno@unmsm.edu.pe.example.com",
        "@unmsm.edu.pe",
        "alumno@@unmsm.edu.pe",
        "",
        None,
    ],
)
def test_rejects_non_institutional_email(email):
    assert not is_institutional_email(email)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://github.com/arnolCP/skillfisi-unmsm",
            ("arnolCP", "skillfisi-unmsm"),
        ),
        (
            "https://www.github.com/equipo6/proyecto.git/",
            ("equipo6", "proyecto"),
        ),
    ],
)
def test_parses_public_github_repository_url(url, expected):
    assert evidence_extractor.parse_github_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/equipo6/proyecto",
        "https://gitlab.com/equipo6/proyecto",
        "https://github.com.example.com/equipo6/proyecto",
        "https://usuario@github.com/equipo6/proyecto",
        "https://github.com:443/equipo6/proyecto",
        "https://github.com/equipo6/proyecto?tab=readme",
        "https://github.com/equipo6/proyecto#readme",
        "https://github.com/equipo6/proyecto/tree/main",
        "https://github.com/equipo-/proyecto",
        "https://github.com/equipo6/",
    ],
)
def test_rejects_unsafe_or_non_repository_url(url):
    with pytest.raises(HTTPException) as error:
        evidence_extractor.parse_github_url(url)

    assert error.value.status_code == 400


@pytest.mark.parametrize("status_code", [301, 401, 403, 404, 500])
def test_rejects_repository_when_github_does_not_return_200(monkeypatch, status_code):
    response = SimpleNamespace(status_code=status_code)
    monkeypatch.setattr(evidence_extractor.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(HTTPException) as error:
        evidence_extractor.extract_from_github(
            "https://github.com/equipo6/repositorio-inaccesible"
        )

    assert error.value.status_code == 400


def test_rejects_repository_marked_as_private(monkeypatch):
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"private": True, "default_branch": "main"},
    )
    monkeypatch.setattr(evidence_extractor.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(HTTPException, match="público"):
        evidence_extractor.extract_from_github(
            "https://github.com/equipo6/repositorio-privado"
        )


def test_truncates_text_at_llm_security_limit():
    oversized_text = "á" * (evidence_extractor.MAX_CHARS_FOR_LLM + 25)

    result = evidence_extractor.truncate_for_llm(oversized_text)

    assert len(result) == evidence_extractor.MAX_CHARS_FOR_LLM
    assert result == oversized_text[: evidence_extractor.MAX_CHARS_FOR_LLM]


def test_truncates_notebook_evidence_at_llm_security_limit():
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": ["a" * (evidence_extractor.MAX_CHARS_FOR_LLM + 100)],
            }
        ]
    }

    result = evidence_extractor.extract_from_ipynb(
        json.dumps(notebook).encode("utf-8")
    )

    assert len(result) == evidence_extractor.MAX_CHARS_FOR_LLM


def test_calculates_teacher_active_time_in_seconds():
    opened_at = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)
    decision_at = opened_at + timedelta(minutes=4, seconds=30)

    assert teacher_active_time_seconds(opened_at, decision_at) == 270


def test_accepts_teacher_time_at_300_second_boundary():
    opened_at = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)

    assert meets_teacher_time_target(opened_at, opened_at + timedelta(seconds=300))
    assert not meets_teacher_time_target(
        opened_at,
        opened_at + timedelta(seconds=301),
    )


def test_rejects_teacher_decision_before_project_opening():
    opened_at = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="anterior"):
        teacher_active_time_seconds(opened_at, opened_at - timedelta(seconds=1))


def test_calculates_precision_and_recall_formulas():
    assert calculate_precision(85, 15) == pytest.approx(0.85)
    assert calculate_recall(80, 20) == pytest.approx(0.80)


def test_applies_precision_acceptance_threshold():
    assert meets_precision_target(85, 15)
    assert not meets_precision_target(84, 16)


def test_applies_recall_acceptance_threshold():
    assert meets_recall_target(80, 20)
    assert not meets_recall_target(79, 21)


@pytest.mark.parametrize(
    ("metric", "counts"),
    [
        (calculate_precision, (0, 0)),
        (calculate_recall, (0, 0)),
        (calculate_precision, (-1, 1)),
        (calculate_recall, (1, -1)),
        (calculate_precision, (True, 1)),
    ],
)
def test_rejects_invalid_quality_metric_counts(metric, counts):
    with pytest.raises(ValueError):
        metric(*counts)
