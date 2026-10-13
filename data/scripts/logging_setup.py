"""data 프로젝트(전처리 스크립트) 전용 로그 설정을 관리합니다.

루트 로거가 아니라 "data" 로거와 "__main__" 로거에만 핸들러를 붙이므로, dashboard 쪽 로그 설정과 서로 영향을 주지 않습니다.
각 모듈은 `logger = logging.getLogger(__name__)`만 만들면 됩니다.
- import된 모듈: 이름이 "data."으로 시작하므로 "data" 로거 설정을 따릅니다.
- 직접 실행된 파일: 이름이 "__main__"이므로 "__main__" 로거 설정을 따릅니다.
로그 설정은 실행 진입점(main.py나 단독 실행한 모듈)에서 setup_logging()을 한 번만 호출해서 합니다.
"""

import logging
from datetime import datetime
from pathlib import Path

from config import DATA_LOG_DIR, ROOT_DIR

# 직접 실행한 파일의 로거 이름은 "__main__"이므로 함께 설정한다.
LOGGER_NAMES = ("data", "__main__")

# %(module)s는 파일 이름이라, 직접 실행한 파일도 "__main__" 대신 실제 모듈 이름으로 찍힌다.
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(module)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(caller: str, log_dir: Path = DATA_LOG_DIR, level: int = logging.INFO) -> Path:
    """"data"·"__main__" 로거가 콘솔과 로그 파일에 같은 내용을 남기도록 설정하고 로그 파일 경로를 반환합니다.

    로그 파일 이름은 `{yyyymmdd}_{hhmmss}_{caller}.log`입니다.
    여러 번 호출하면 이전에 붙인 핸들러를 닫고 새로 설정합니다.

    Args:
        caller: 로그 파일 이름에 들어갈 실행 모듈 이름 (예: "main")
        log_dir: 로그 파일을 저장할 폴더
        level: 기록할 최소 로그 레벨
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{caller}.log"

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    # 두 로거가 같은 핸들러를 공유해야 같은 파일에 순서대로 기록된다.
    # Windows 기본 인코딩(cp949)으로 저장되지 않도록 파일 인코딩을 지정한다.
    handlers = [logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")]
    for handler in handlers:
        handler.setFormatter(formatter)

    for name in LOGGER_NAMES:
        logger = logging.getLogger(name)
        for old_handler in list(logger.handlers):
            logger.removeHandler(old_handler)
            old_handler.close()
        logger.setLevel(level)
        # 루트 로거로 전달하지 않아야 dashboard 쪽 로그 설정에 섞여 두 번 출력되지 않는다.
        logger.propagate = False
        for handler in handlers:
            logger.addHandler(handler)
    return log_path


def display_path(path: Path) -> str:
    """로그에 남길 경로를 프로젝트 루트 기준 상대 경로로 바꿉니다.

    절대 경로에는 사용자 이름 같은 개인 환경 정보가 들어가므로, 로그를 공유해도 괜찮도록 상대 경로로 남깁니다.
    """
    try:
        return Path(path).resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return str(path)
