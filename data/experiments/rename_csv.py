import os
import pandas as pd
import re

folder_path = 'csv_file'
all_dfs = []

# 12개 파일 탐색 및 MONTH 컬럼 추가
for filename in os.listdir(folder_path):
    if filename.lower().endswith('.csv'):
        file_path = os.path.join(folder_path, filename)
        name, ext = os.path.splitext(filename)
        
        # 파일명 끝의 6자리 숫자 추출 (예: 220202)
        match = re.search(r'\d{6}$', name)
        if match:
            date_digits = match.group()
            # 마지막 2자리를 월(Month)로 추출 (예: 02)
            month_val = date_digits[-2:]
            
            # 01~12 범위 내에 있는지 확인
            if month_val in [f"{i:02d}" for i in range(1, 13)]:
                try:
                    # 데이터 로드 (한글 깨짐 방지 cp949/utf-8-sig 선택)
                    df = pd.read_csv(file_path, encoding='utf-8-sig')
                    
                    # 1. MONTH 컬럼을 맨 앞에 추가
                    df.insert(0, 'MONTH', month_val)
                    all_dfs.append(df)
                    print(f"성공: {filename} ➡️ MONTH '{month_val}' 적용 완료")
                except Exception as e:
                    print(f"오류 발생 ({filename}): {e}")

# 12개 데이터 통합 및 센터명(CNTER_NM) 기준 정렬
if all_dfs:
    integrated_df = pd.concat(all_dfs, ignore_index=True)
    
    # CNTER_NM이 동일한 것들끼리 모이도록 나열
    if 'CNTER_NM' in integrated_df.columns:
        integrated_df = integrated_df.sort_values(by=['CNTER_NM', 'MONTH']).reset_index(drop=True)
    
    # 통합 파일 저장 (Oracle SQL Developer 등에서 임포트하기 편리하도록 인코딩 설정)
    output_path = 'integrated_fitness_data1.csv'
    integrated_df.to_csv(output_path, index=False, encoding='cp949')
    print(f"\n🎉 통합 완료! 파일이 생성되었습니다: {output_path}")
else:
    print("조건에 맞는 CSV 파일이 없습니다.")
