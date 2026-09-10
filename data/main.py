# pipeline.py
import pandas as pd
import json
from pathlib import Path
from google import genai
from data.test_py_folder.config import DB_DIR,CSV_DIR, CSV_DEFINE_DIR, COMPLETE_DIR, SPECS_JSON_PATH, GEMINI_API_KEY, TEST_DIR
from data.test_py_folder.csv_data_format import ColumnStandardizerPipeline

if __name__ == "__main__":
    pipeline = ColumnStandardizerPipeline(db_name="PLACE_DIABETES")
    

    result_df = pipeline.run_standardization_workflow(
        target_korean_attr="성별", 
        composite_keys=["지역", "성별"]
    )