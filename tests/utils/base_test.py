"""CI 동작 확인용 placeholder 테스트입니다. 실제 테스트가 추가되면 삭제해도 됩니다."""


def test_addition():
    """정수 덧셈이 동작하는지 확인합니다."""
    assert 1 + 1 == 2


def test_string_concat():
    """한글 문자열을 이어 붙일 수 있는지 확인합니다."""
    assert "국방" + "대시보드" == "국방대시보드"


def test_list_length():
    """리스트 길이를 구할 수 있는지 확인합니다."""
    assert len([1, 2, 3]) == 3
