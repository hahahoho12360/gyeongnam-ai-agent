import pytest

from scripts.backfill import (
    CORE_HISTORICAL_SOURCES,
    SNAPSHOT_SOURCES,
    chunked,
    resolve_sources,
    scope_token,
    task_key,
)


def test_historical_only_defaults_to_core_history():
    assert resolve_sources(None, historical_only=True, snapshot_only=False, start='2025-09', end='2026-09') == CORE_HISTORICAL_SOURCES


def test_snapshot_requires_single_month():
    with pytest.raises(ValueError):
        resolve_sources(None, historical_only=False, snapshot_only=True, start='2026-09', end='2026-10')


def test_multimonth_rejects_snapshot_even_if_explicit():
    with pytest.raises(ValueError):
        resolve_sources(['population', 'commerce'], historical_only=False, snapshot_only=False, start='2025-09', end='2026-09')


def test_snapshot_defaults():
    assert resolve_sources(None, historical_only=False, snapshot_only=True, start='2026-10', end='2026-10') == SNAPSHOT_SOURCES


def test_chunked_and_scope_are_stable():
    rows=[{'id':str(i)} for i in range(5)]
    assert [len(x) for x in chunked(rows,2)] == [2,2,1]
    assert scope_token(['b','a']) == scope_token(['a','b'])
    assert task_key('abc','population','2026-09') == 'abc:population:2026-09'
