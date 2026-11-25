"""The API contract in web/ matches the code: a changed API needs export_openapi run again."""

from sobreplano.interface.cli.export_openapi import CONTRACT_PATH, main, render_contract


def test_the_contract_in_the_repo_matches_the_code() -> None:
    assert CONTRACT_PATH.exists(), "run: uv run python -m sobreplano.interface.cli.export_openapi"
    assert CONTRACT_PATH.read_text(encoding="utf-8") == render_contract(), (
        "the API changed; run: uv run python -m sobreplano.interface.cli.export_openapi"
    )


def test_check_exits_zero_when_the_contract_is_current() -> None:
    assert main(["--check"]) == 0


def test_the_contract_is_stable_text() -> None:
    # Two renders are byte for byte equal, so the snapshot never flips on key order.
    assert render_contract() == render_contract()
    assert render_contract().endswith("}\n")
