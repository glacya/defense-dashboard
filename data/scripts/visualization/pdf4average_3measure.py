"""KS_NFA_OUTLIERS.csv 파일을 읽어 전체 회원의 1차, 2차, 3차 측정 평균 변화 추이를
모든 능력치(측정 항목)에 대해 한 페이지(또는 다중 페이지)에 시각화하여 PDF로 출력합니다.
"""

import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from config import PROCESSED_DIR as CSV_DATA_DIR

# ==================== [설정 및 매개변수 영역] ====================
INPUT_PATH = CSV_DATA_DIR / "KS_NFA_FINAL_OUTPUT.csv"                  # 입력 이상치 파일 경로
PDF_OUTPUT_PATH = CSV_DATA_DIR / "KS_NFA_ALL_METRICS_AVERAGE.pdf"   # 출력 PDF 파일 경로

ID_COL = "M_CODE"           # 회원 식별자 컬럼
DATE_COL = "MESURE_DE"      # 측정일 컬럼 (YYYYMMDD)

# 시각화에서 제외할 메타데이터 컬럼
EXCLUDE_COLS = {ID_COL, DATE_COL, "AGE", "SEX", "MESURE_NO", "MVM_PRSCRPTN_CN"}
# ==============================================================

def generate_all_metrics_average_pdf(input_path: Path, output_pdf_path: Path) -> None:
    if not input_path.exists():
        sys.exit(f"{input_path} 파일이 존재하지 않습니다. 이전 단계를 먼저 실행하세요.")

    print(f"데이터 로드 중: {input_path.name}")
    df = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)

    # 날짜 파싱 및 시간순 정렬 준비
    df["_measure_date"] = pd.to_datetime(df[DATE_COL].astype(str), format="%Y%m%d", errors="coerce")
    
    # 회원별로 그룹화하여 3회 측정 데이터가 모두 있는 회원들만 추출
    valid_groups = []
    grouped = df.groupby(ID_COL, sort=False)
    
    for member_id, group in grouped:
        sorted_group = group.sort_values("_measure_date")
        if len(sorted_group) >= 3:
            valid_groups.append(sorted_group.iloc[:3].copy())

    if not valid_groups:
        print("조건에 맞는 3회 측정 회원 데이터가 없습니다.")
        return

    print(f"총 {len(valid_groups):,}명의 유효 회원을 기반으로 전체 평균 산출 중...")

    # 데이터셋 내에서 숫자형으로 변환 가능한 모든 능력치 컬럼 자동 추출
    sample_row = valid_groups[0]
    metric_cols = []
    for col in sample_row.columns:
        if col not in EXCLUDE_COLS and not col.startswith("_"):
            # 숫자형 변환 테스트
            converted = pd.to_numeric(sample_row[col], errors="coerce")
            if converted.notna().any():
                metric_cols.append(col)

    if not metric_cols:
        print("시각화할 수 있는 수치형 능력치 컬럼이 없습니다.")
        return

    # 모든 회원 데이터에 대해 숫자형 변환 적용
    for g in valid_groups:
        for col in metric_cols:
            g[col] = pd.to_numeric(g[col], errors="coerce")

    # 1차, 2차, 3차 측정치별 전체 평균 데이터프레임 생성
    all_first = pd.DataFrame([g.iloc[0][metric_cols] for g in valid_groups])
    all_second = pd.DataFrame([g.iloc[1][metric_cols] for g in valid_groups])
    all_third = pd.DataFrame([g.iloc[2][metric_cols] for g in valid_groups])

    avg_first = all_first.mean()
    avg_second = all_second.mean()
    avg_third = all_third.mean()

    # 한글 폰트 설정 (윈도우: 'Malgun Gothic', 맥: 'AppleGothic')
    plt.rcParams['font.family'] = 'Malgun Gothic'
    plt.rcParams['axes.unicode_minus'] = False

    measure_stages = ["1차 측정", "2차 측정", "3차 측정"]
    n_metrics = len(metric_cols)
    
    # 한 페이지에 너무 많은 그래프가 들어가면 복잡해지므로, 
    # 한 페이지당 최대 4~6개 항목씩 나누거나 모든 항목을 한눈에 볼 수 있도록 동적 분할 또는 단일 페이지 구성
    # 여기서는 한 페이지에 최대 4개씩 서브플롯을 배치하여 멀티페이지 PDF로 구성합니다.
    
    ITEMS_PER_PAGE = 4
    pages_count = (n_metrics + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    with PdfPages(output_pdf_path) as pdf:
        for page_idx in range(pages_count):
            start_idx = page_idx * ITEMS_PER_PAGE
            end_idx = min(start_idx + ITEMS_PER_PAGE, n_metrics)
            page_metrics = metric_cols[start_idx:end_idx]
            n_page_items = len(page_metrics)

            fig, axes = plt.subplots(n_page_items, 1, figsize=(8, 2.8 * n_page_items), sharex=True)
            if n_page_items == 1:
                axes = [axes]

            for idx, metric in enumerate(page_metrics):
                ax = axes[idx]
                avg_values = [avg_first[metric], avg_second[metric], avg_third[metric]]
                
                ax.plot(measure_stages, avg_values, marker='o', linestyle='-', color='#1f77b4', linewidth=2.5, markersize=7)
                ax.set_ylabel(metric, fontsize=10, fontweight='bold')
                ax.grid(True, linestyle='--', alpha=0.6)
                
                # 각 측정 단계별 평균값 텍스트 표기
                for stage, v in zip(measure_stages, avg_values):
                    if pd.notna(v):
                        ax.annotate(f"{v:.2f}", (stage, v), textcoords="offset points", 
                                    xytext=(0, 6), ha='center', fontsize=9, fontweight='bold', color='#333333')

            fig.suptitle(f"전체 회원 능력치별 1차·2차·3차 측정 평균 추이 (페이지 {page_idx+1}/{pages_count})", fontsize=13, fontweight='bold', y=0.98)
            plt.xlabel("측정 단계", fontsize=10, fontweight='bold')
            plt.tight_layout(rect=[0, 0.02, 1, 0.95])
            
            pdf.savefig(fig)
            plt.close(fig)

    print(f"모든 능력치 전체 평균 비교 PDF 출력 완료: {output_pdf_path.resolve()}")


def main() -> None:
    generate_all_metrics_average_pdf(INPUT_PATH, PDF_OUTPUT_PATH)


if __name__ == "__main__":
    main()