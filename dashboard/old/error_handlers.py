"""  ==========================================
위 코드는 아래와 같습니다.
1. app을 구동하기 위해 사용되는 함수들의 오류발생을 데코레이터의 형식으로 로그오류를 출력하는 형태로 반환합니다.
위 코드는 다음을 위해 작성되었습니다.  
1. 코드의 오류를 방지합니다.
2. 가시성을 높이기 위해 중복에러를 획일화 합니다.
"""
import logging
from functools import wraps
from typing import Any, Callable, Optional


# ============================================================================
# 로깅 및 데코레이터 설정
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)  # logger 객체 생성

def safe_execution(
    error_message: Optional[str] = None,
    error_type: str = "error",  # "error", "warning", "info"
    reraise: bool = False,
):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                msg = error_message or str(e)
                log_msg = f"[{func.__name__}] {msg} (상세: {e})"

                if error_type == "error":
                    logger.error(log_msg, exc_info=True)
                elif error_type == "warning":
                    logger.warning(log_msg)
                elif error_type == "info":
                    logger.info(log_msg)

                if reraise:
                    raise
                return None

        return wrapper
    return decorator

