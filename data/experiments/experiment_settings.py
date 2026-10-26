"""이전 CSV 편집 실험의 경로를 현재 data 구조에 연결한다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV_DATA_DIR = ROOT / 'data/processed'
CSV_DEFINE_DIR = ROOT / 'data/definitions'
CSV_FINAL_DIR = ROOT / 'data/experiments/results/csv_standardizer'
SPECS_JSON_PATH = CSV_FINAL_DIR / 'standard_specs.json'
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')


def definition_path(name):
    names = {'KS_NFA_PROCESSED': 'KS_NFA_FINAL_DEFINITION.csv',
             'KS_NFA_PRESCRIPTION': 'KS_NFA_PRESCRIPTION_DEFINITION.csv',
             'KS_NFA_PRESCRIPTION_DETAIL': 'KS_NFA_PRESCRIPTION_DETAIL_DEFINITION.csv'}
    return CSV_DEFINE_DIR / names.get(name, f'{name}_DEFINITION.csv')
