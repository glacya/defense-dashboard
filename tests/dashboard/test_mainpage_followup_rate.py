"""메인 체력 후속조치 완료율의 안전 인원 제외를 검증합니다."""

import pandas as pd

from dashboard.views import mainpage


def test_completion_excludes_safe_and_outside_population(monkeypatch):
    """안전 인원의 완료 기록은 분자에서, 안전·조회 외 인원은 분모에서 제외합니다."""
    monkeypatch.setattr(mainpage, 'load_probabilities', lambda: pd.DataFrame({
        'SOLDIER_ID': ['safe', 'risk1', 'risk2', 'outside'],
        'RISK_LEVEL': ['안전', '경계1등급', '경계3등급', '경계2등급'],
    }))
    records = pd.DataFrame({'SOLDIER_ID': ['safe', 'risk1', 'risk1', 'outside'],
                            'STATUS': ['완료'] * 4})
    monkeypatch.setattr(mainpage, 'load_records', lambda kind: records if kind == 'followup_records' else pd.DataFrame())
    rendered = []
    monkeypatch.setattr(mainpage.st, 'markdown', lambda value, **kwargs: rendered.append(value))
    latest = pd.DataFrame({'SOLDIER_ID': ['safe', 'risk1', 'risk2']})
    injuries = pd.DataFrame(columns=['SOLDIER_ID', 'INJURY_ID'])
    mainpage._render_kpis(3, 1, latest, injuries)
    assert '50.0%' in rendered[0]
    assert '경계1~3등급 2명 기준 · 안전 제외' in rendered[0]
