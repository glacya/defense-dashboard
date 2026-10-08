# pipeline.py
import pandas as pd
import json
from pathlib import Path
from data.test_py_folder.csv_data_format import ColumnStandardizerPipeline

if __name__ == "__main__":
    pipeline = ColumnStandardizerPipeline(db_name="PLACE_DIABETES")
    

    result_df = pipeline.run_standardization_workflow(
        target_korean_attr="성별", 
        composite_keys=["지역", "성별"]
    )