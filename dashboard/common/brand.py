"""사이드바 상단 브랜드(로고 + 문구)입니다. 크기와 색은 인라인 스타일로 지정해 CSS 선택자에 의존하지 않습니다."""

BRAND_TITLE = "국방 체력 대시보드"
BRAND_SUB = "대한민국 국군 체력관리 시스템"

BRAND_SVG = (
    '<svg width="28" height="28" viewBox="-3 -1 32 32" fill="none" aria-hidden="true" '
    'style="display:block;">'
    '<g stroke="#C9D6EA" stroke-width="1.2" stroke-linecap="round" fill="none">'
    '<path d="M-0.5 4 C-3 9 -3 18 2 24"/>'
    '<path d="M-1.6 9.2 l-1.8 0.6 M-2.2 14.5 l-1.8 0.6 M-1.2 19.5 l-1.8 0.5"/>'
    '<path d="M26.5 4 C29 9 29 18 24 24"/>'
    '<path d="M27.6 9.2 l1.8 0.6 M28.2 14.5 l1.8 0.6 M27.2 19.5 l1.8 0.5"/>'
    '</g>'
    '<path d="M13 0 C17 2 21 2.5 24 3 V13 C24 21 19 26 13 28 C7 26 2 21 2 13 V3 C5 2.5 9 2 13 0 Z" '
    'fill="#1B2A44" stroke="#C9D6EA" stroke-width="1.5"/>'
    '<path d="M13 3 C16 4.5 19 5 21 5.3 V13 C21 19 17.5 22.5 13 24.5 C8.5 22.5 5 19 5 13 V5.3 C7 5 10 4.5 13 3 Z" '
    'fill="none" stroke="#7F93B0" stroke-width="1"/>'
    '<polygon points="13,7.5 14.12,10.46 17.28,10.61 14.81,12.59 15.65,15.64 13,13.9 '
    '10.35,15.64 11.19,12.59 8.72,10.61 11.88,10.46" fill="#C9D6EA"/>'
    '</svg>'
)


def brand_html(href: str = "/") -> str:
    """사이드바 브랜드 블록 HTML. 클릭하면 href(기본: 홈)로 이동합니다."""
    return (
        f'<a href="{href}" target="_self" '
        'style="display:flex;align-items:center;gap:9px;'
        'padding:0;text-decoration:none !important;">'
        '<span style="display:block;flex:0 0 auto;width:28px;height:28px;">'
        f'{BRAND_SVG}'
        '</span>'
        '<span style="display:flex;flex-direction:column;min-width:0;">'
        '<span style="display:block;font-size:14px;font-weight:700;line-height:1.2;'
        f'color:#E8ECF4 !important;text-decoration:none !important;">{BRAND_TITLE}</span>'
        '<span style="display:block;margin-top:2px;font-size:10px;line-height:1.3;'
        f'color:#7F8BA0 !important;text-decoration:none !important;">{BRAND_SUB}</span>'
        '</span>'
        '</a>'
    )