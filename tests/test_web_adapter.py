"""Web adapter tests for strict exact input and presentation-safe proof output."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from fractions import Fraction

import pytest
import sympy as sp

from triangle_method import (
    HomogeneousPolynomial,
    ProofDiagnostic,
    ProofResult,
    ProofStatus,
    SolverBackend,
    SquareComponent,
    WeightedComponent,
)
from triangle_method.web_adapter import (
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    WEB_SCHEMA_VERSION,
    WebAdapterInputError,
    handle_request,
    main,
    parse_request_document,
    process_request_document,
)


def _request(
    rows: list[list[str]],
    *,
    degree: int | None = None,
) -> dict[str, object]:
    """Build one valid request dictionary from triangular coefficient strings."""
    return {
        "schema": REQUEST_SCHEMA,
        "schemaVersion": WEB_SCHEMA_VERSION,
        "degree": len(rows) - 1 if degree is None else degree,
        "coefficientRows": rows,
    }


def _rational(record: object) -> Fraction:
    """Decode one JavaScript-safe rational response record for assertions."""
    assert isinstance(record, dict)
    assert set(record) == {"numerator", "denominator"}
    assert isinstance(record["numerator"], str)
    assert isinstance(record["denominator"], str)
    return Fraction(int(record["numerator"]), int(record["denominator"]))


def _rows(records: object) -> tuple[tuple[Fraction, ...], ...]:
    """Decode exact response rows into immutable fractions for arithmetic checks."""
    assert isinstance(records, list)
    return tuple(
        tuple(_rational(coefficient) for coefficient in row) for row in records
    )


def _add_rows(
    left: tuple[tuple[Fraction, ...], ...],
    right: tuple[tuple[Fraction, ...], ...],
) -> tuple[tuple[Fraction, ...], ...]:
    """Add equally shaped exact coefficient rows for certificate assertions."""
    return tuple(
        tuple(a + b for a, b in zip(left_row, right_row, strict=True))
        for left_row, right_row in zip(left, right, strict=True)
    )


def test_proved_response_contains_exact_cauchy_certificate_and_steps() -> None:
    """Expose the motivating quadratic as exact colored components and proof states."""
    response = handle_request(_request([["1"], ["-1", "-1"], ["1", "-1", "1"]]))

    assert response["schema"] == RESPONSE_SCHEMA
    assert response["schemaVersion"] == WEB_SCHEMA_VERSION
    assert response["outcome"] == "PROVED"
    assert response["method"] == "candidate_combination"
    assert response["counterexample"] is None
    assert response["target"] == {
        "degree": 2,
        "coefficientRows": [
            [{"numerator": "1", "denominator": "1"}],
            [
                {"numerator": "-1", "denominator": "1"},
                {"numerator": "-1", "denominator": "1"},
            ],
            [
                {"numerator": "1", "denominator": "1"},
                {"numerator": "-1", "denominator": "1"},
                {"numerator": "1", "denominator": "1"},
            ],
        ],
        "latex": "x^{2} - x y - x z + y^{2} - y z + z^{2} \\ge 0",
    }

    proof = response["proof"]
    assert isinstance(proof, dict)
    assert proof["verified"] is True
    assert proof["residualZero"] is True
    assert proof["identityLatex"].endswith("\\ge 0")
    assert proof["groups"] == [
        {
            "id": "group-1",
            "label": "Cauchy",
            "semanticKind": "cauchy",
            "termIds": ["component-1", "component-2", "component-3"],
        }
    ]

    terms = proof["terms"]
    assert [term["id"] for term in terms] == [
        "component-1",
        "component-2",
        "component-3",
    ]
    assert {term["kind"] for term in terms} == {"square"}
    assert [_rational(term["weight"]) for term in terms] == [
        Fraction(1, 2),
        Fraction(1, 2),
        Fraction(1, 2),
    ]
    assert all(term["expressionLatex"].endswith("^{2}") for term in terms)

    target_rows = _rows(response["target"]["coefficientRows"])
    zero_rows = tuple(
        tuple(Fraction(0) for _ in range(row_index + 1)) for row_index in range(3)
    )
    accumulated = zero_rows
    for term, step in zip(terms, proof["steps"], strict=True):
        accumulated = _add_rows(accumulated, _rows(term["contributionRows"]))
        assert step["componentId"] == term["id"]
        assert _rows(step["accumulatedRows"]) == accumulated
        assert _add_rows(accumulated, _rows(step["remainderRows"])) == target_rows
    assert accumulated == target_rows
    assert all(
        value == 0
        for row in _rows(proof["steps"][-1]["remainderRows"])
        for value in row
    )


def test_zero_input_preserves_the_selected_display_degree() -> None:
    """Keep every requested degree-three position after canonical zero proof handling."""
    response = handle_request(
        _request([["0"], ["0", "0"], ["0", "0", "0"], ["0", "0", "0", "0"]])
    )

    assert response["outcome"] == "PROVED"
    assert response["method"] == "zero"
    assert response["target"]["degree"] == 3
    assert [len(row) for row in response["target"]["coefficientRows"]] == [1, 2, 3, 4]
    assert all(
        _rational(coefficient) == 0
        for row in response["target"]["coefficientRows"]
        for coefficient in row
    )
    assert response["proof"] == {
        "verified": True,
        "residualZero": True,
        "identityLatex": "0 = 0 \\ge 0",
        "terms": [],
        "steps": [],
        "groups": [],
    }


def test_degree_twelve_candidate_combination_returns_an_exact_certificate() -> None:
    """Prove a degree-twelve monomial lift through the configured candidate search."""
    rows = [
        ["1"],
        ["-1", "-1"],
        ["1", "-1", "1"],
        *[["0"] * (row_index + 1) for row_index in range(3, 13)],
    ]

    response = handle_request(_request(rows))

    assert response["outcome"] == "PROVED"
    assert response["method"] == "candidate_combination"
    assert response["target"]["degree"] == 12
    assert [len(row) for row in response["target"]["coefficientRows"]] == list(
        range(1, 14)
    )
    proof = response["proof"]
    assert isinstance(proof, dict)
    assert proof["verified"] is True
    assert proof["residualZero"] is True
    assert len(proof["terms"]) == 3
    assert proof["groups"] == [
        {
            "id": "group-1",
            "label": "Cauchy",
            "semanticKind": "cauchy",
            "termIds": ["component-1", "component-2", "component-3"],
        }
    ]
    assert all(
        value == 0
        for row in _rows(proof["steps"][-1]["remainderRows"])
        for value in row
    )


def test_disproved_response_contains_only_an_exact_negative_witness() -> None:
    """Return the backend's exactly evaluated rational point for a false quadratic."""
    response = handle_request(_request([["1"], ["-4", "0"], ["1", "0", "1"]]))

    assert response["outcome"] == "DISPROVED"
    assert response["method"] == "rational_counterexample"
    assert response["proof"] is None
    counterexample = response["counterexample"]
    assert isinstance(counterexample, dict)
    assert [_rational(value) for value in counterexample["coordinates"]] == [
        Fraction(1, 2),
        Fraction(1, 2),
        Fraction(0),
    ]
    assert _rational(counterexample["value"]) == Fraction(-1, 2)
    assert counterexample["evaluationLatex"].endswith("- \\frac{1}{2} < 0")
    assert response["diagnostics"][-1]["code"] == "counterexample.found"


@pytest.mark.parametrize(
    ("rows", "label", "semantic_kind"),
    [
        ([["1"], ["-2", "0"], ["1", "0", "0"]], "AM-GM", "am_gm"),
        ([["1"], ["2", "0"], ["1", "0", "0"]], "Square", "square"),
        (
            [
                ["1"],
                ["-1", "-1"],
                ["-1", "3", "-1"],
                ["1", "-1", "-1", "1"],
            ],
            "Schur",
            "schur",
        ),
    ],
)
def test_group_labels_require_exact_supported_primitive_shapes(
    rows: list[list[str]],
    label: str,
    semantic_kind: str,
) -> None:
    """Use named labels only for exact binomial-square, generic-square, or Schur forms."""
    response = handle_request(_request(rows))

    assert response["outcome"] == "PROVED"
    proof = response["proof"]
    assert isinstance(proof, dict)
    assert len(proof["groups"]) == 1
    assert proof["groups"][0]["label"] == label
    assert proof["groups"][0]["semanticKind"] == semantic_kind


def test_weighted_difference_triangle_splits_into_cauchy_and_am_gm_groups() -> None:
    """Extract the common Cauchy weight and retain an exact leftover edge square."""
    response = handle_request(_request([["3"], ["-4", "-2"], ["3", "-2", "2"]]))

    assert response["outcome"] == "PROVED"
    proof = response["proof"]
    assert isinstance(proof, dict)
    assert [_rational(term["weight"]) for term in proof["terms"]] == [
        Fraction(1),
        Fraction(1),
        Fraction(1),
        Fraction(1),
    ]
    assert proof["groups"] == [
        {
            "id": "group-1",
            "label": "Cauchy",
            "semanticKind": "cauchy",
            "termIds": ["component-1", "component-2", "component-3"],
        },
        {
            "id": "group-2",
            "label": "AM-GM",
            "semanticKind": "am_gm",
            "termIds": ["component-4"],
        },
    ]
    assert proof["terms"][0]["expressionLatex"] == proof["terms"][3]["expressionLatex"]
    assert [step["componentId"] for step in proof["steps"]] == [
        "component-1",
        "component-2",
        "component-3",
        "component-4",
    ]
    assert all(
        value == 0
        for row in _rows(proof["steps"][-1]["remainderRows"])
        for value in row
    )


def test_weighted_cauchy_split_supports_one_common_monomial_multiplier() -> None:
    """Recognize the same exact split after multiplying every edge square by x."""
    response = handle_request(
        _request(
            [
                ["3"],
                ["-4", "-2"],
                ["3", "-2", "2"],
                ["0", "0", "0", "0"],
            ]
        )
    )

    assert response["outcome"] == "PROVED"
    proof = response["proof"]
    assert isinstance(proof, dict)
    assert [group["semanticKind"] for group in proof["groups"]] == [
        "cauchy",
        "am_gm",
    ]
    assert all("x" in term["weightedExpressionLatex"] for term in proof["terms"])
    assert all(
        value == 0
        for row in _rows(proof["steps"][-1]["remainderRows"])
        for value in row
    )


def test_cauchy_label_requires_an_exact_unit_difference_triangle() -> None:
    """Keep a scaled near-Cauchy edge labeled as separate AM-GM components."""
    import triangle_method.web_adapter as adapter

    x, y, z = sp.symbols("x y z")
    variables = (x, y, z)
    terms = tuple(
        WeightedComponent(
            weight=weight,
            component=SquareComponent(
                factor=HomogeneousPolynomial.from_expr(
                    factor,
                    variables=variables,
                )
            ),
        )
        for weight, factor in ((1, x - y), (1, x - z), (1, 2 * y - 2 * z))
    )

    presentation = adapter._build_presentation(terms)
    groups = adapter._encode_presentation_groups(presentation.groups)

    assert [group["semanticKind"] for group in groups] == [
        "am_gm",
        "am_gm",
        "am_gm",
    ]
    assert all(len(group["termIds"]) == 1 for group in groups)


def test_unknown_response_excludes_proof_and_counterexample_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map a backend UNKNOWN result without manufacturing certificate or witness data."""
    import triangle_method.web_adapter as adapter

    def return_unknown(target, *, options):
        assert options.combination_limits.backend is SolverBackend.AUTO
        return ProofResult(
            target=target,
            status=ProofStatus.UNKNOWN,
            diagnostics=(
                ProofDiagnostic(
                    code="test.inconclusive",
                    message="The bounded test search was inconclusive.",
                ),
            ),
        )

    monkeypatch.setattr(adapter, "prove", return_unknown)
    response = adapter.handle_request(_request([["1"], ["0", "0"], ["0", "0", "0"]]))

    assert response["outcome"] == "UNKNOWN"
    assert response["method"] is None
    assert response["proof"] is None
    assert response["counterexample"] is None
    assert response["diagnostics"] == [
        {
            "code": "test.inconclusive",
            "message": "The bounded test search was inconclusive.",
        }
    ]


def test_large_and_reducible_rationals_remain_exact_string_records() -> None:
    """Accept 64-digit parts, retain large integers, and reduce fractions exactly."""
    large = "9" * 64
    denominator = "8" * 64
    response = handle_request(
        _request([[large], ["0", "0"], [f"1/{denominator}", "2/4", "0"]])
    )

    target_rows = response["target"]["coefficientRows"]
    assert target_rows[0][0] == {"numerator": large, "denominator": "1"}
    assert target_rows[2][0] == {"numerator": "1", "denominator": denominator}
    assert target_rows[2][1] == {"numerator": "1", "denominator": "2"}


def test_integral_json_numbers_match_the_typescript_contract() -> None:
    """Accept 1.0 and 2.0 because JSON Schema treats them as integer values."""
    request = _request([["1"], ["0", "0"], ["0", "0", "0"]])
    request["schemaVersion"] = 1.0
    request["degree"] = 2.0

    response = handle_request(request)

    assert response["schemaVersion"] == 1
    assert response["target"]["degree"] == 2


def test_split_groups_cover_every_presentation_term_exactly_once() -> None:
    """Partition all split Cauchy and leftover terms into disjoint semantic groups."""
    response = handle_request(_request([["3"], ["-4", "-2"], ["3", "-2", "2"]]))
    proof = response["proof"]
    assert isinstance(proof, dict)

    term_ids = [term["id"] for term in proof["terms"]]
    grouped_ids = [term_id for group in proof["groups"] for term_id in group["termIds"]]

    assert len(grouped_ids) == len(set(grouped_ids))
    assert sorted(grouped_ids) == sorted(term_ids)


def test_missing_presentation_group_fails_before_a_proof_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse to emit a proof when semantic groups omit a split presentation term."""
    import triangle_method.web_adapter as adapter

    build_presentation = adapter._build_presentation

    def omit_last_group(terms):
        presentation = build_presentation(terms)
        return adapter._Presentation(
            terms=presentation.terms,
            groups=presentation.groups[:-1],
        )

    monkeypatch.setattr(adapter, "_build_presentation", omit_last_group)

    with pytest.raises(RuntimeError, match="cover every term exactly once"):
        adapter.handle_request(_request([["3"], ["-4", "-2"], ["3", "-2", "2"]]))


def test_tampered_presentation_weight_fails_exact_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a presentation whose displayed weights no longer reconstruct the target."""
    import triangle_method.web_adapter as adapter

    build_presentation = adapter._build_presentation

    def increase_first_weight(terms):
        presentation = build_presentation(terms)
        changed_terms = list(presentation.terms)
        first = changed_terms[0]
        changed_terms[0] = WeightedComponent(
            weight=first.weight + 1,
            component=first.component,
        )
        return adapter._Presentation(
            terms=tuple(changed_terms),
            groups=presentation.groups,
        )

    monkeypatch.setattr(adapter, "_build_presentation", increase_first_weight)

    with pytest.raises(RuntimeError, match="failed exact certificate verification"):
        adapter.handle_request(_request([["1"], ["-2", "0"], ["1", "0", "0"]]))


def test_mismatched_display_expression_fails_before_identity_emission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require displayed semantic expressions to match verified primitives exactly."""
    import triangle_method.web_adapter as adapter

    monkeypatch.setattr(adapter, "_component_expression", lambda _component: sp.S.Zero)

    with pytest.raises(RuntimeError, match="does not match"):
        adapter.handle_request(_request([["1"], ["-2", "0"], ["1", "0", "0"]]))


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda request: request.update(extra=True), "request.invalid_fields"),
        (lambda request: request.update(schema="other"), "request.unsupported_schema"),
        (
            lambda request: request.update(schemaVersion=True),
            "request.unsupported_version",
        ),
        (
            lambda request: request.update(schemaVersion=2),
            "request.unsupported_version",
        ),
        (
            lambda request: request.update(schemaVersion=1.5),
            "request.unsupported_version",
        ),
        (lambda request: request.update(degree=1), "request.invalid_degree"),
        (lambda request: request.update(degree=13), "request.invalid_degree"),
        (lambda request: request.update(degree=2.5), "request.invalid_degree"),
        (
            lambda request: request.update(coefficientRows=[["1"]]),
            "request.invalid_rows",
        ),
        (
            lambda request: request["coefficientRows"].__setitem__(1, ["0"]),
            "request.invalid_rows",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(0, "1.0"),
            "request.invalid_coefficient",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(0, 1),
            "request.invalid_coefficient",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(0, " 1"),
            "request.invalid_coefficient",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(0, "01"),
            "request.invalid_coefficient",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(0, "+1"),
            "request.invalid_coefficient",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(0, "-0"),
            "request.invalid_coefficient",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(0, "1" * 65),
            "request.invalid_coefficient",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(
                0, f"1/{'1' * 65}"
            ),
            "request.invalid_coefficient",
        ),
        (
            lambda request: request["coefficientRows"][0].__setitem__(0, "1/0"),
            "request.invalid_coefficient",
        ),
    ],
)
def test_request_validation_rejects_malformed_contracts(mutation, code: str) -> None:
    """Reject schema, shape, degree, and inexact coefficient errors with stable codes."""
    request = _request([["1"], ["0", "0"], ["0", "0", "0"]])
    mutation(request)

    with pytest.raises(WebAdapterInputError) as captured:
        handle_request(request)

    assert captured.value.code == code


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ("", "request.invalid_json"),
        ("[]", "request.invalid_root"),
        ('{"degree": 2, "degree": 3}', "request.invalid_json"),
        ('{"value": NaN}', "request.invalid_json"),
    ],
)
def test_json_parser_rejects_extensions_and_ambiguous_documents(
    document: str,
    code: str,
) -> None:
    """Reject malformed roots, duplicate keys, and nonstandard numeric constants."""
    with pytest.raises(WebAdapterInputError) as captured:
        parse_request_document(document)

    assert captured.value.code == code


def test_request_document_processing_is_compact_and_deterministic() -> None:
    """Return identical single-document JSON for repeated exact requests."""
    request_document = json.dumps(_request([["1"], ["-2", "0"], ["1", "0", "0"]]))

    first = process_request_document(request_document)
    second = process_request_document(request_document)

    assert first == second
    assert "\n" not in first
    assert json.loads(first)["outcome"] == "PROVED"


def test_main_separates_success_output_from_structured_input_errors() -> None:
    """Use stdout only for a valid response and stderr only for rejected input."""
    valid_input = io.StringIO(
        json.dumps(_request([["1"], ["-2", "0"], ["1", "0", "0"]]))
    )
    valid_output = io.StringIO()
    valid_error = io.StringIO()

    assert main(valid_input, valid_output, valid_error) == 0
    assert json.loads(valid_output.getvalue())["outcome"] == "PROVED"
    assert valid_error.getvalue() == ""

    invalid_output = io.StringIO()
    invalid_error = io.StringIO()
    assert main(io.StringIO("{}"), invalid_output, invalid_error) == 2
    assert invalid_output.getvalue() == ""
    error = json.loads(invalid_error.getvalue())
    assert error["error"]["code"] == "request.invalid_fields"


def test_module_entry_point_processes_one_stdin_document() -> None:
    """Support Node's intended `python -m` subprocess boundary end to end."""
    request_document = json.dumps(_request([["1"], ["-4", "0"], ["1", "0", "1"]]))

    completed = subprocess.run(
        [sys.executable, "-m", "triangle_method.web_adapter"],
        input=request_document,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert json.loads(completed.stdout)["outcome"] == "DISPROVED"
