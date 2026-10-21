"""data 프로젝트(전처리 스크립트) 전용 로그 설정을 관리합니다.

루트 로거가 아니라 "data" 로거와 "__main__" 로거에만 핸들러를 붙이므로, dashboard 쪽 로그 설정과 서로 영향을 주지 않습니다.
각 모듈은 `logger = logging.getLogger(__name__)`만 만들면 됩니다.
- import된 모듈: 이름이 "data."으로 시작하므로 "data" 로거 설정을 따릅니다.
- 직접 실행된 파일: 이름이 "__main__"이므로 "__main__" 로거 설정을 따릅니다.
로그 설정은 실행 진입점(main.py나 단독 실행한 모듈)에서 setup_logging()을 한 번만 호출해서 합니다.
로그 파일 이름과 각 줄의 모듈 표시는 data/scripts 기준 하위 폴더를 포함합니다(예: preprocessing.merge_raw_measurements).
"""

import logging
from datetime import datetime
from pathlib import Path

from config import DATA_LOG_DIR, DATA_SCRIPTS_DIR, ROOT_DIR

# 직접 실행한 파일의 로거 이름은 "__main__"이므로 함께 설정한다.
LOGGER_NAMES = ("data", "__main__")

# %(origin)s는 _OriginFilter가 붙이는 "하위폴더.모듈" 이름이다.
# 직접 실행한 파일도 "__main__" 대신 실제 위치로 찍히고, 폴더가 달라 이름이 같은 모듈도 구분된다.
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(origin)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def caller_name(file: str | Path) -> str:
    """파일 경로를 data/scripts 기준 "하위폴더.모듈" 이름으로 바꿉니다. data/scripts 밖의 파일은 파일 이름만 씁니다.

    예: data/scripts/preprocessing/merge_raw_measurements.py → "preprocessing.merge_raw_measurements"
    """
    path = Path(file).resolve()
    try:
        return ".".join(path.relative_to(DATA_SCRIPTS_DIR).with_suffix("").parts)
    except ValueError:
        return path.stem


class _OriginFilter(logging.Filter):
    """로그 레코드에 기록한 파일의 "하위폴더.모듈" 이름(origin)을 붙입니다."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.origin = caller_name(record.pathname)
        return True


def setup_logging(caller: str, log_dir: Path = DATA_LOG_DIR, level: int = logging.INFO) -> Path:
    """"data"·"__main__" 로거가 콘솔과 로그 파일에 같은 내용을 남기도록 설정하고 로그 파일 경로를 반환합니다.

    로그 파일 이름은 `{yyyymmdd}_{hhmmss}_{caller}.log`입니다.
    여러 번 호출하면 이전에 붙인 핸들러를 닫고 새로 설정합니다.

    Args:
        caller: 로그 파일 이름에 들어갈 실행 이름. 단독 실행하는 모듈은 caller_name(__file__)을 넘긴다
            (예: "preprocessing.merge_raw_measurements", "main.all")
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
        # 핸들러에 붙여야 두 로거와 그 하위 로거의 레코드에 모두 적용된다.
        handler.addFilter(_OriginFilter())

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
