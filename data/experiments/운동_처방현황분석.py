"""실행: python -m streamlit run data/experiments/운동_처방현황분석.py"""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parents[2] / 'data/processed'


def load_catalog():
    data = pd.read_csv(DATA_DIR/'KS_NFA_PRESCRIPTION_DETAIL.csv',
                       dtype={'PRESCRIPTION_TYPE_ID': 'string', 'PRESCRIPTION': 'string'})
    required = {'PRESCRIPTION_TYPE_ID', 'PRESCRIPTION'}
    if required-set(data.columns):
        raise ValueError('DETAIL 파일에 처방유형번호와 운동명 컬럼이 필요합니다.')
    data = data[list(['PRESCRIPTION_TYPE_ID', 'PRESCRIPTION'])].copy()
    for col in data:
        data[col] = data[col].str.strip()
        if data[col].isna().any() or data[col].eq('').any():
            raise ValueError(f'{col}에 빈 값이 있습니다.')
    if data.PRESCRIPTION_TYPE_ID.duplicated().any():
        raise ValueError('DETAIL의 처방유형번호가 중복되었습니다.')
    return data


def calculate():
    catalog = load_catalog()
    records = pd.read_csv(DATA_DIR/'KS_NFA_PRESCRIPTION.csv', dtype='string')
    required = ['PRESCRIPTION_ID', 'MESURE_ID', 'PRESCRIPTION_TYPE_ID']
    if set(required)-set(records.columns):
        raise ValueError('처방 파일의 필수 식별자 컬럼이 없습니다.')
    for col in required:
        records[col] = records[col].str.strip()
        if records[col].isna().any() or records[col].eq('').any():
            raise ValueError(f'{col}에 빈 값이 있습니다.')
    if records.PRESCRIPTION_ID.duplicated().any():
        raise ValueError('처방식별번호가 중복되었습니다.')
    if records.duplicated(['MESURE_ID', 'PRESCRIPTION_TYPE_ID']).any():
        raise ValueError('같은 측정·운동의 처방이 중복되었습니다. 전처리를 확인하세요.')
    joined = records.merge(catalog, on='PRESCRIPTION_TYPE_ID', how='left', validate='many_to_one', indicator=True)
    if not joined['_merge'].eq('both').all():
        raise ValueError('DETAIL에 없는 처방유형번호가 있습니다.')
    counts = joined.groupby('PRESCRIPTION').agg(
        처방건수=('PRESCRIPTION_ID', 'size'), 처방된측정수=('MESURE_ID', 'nunique')).reset_index()
    # 같은 운동명이 여러 유형번호에 등록된 경우에도 운동명 단위로 합산한다.
    result = catalog[['PRESCRIPTION']].drop_duplicates().merge(counts, on='PRESCRIPTION', how='left')
    result[['처방건수', '처방된측정수']] = result[['처방건수', '처방된측정수']].fillna(0).astype(int)
    total, measurements = len(records), records.MESURE_ID.nunique()
    result['전체처방중구성비(%)'] = result['처방건수']/total*100 if total else float('nan')
    result['처방기록있는측정중포함률(%)'] = result['처방된측정수']/measurements*100 if measurements else float('nan')
    result = result.rename(columns={'PRESCRIPTION': '운동명'}).sort_values(['처방건수', '운동명'], ascending=[False, True]).reset_index(drop=True)
    result = result.sort_values(['처방된측정수', '운동명'], ascending=[False, True]).reset_index(drop=True)
    result.insert(0, '순위', result['처방된측정수'].rank(method='min', ascending=False).astype(int))
    top_names = result.head(10)['운동명']
    result.attrs['상위10개포함측정수'] = joined.loc[joined.PRESCRIPTION.isin(top_names), 'MESURE_ID'].nunique()
    return result, total, measurements


def main():
    st.set_page_config(page_title='측정별 운동처방 현황', layout='wide')
    st.title('어떤 운동이 많이 처방됐을까? · 측정별 운동처방 현황')
    st.caption('운동 목록은 DETAIL, 실제 처방 횟수는 PRESCRIPTION 기록을 연결해 집계합니다. 사람·측정값 정보 파일은 사용하지 않습니다.')
    try:
        data = load_catalog()
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    a, b = st.columns(2)
    a.metric('등록된 처방유형 수', f'{len(data):,}개')
    b.metric('서로 다른 운동명 수', f'{data.PRESCRIPTION.nunique():,}개')
    st.subheader('등록 운동 목록')
    search = st.text_input('운동명 검색')
    selected = data.loc[data.PRESCRIPTION.str.contains(search, regex=False, na=False)] if search else data
    st.write(f'조회된 운동처방 유형: **{len(selected):,}개**')
    st.dataframe(selected.rename(columns={'PRESCRIPTION_TYPE_ID': '처방유형번호', 'PRESCRIPTION': '운동명'}), hide_index=True)
    st.download_button('조회 운동목록 CSV', selected.to_csv(index=False).encode('utf-8-sig'),
                       file_name='운동_종류목록.csv', mime='text/csv')
    # 목록 조회는 DETAIL만으로 가능하며, 실제 횟수 계산에만 처방 기록이 필요하다.
    st.subheader('운동별 실제 처방 횟수·비율')
    try:
        frequencies, total, measurements = calculate()
    except (ValueError, OSError, KeyError) as exc:
        st.warning(f'목록은 조회 가능하지만 처방 빈도를 계산할 수 없습니다: {exc}')
        return
    a, b, c = st.columns(3)
    a.metric('전체 처방 건수(측정별 1건)', f'{measurements:,}건')
    b.metric('처방 기록이 있는 측정', f'{measurements:,}건')
    c.metric('측정당 평균 처방 운동 수', f'{frequencies.처방된측정수.sum()/measurements:.2f}개' if measurements else '계산 불가')
    st.caption('같은 측정번호에 여러 운동이 있어도 전체 처방은 1건입니다. 날짜만으로 묶지 않습니다. 운동 포함률은 해당 운동 포함 측정 수/전체 처방 측정 수×100입니다.')
    frequencies = frequencies[['순위', '운동명', '처방된측정수', '처방기록있는측정중포함률(%)']].rename(columns={'처방된측정수': '처방건수', '처방기록있는측정중포함률(%)': '운동포함률(%)'}).copy()
    filtered = frequencies.loc[frequencies.운동명.str.contains(search, regex=False, na=False)] if search else frequencies
    st.dataframe(filtered.rename(columns={'처방건수': '운동포함_측정건수'}), hide_index=True, width='stretch')
    top = st.slider('그래프에 표시할 상위 운동 수', 5, 50, 20, 5)
    st.bar_chart(filtered.head(top).set_index('운동명')[['처방건수']], horizontal=True, x_label='해당 운동이 포함된 측정 수')
    st.caption('검색하거나 상위 운동만 표시해도 비율의 분모는 전체 처방 측정 수입니다. 측정 중 포함률의 분모는 처방이 있는 측정이며, 여러 운동이 함께 처방되므로 합은 100%를 넘을 수 있습니다.')
    st.subheader('추가 분석 ① 상위 운동에 처방이 집중되는가?')
    top10 = frequencies.head(10)
    top10_count = int(frequencies.attrs['상위10개포함측정수'])
    share = top10_count/measurements*100 if measurements else 0
    st.metric('상위 10개 운동 중 하나 이상 포함된 측정 비율', f'{share:.2f}%' if total else '계산 불가')
    st.write(f'전체 처방 측정 {measurements:,}건 중 {top10_count:,}건에 상위 10개 운동이 하나 이상 포함됩니다. 같은 측정은 한 번만 셉니다.')
    if total:
        composition = pd.DataFrame({'구분': ['상위 10개 중 하나 이상 포함', '상위 10개 모두 미포함'],
                                    '처방건수': [top10_count, measurements-top10_count]}).set_index('구분')
        st.bar_chart(composition)
    st.caption('자주 처방되는 운동에 대한 집중도를 보여주는 기술통계이며, 운동의 효과·적절성에 대한 평가는 아닙니다.')
    st.subheader('추가 분석 ② 등록 운동 중 실제로 사용된 운동은?')
    used = int(frequencies.처방건수.gt(0).sum())
    unused = frequencies.loc[frequencies.처방건수.eq(0), ['운동명']]
    a, b = st.columns(2)
    a.metric('처방 기록이 있는 운동명', f'{used:,}개')
    b.metric('처방 기록이 없는 등록 운동명', f'{len(unused):,}개')
    st.caption('현재 분석에 포함된 처방 데이터 안에서의 사용 여부입니다. 기록이 없다고 불필요한 운동이라는 뜻은 아닙니다.')
    with st.expander('처방 기록이 없는 운동 목록'):
        st.dataframe(unused, hide_index=True)
    st.download_button('운동별 처방 횟수·비율 전체 CSV', frequencies.rename(columns={'처방건수': '운동포함_측정건수'}).to_csv(index=False).encode('utf-8-sig'),
                       file_name='운동_목록별처방현황.csv', mime='text/csv')


if __name__ == '__main__':
    main()
