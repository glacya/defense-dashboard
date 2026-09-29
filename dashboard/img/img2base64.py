import base64
import json
import os
from pathlib import Path
# 위 파일은 아래와 같이 동작합니다.
"""
1. 아래의 img_name에 추가할 이미지이름을 입력합니다.
2. 경로 img폴더내에 img_name을 가진 이미지파일이 존재하여야 합니다.
3. 아래의 함수를 실행하여 이미지를 base64.json에 저장합니다.(이미지는 github에 올릴 필요 없습니다.)

위 파일은 다음을 위해 동작합니다.
1. streamlit에서 내부경로 이미지를 사용하기 위해서는 base64형식으로 바꾸어야합니다.
2. app에서의 동작을 최소한으로 줄이기 위하여 미리 전처리 된 base64형식을 사용합니다.
3. 사용할 이미지들을 정리하고 이름을 부여하여 쉽게 꺼낼 수 있도록 합니다. 
"""

def get_image_base64(image_path):
  with open(image_path, "rb") as img_file:
    return base64.b64encode(img_file.read()).decode()
ROOT = Path(__file__).resolve().parent

img_name = "bg_img"
img = img_name + ".png"
img_path = str(Path(ROOT)/img) 
base64_str = get_image_base64(img_path)
base64_path = str(Path(ROOT)/"base64.json")

# 1. 기존 JSON 파일이 있으면 불러오고, 없으면 빈 딕셔너리 생성
data = {}
if os.path.exists(base64_path):
  with open(base64_path, "r", encoding="utf-8") as f:
    try:
      data = json.load(f)
    except json.JSONDecodeError:
      data = {}

# 2. Key-Value 형태로 데이터 추가
data[img_name] = base64_str

# 3. JSON 파일에 덮어쓰기 저장
with open(base64_path, "w", encoding="utf-8") as f:
  json.dump(data, f, ensure_ascii=False, indent=4)