# dashboard

장병 체력·부상 관리 Streamlit 대시보드입니다. 데이터는 PostgreSQL DB에서 읽고, 후속조치 기록은 같은 DB에 저장합니다.

## 실행

```powershell
python -m streamlit run dashboard/app.py
```

DB 접속 정보는 환경 변수 또는 `dashboard/.env`(형식은 `dashboard/.env.example`)에 둡니다. 둘 다 있으면 환경 변수가 우선합니다. Streamlit Community Cloud에서는 Secrets에 같은 이름으로 넣습니다.

## 폴더와 파일

| 위치 | 역할 | 자세한 설명 |
|---|---|---|
| `app.py` | 앱의 시작점. 페이지 설정, CSS 주입, 사이드바 메뉴, 선택한 화면 실행 | [views/README.md](views/README.md) |
| `router.py` | 화면 등록(`st.Page`)과 URL 경로 | [views/README.md](views/README.md) |
| `db.py` | DB 접속, 조회(`run_query`, 결과 캐시), 쓰기 트랜잭션 | [py/README.md](py/README.md) |
| `style.css` | 전역 CSS | [common/README.md](common/README.md) |
| `views/` | 화면 파일(화면 하나에 `render()` 하나) | [views/README.md](views/README.md) |
| `py/` | 화면이 쓰는 데이터 조회(SQL)·가공·후속조치 기록 저장 | [py/README.md](py/README.md) |
| `common/` | 여러 화면이 함께 쓰는 CSS 주입, 색상·차트 스타일, 카드 필터, 상수, 위젯 | [common/README.md](common/README.md) |
| `static/` | 브라우저가 직접 받는 정적 파일(홈 지도의 시·도 경계 GeoJSON). `app/static/<파일명>`으로 제공됩니다(`.streamlit/config.toml`의 `enableStaticServing`). | - |
| `img/` | 아이콘 SVG와 그 base64 묶음(`base64.json`, `img2base64.py`로 생성) | - |
