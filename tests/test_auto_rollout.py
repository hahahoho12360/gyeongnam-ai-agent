from datetime import date

from scripts.auto_rollout import current_month, previous_month, scope_resume_path


def test_month_helpers():
    d = date(2026, 10, 5)
    assert current_month(d) == '2026-10'
    assert previous_month(d) == '2026-09'


def test_resume_paths_are_scope_specific():
    assert scope_resume_path('changwon', 'historical') == '.rollout-changwon-historical.json'
    assert scope_resume_path('gyeongnam', 'snapshot') == '.rollout-gyeongnam-snapshot.json'
