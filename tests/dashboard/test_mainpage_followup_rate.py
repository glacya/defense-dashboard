"""메인 후속조치 완료율 카드를 검증합니다(완료 건수는 DB에서 세므로 가짜 값으로 대체)."""

from dashboard.py import management_store
from dashboard.views import mainpage


def test_completion_rates_use_non_safe_and_injury_denominators(monkeypatch):
    """체력 완료율은 경계1~3등급 인원, 부상 완료율은 부상 건수가 분모인지 확인합니다."""
    monkeypatch.setattr(mainpage.queries, 'load_non_safe_count', lambda threshold: 2)
    monkeypatch.setattr(mainpage, 'load_completion_counts', lambda threshold: {
        'fitness_records': 4, 'fitness_completed': 1, 'injury_records': 1, 'injury_completed': 1})
    rendered = []
    monkeypatch.setattr(mainpage.st, 'markdown', lambda value, **kwargs: rendered.append(value))

    mainpage._render_kpis(3, 4)

    assert '50.0%' in rendered[0] and '25.0%' in rendered[0]
    assert '경계1~3등급 2명 기준 · 안전 제외' in rendered[0]


def test_completion_sql_counts_only_non_safe_soldiers_and_latest_injury_record():
    """완료율 SQL이 확률 기준으로 걸러 세고, 부상은 부상별 최신 기록만 보는지 확인합니다."""
    sql = management_store.COMPLETION_SQL
    assert "failure_probability >= :threshold" in sql and "count(DISTINCT f.soldier_id)" in sql
    assert "DISTINCT ON (injury_id)" in sql and "ORDER BY injury_id, check_date DESC, updated_at DESC" in sql
