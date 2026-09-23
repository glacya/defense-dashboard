# pipeline.py
import pandas as pd
import json
from pathlib import Path
from google import genai
from data.test_py_folder.config import CSV_DATA_DIR ,CSV_DEFINE_DIR, CSV_FINAL_DIR, SPECS_JSON_PATH, GEMINI_API_KEY

class ColumnStandardizerPipeline:
    def __init__(self, db_name):
        self.db_name = db_name
        self.define_dir = CSV_DEFINE_DIR
        self.data_dir = CSV_DATA_DIR
        self.complete_dir = CSV_FINAL_DIR
        self.specs_path = SPECS_JSON_PATH
        
        self.define_path = self.define_dir / f"{db_name}_define.csv"
        self.data_path = self.data_dir / f"{db_name}.csv"
        
        self.df_define = None
        self.df_data = None
        
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def load_standard_specs(self, target_korean_attr):
        """
        standard_specs.json 파일에서 현재 db_name과 target_korean_attr에 해당하는 규격 리스트를 로드
        """
        if not self.specs_path.exists():
            print(f"[경고] 표준 규격 파일({self.specs_path})을 찾을 수 없습니다.")
            return None
            
        try:
            with open(self.specs_path, 'r', encoding='utf-8-sig') as f:
                specs_data = json.load(f)
                
            if self.db_name in specs_data and target_korean_attr in specs_data[self.db_name]:
                stand_data = specs_data[self.db_name][target_korean_attr]
                print(f"[정보] JSON 파일에서 [{target_korean_attr}]의 표준 규격을 불러왔습니다: {stand_data}")
                return stand_data
            else:
                print(f"[정보] JSON 파일에 [{self.db_name} -> {target_korean_attr}] 규격이 정의되어 있지 않습니다.")
                return None
                
        except Exception as e:
            print(f"[오류] 표준 규격 JSON 파일 읽기 실패: {e}")
            return None

    def validate_and_load_files(self):
        missing_files = []
        if not self.define_path.exists():
            missing_files.append(str(self.define_path))
        if not self.data_path.exists():
            missing_files.append(str(self.data_path))
            
        if missing_files:
            print(f"찾지 못한 파일 이름을 출력합니다:\n- " + "\n- ".join(missing_files))
            return False
            
        try:
            self.df_define = pd.read_csv(self.define_path, encoding='utf-8-sig')
            self.df_data = pd.read_csv(self.data_path, encoding='utf-8-sig')
        except Exception as e:
            with open(self.define_path, 'r', encoding='utf-8-sig') as f:
                lines = [line.strip().split(',') for line in f if line.strip()]
            self.df_define = pd.DataFrame(lines[1:], columns=lines[0]) if len(lines) > 1 else pd.DataFrame(lines)
            self.df_data = pd.read_csv(self.data_path, encoding='utf-8-sig')
            
        return True

    def generate_ai_mapping(self, not_stand_data, stand_data):
        if not not_stand_data:
            return []

        prompt = f"""
        당신은 데이터 정제 전문가입니다.
        아래 [비표준 데이터] 리스트의 각 항목을 [표준 데이터] 리스트 중 가장 의미가 일치하는 곳으로 매핑해주세요.
        
        [비표준 데이터]: {not_stand_data}
        [표준 데이터]: {stand_data}
        
        반드시 부가 설명 없이 아래의 JSON 배열 형식으로만 답변을 출력하세요.
        [
            {{"from": "비표준항목1", "to": "표준항목1"}},
            {{"from": "비표준항목2", "to": "표준항목2"}}
        ]
        """

        import time
        max_retries = 3
        delay = 2

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=prompt,
                )
                ai_response_text = response.text
                print(" 정렬기준 표입니다 ",ai_response_text)
                clean_text = ai_response_text.replace("```json", "").replace("```", "").strip()
                return json.loads(clean_text)
            except Exception as e:
                print(f"[Gemini API 경고] 시도 {attempt + 1}/{max_retries} 실패: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2  # 지연 시간 증가 (Exponential Backoff)
                else:
                    print(f"[Gemini API 오류] 최대 재시도 횟수를 초과했습니다.")
                    return []

    def run_standardization_workflow(self, target_korean_attr, stand_data=None, composite_keys=None):
        if not self.validate_and_load_files():
            return None

        if stand_data is None:
            stand_data = self.load_standard_specs(target_korean_attr)
            if not stand_data:
                print(f"[오류] [{target_korean_attr}]에 대한 표준 규격 데이터가 없습니다. 직접 stand_data를 입력하거나 JSON을 확인하세요.")
                return None

        self.df_define.columns = self.df_define.columns.str.strip()
        match_col = None
        
        if '컬럼한글명' in self.df_define.columns and '영문속성명' in self.df_define.columns:
            matched_rows = self.df_define[
                self.df_define['컬럼한글명'].astype(str).str.contains(target_korean_attr, na=False)
            ]
            if not matched_rows.empty:
                match_col = str(matched_rows.iloc[0]['영문속성명']).strip()
        else:
            print(f"[오류] 컬럼 정의서에 '컬럼한글명' 또는 '영문속성명' 열이 없습니다.")
            return None

        if not match_col or match_col not in self.df_data.columns:
            print(f"속성 [{target_korean_attr}]을(를) 찾지 못했거나, 데이터셋에 [{match_col}] 컬럼이 없습니다.")
            return None

        current_unique_values = self.df_data[match_col].dropna().unique().tolist()
        not_stand_data = [val for val in current_unique_values if val not in stand_data]

        print(f"\n[탐지된 영문 속성명]: {match_col}")
        print(f"[정상 규격 리스트]: {stand_data}")
        print(f"[규격 외 데이터 리스트]: {not_stand_data}")

        change2stand4data = self.generate_ai_mapping(not_stand_data, stand_data)
        print(f"[생성된 변환 룰 리스트]: {change2stand4data}")

        mapping_dict = {item['from']: item['to'] for item in change2stand4data}
        self.df_data[match_col] = self.df_data[match_col].replace(mapping_dict)

        groupby_cols = [match_col]
        if composite_keys:
            for key in composite_keys:
                target_col = key
                # 만약 입력한 키가 데이터프레임에 없다면, 한글명으로 보고 정의서에서 영문명을 찾음
                if key not in self.df_data.columns:
                    matched_rows = self.df_define[
                        self.df_define['컬럼한글명'].astype(str).str.contains(key, na=False)
                    ]
                    if not matched_rows.empty:
                        target_col = str(matched_rows.iloc[0]['영문속성명']).strip()
                
                if target_col in self.df_data.columns and target_col not in groupby_cols:
                    groupby_cols.append(target_col)

        print(f"[정보] 적용된 그룹화 복합키 기준: {groupby_cols}")

        group_cols = [col for col in self.df_data.columns if col not in groupby_cols]
        if group_cols:
            agg_dict = {col: 'sum' if pd.api.types.is_numeric_dtype(self.df_data[col]) else 'first' for col in group_cols}
            merged_df = self.df_data.groupby(groupby_cols, as_index=False).agg(agg_dict)
        else:
            merged_df = self.df_data

        print("\n[병합 및 정제 완료된 데이터셋 미리보기]:")
        print(merged_df)
        
        output_path = self.complete_dir / f"{self.db_name}_completed.csv"
        merged_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"\n[성공] 완성된 파일이 저장되었습니다: {output_path}")
        
        return merged_df

    def save_spec_to_json(self, target_korean_attr: str, stand_data: list):
        """
        standard_specs.json 파일에 특정 속성과 표준 규격 리스트를 추가/업데이트하는 함수
        """
        specs_data = {}
        
        if self.specs_path.exists():
            try:
                with open(self.specs_path, 'r', encoding='utf-8-sig') as f:
                    specs_data = json.load(f)
            except Exception as e:
                print(f"[경고] 기존 JSON 파일을 읽는 중 오류 발생, 새로 작성합니다: {e}")
        
        if self.db_name not in specs_data:
            specs_data[self.db_name] = {}
            
        specs_data[self.db_name][target_korean_attr] = stand_data
        
        try:
            with open(self.specs_path, 'w', encoding='utf-8-sig') as f:
                json.dump(specs_data, f, ensure_ascii=False, indent=4)
            print(f"[성공] 규격 정보가 [{self.specs_path}]에 저장되었습니다.")
            print(f"- DB: {self.db_name} | 속성: {target_korean_attr} | 규격: {stand_data}")
        except Exception as e:
            print(f"[오류] JSON 파일 저장 실패: {e}")

if __name__ == "__main__":
    pipeline = ColumnStandardizerPipeline(db_name="PLACE_DIABETES")
    result_df = pipeline.run_standardization_workflow(target_korean_attr="지역", stand_data=["경기도", "충청도"])