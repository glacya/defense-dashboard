import pandas as pd
import numpy as np
import oracledb as oci
"""
    csv파일의 이름의 규격은 A_B와 같은 형태일때 컬럼정의서는 A_B_define의 형태.
    
"""
class CSVToOracleFormatter:
    def __init__(self, file_path, type_mapping=None, primary_key_candidate=None):
        """
        Args:
            file_path (str): CSV 파일 경로
            type_mapping (dict): {컬럼명: 'int', 'float', 'str', 'date'} 형태의 목표 타입 딕셔너리
            primary_key_candidate (str): 기본키로 우선 검토할 컬럼명
        """
        self.file_path = file_path
        self.type_mapping = type_mapping or {}
        self.pk_candidate = primary_key_candidate
        self.df = None

    def load_data(self):
        self.df = pd.read_csv(self.file_path)
        return self

    def handle_primary_key(self, pk_col_name='SEQ_ID'):
        """문제 2 해결: 기본키 유효성 검사 또는 순차 번호(서로게이트 키) 부여"""
        if self.pk_candidate and self.pk_candidate in self.df.columns:
            # 유일하고 결측치가 없는지 확인
            is_unique = self.df[self.pk_candidate].is_unique
            has_no_null = self.df[self.pk_candidate].notnull().all()
            
            if is_unique and has_no_null:
                return self

        # 적절한 기본키가 없거나 조건을 만족하지 못할 경우 새로 생성
        if pk_col_name in self.df.columns:
            pk_col_name = f"_{pk_col_name}"
            
        self.df.insert(0, pk_col_name, range(1, len(self.df) + 1))
        return self

    def validate_and_convert_types(self):
        """문제 1 해결: 명시된 규격에 맞게 데이터 타입 강제 변환 및 오류 처리"""
        for col, target_type in self.type_mapping.items():
            if col not in self.df.columns:
                continue
                
            if target_type == 'int':
                # 변환 불가 값은 NaN 처리 후 기본값(0 등) 부여 혹은 Oracle 허용 형태로 조정
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0).astype('int64')
            elif target_type == 'float':
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
            elif target_type == 'str':
                self.df[col] = self.df[col].astype(str).replace(['nan', 'None', 'NAT'], None)
            elif target_type == 'date':
                self.df[col] = pd.to_datetime(self.df[col], errors='coerce')
                
        return self

    def process(self, seq_col_name='SEQ_ID'):
        """전체 규격화 파이프라인 실행"""
        self.load_data()
        self.handle_primary_key(seq_col_name)
        self.validate_and_convert_types()
        return self.df
    
"""# 컬럼 타입 정의
type_rules = {
    'AGE': 'int',
    'SCORE': 'float',
    'NAME': 'str',
    'JOIN_DATE': 'date'
}

# 클래스 인스턴스화 및 실행
formatter = CSVToOracleFormatter(
    file_path='data.csv', 
    type_mapping=type_rules, 
    primary_key_candidate='USER_ID'
)

cleaned_df = formatter.process(seq_col_name='ROW_SEQ_ID')"""