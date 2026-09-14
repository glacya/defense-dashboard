import pandas as pd
from pathlib import Path
import re

MEAL_TYPES = ["조식", "중식", "석식", "증특식"]

INPUT_DIR = Path(__file__).parent / "csv_file" / "csv_data" / "military_base_diet"
OUTPUT_DIR = Path(__file__).parent / "csv_file" / "csv_processed" / "military_base_diet"

def normalize_meal(name: str) -> str:
    try:
        # 정규 표현식으로 괄호 제거
        split_name = re.sub(r'\(.*?\)', '', name)
        
        # 이중 괄호의 경우 닫는 소괄호가 남으므로 제거
        if split_name[-1] == ')':
            split_name = split_name[:-1]
        
        # 쉼표로 구별된 값 제거
        return split_name.split(',')[0]
    except:
        return f"Anomaly: {name}"
    

def convert_diet_csv(input_path: Path, output_dir: Path = None):
    """
    [날짜,조식,조식열량,중식,중식열량,석식,석식열량,증특식,증특식열량,열량합계] 형태의
    급식 CSV를 아래 두 개의 CSV로 변환한다.

    1. <이름>_meal.csv    : [날짜, 음식, 식사유형]
    2. <이름>_calorie.csv : [음식, 열량]  (음식별 중복 제거)
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    
    df = df.dropna(subset=['날짜'])

    meal_frames = []
    for meal in MEAL_TYPES:
        calorie_col = f"{meal}열량"
        part = df[["날짜", meal, calorie_col]].rename(
            columns={meal: "음식", calorie_col: "열량"}
        )
        part["식사유형"] = meal
        meal_frames.append(part)

    long_df = pd.concat(meal_frames, ignore_index=True)
    long_df = long_df.dropna(subset=['음식'])
    long_df["음식"] = long_df["음식"].astype(str).str.strip()

    # 1. [날짜, 음식, 식사유형]
    meal_df = long_df[["날짜", "음식", "식사유형"]]
    
    meal_df = meal_df.dropna(subset=['음식'])
    
    meal_df["음식"] = meal_df["음식"].apply(normalize_meal)
    meal_output_path = output_dir / f"{input_path.stem}_meal.csv"
    meal_df.to_csv(meal_output_path, index=False, encoding="utf-8-sig")

    # 2. [음식, 열량] - 음식명 기준 중복 제거
    calorie_df = long_df[["음식", "열량"]].drop_duplicates(subset="음식", keep="first")
    calorie_df["열량"] = (
        calorie_df["열량"].astype(str).str.replace("kcal", "", regex=False).astype(float)
    )
    calorie_df = calorie_df.sort_values("음식").reset_index(drop=True)
    calorie_output_path = output_dir / f"{input_path.stem}_calorie.csv"
    calorie_df.to_csv(calorie_output_path, index=False, encoding="utf-8-sig")

    print(f"[성공] {meal_output_path}")
    print(f"[성공] {calorie_output_path}")

    return meal_df, calorie_df


if __name__ == "__main__":
    for csv_path in INPUT_DIR.glob("*.csv"):
        convert_diet_csv(csv_path, OUTPUT_DIR)
