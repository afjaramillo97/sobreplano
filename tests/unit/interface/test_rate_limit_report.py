"""Unit tests for the rate limit report: ranking, top ten and who went over the limit."""

from sobreplano.domain.rate_limit import ClientUsage
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.api.rate_limit import limits_from
from sobreplano.interface.cli.rate_limit_report import format_report

LIMITS = limits_from(Settings(database_url="postgresql+psycopg://unused@127.0.0.1:1/unused"))


def usage(
    bucket: str, key: str, requests: int, peak_minute: int = 1, peak_day: int = 1
) -> ClientUsage:
    return ClientUsage(bucket, key, requests, peak_minute, peak_day)


def test_clients_are_ranked_by_requests_and_cut_to_ten() -> None:
    usages = [usage("list", f"{i:032x}", requests=i) for i in range(1, 13)]
    lines = format_report(usages, LIMITS).splitlines()
    list_lines = lines[1:11]
    assert [int(line.split()[1]) for line in list_lines] == list(range(12, 2, -1))
    assert lines[0].startswith("list (limit 30/min, 600/day): 12 clients, 0 over the limit")


def test_a_client_over_the_minute_or_the_day_limit_is_flagged() -> None:
    usages = [
        usage("detail", "a" * 32, requests=41, peak_minute=5, peak_day=41),  # over the day
        usage("detail", "b" * 32, requests=11, peak_minute=11, peak_day=11),  # over the minute
        usage("detail", "c" * 32, requests=40, peak_minute=10, peak_day=40),  # at the limit
    ]
    report = format_report(usages, LIMITS)
    assert "detail (limit 10/min, 40/day): 3 clients, 2 over the limit" in report
    assert "aaaaaaaa      41 requests  peak 5/min  41/day  OVER" in report
    assert "cccccccc      40 requests  peak 10/min  40/day\n" in report + "\n"


def test_only_the_short_key_is_printed() -> None:
    report = format_report([usage("advisor", "f" * 32, requests=1)], LIMITS)
    assert "f" * 9 not in report
    assert "advisor (limit 5/min, 30/day): 1 clients, 0 over the limit" in report
