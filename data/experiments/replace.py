import os
import pandas as pd

def extract_unique_centers(file_prefix, base_dir="./"):
    db_dir = os.path.join(base_dir, "DB")
    define_dir = os.path.join(base_dir, "DB_define")
    
    data_path = os.path.join(db_dir, f"{file_prefix}.csv")
    define_path = os.path.join(define_dir, f"{file_prefix}_define.csv")
    
    if not os.path.exists(data_path) or not os.path.exists(define_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다.\n- 데이터: {data_path}\n- 정의서: {define_path}")
        
    # 쉼표로 나열된 구조이므로 일반 read_csv 대신 파일을 통째로 읽거나 
    # 혹은 정의서가 어떤 형태로 저장되어 있는지에 따라 파싱 방식을 달리해야 합니다.
    # 만약 정의서 파일 자체도 콤마로 구분된 한 줄(또는 여러 줄) 형태라면:
    with open(define_path, 'r', encoding='utf-8-sig') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
        
    # 보통 0번: 컬럼명, 1번: 타입, 2번: 설명, 3번: 항목구분 형태로 저장되어 있다고 가정
    if len(lines) < 3:
        raise ValueError("컬럼 정의서 형식이 올바르지 않습니다. (설명 행을 찾을 수 없습니다)")
        
    col_names = [x.strip() for x in lines[0].split(',')]
    descriptions = [x.strip() for x in lines[2].split(',')] # 3번째 줄이 설명이라고 가정
    
    target_col = None
    # '지역'이라는 정확한 설명을 가진 항목의 인덱스 탐색
    for idx, desc in enumerate(descriptions):
        if desc == '지역' or '지역' in desc:
            if idx < len(col_names):
                target_col = col_names[idx]
                break
                
    if not target_col:
        raise ValueError("컬럼 정의서 설명에서 '지역'에 해당하는 속성을 찾을 수 없습니다.")
        
    # 실제 CSV 데이터 로드
    df = pd.read_csv(data_path)
    
    if target_col not in df.columns:
        raise KeyError(f"CSV 파일에 정의서의 지역 컬럼({target_col})이 존재하지 않습니다.")
        
    unique_centers = df[target_col].dropna().unique().tolist()
    print( target_col, unique_centers)