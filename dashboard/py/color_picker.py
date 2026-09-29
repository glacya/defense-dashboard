"""  ==========================================
위 코드는 아래와 같습니다.
1. app에서 사용할 css의 색깔을 변결할 수 있습니다.

위 코드는 다음을 위해 작성되었습니다.  
1. 정의된 css파일의 색상을 불러오고 app.py에서 사용할 색상들을 빠르게 변경할 수 있습니다..
================== """
from pathlib import Path
import re
import math
import colorsys
import tkinter as tk
from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent


TARGET_CSS = Path(
    "C:/Users/user/AI/Python_ex/defense-dashboard/dashboard/style.css"
)


def load_css_colors(css_path: Path) -> dict[str, str]:
    """style.css의 :root에 정의된 --color-* 변수들을 읽어옵니다."""
    colors = {}
    if not css_path.exists():
        return colors

    with open(css_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"(--color-[\w-]+):\s*([^;]+);"
    matches = re.findall(pattern, content)

    for key, val in matches:
        colors[key] = val.strip()

    return colors


def update_css_color(css_var_name: str, new_color: str):
    """style.css 파일 내 특정 CSS 변수 값을 수정합니다."""
    try:
        with open(TARGET_CSS, "r", encoding="utf-8") as f:
            content = f.read()

        pattern = rf"({re.escape(css_var_name)}\s*:\s*)(#[0-9a-fA-F]{{6}})(;)"
        if re.search(pattern, content):
            modified_content = re.sub(pattern, rf"\1{new_color}\3", content)

            with open(TARGET_CSS, "w", encoding="utf-8") as f:
                f.write(modified_content)
            print(f" 성공: {TARGET_CSS.name} 내 {css_var_name} 값을 {new_color}로 수정했습니다.")
        else:
            print(f"⚠️ 경고: {TARGET_CSS.name} 내에서 {css_var_name} 변수를 찾지 못했습니다.")

    except Exception as e:
        print(f"❌ 파일 수정 중 오류 발생: {e}")


class CircularColorPicker(tk.Toplevel):
    """OS 기본 컬러 피커를 대체할 커스텀 원형 컬러 팝업 창"""
    def __init__(self, parent, initial_color="#ffffff", title="Choose Color"):
        super().__init__(parent)
        self.title(title)
        self.geometry("260x360")
        self.resizable(False, False)
        self.transient(parent)  # 부모 창 위에 띄우기
        self.grab_set()         # 모달 창 설정 (다른 창 클릭 방지)

        self.confirmed = False
        self.result_color = initial_color
        self.hue = 0.0
        self.sat = 0.0
        self.val = 1.0

        self._hex_to_hsv(initial_color)

        # 1. 캔버스 생성
        self.canvas_size = 200
        self.canvas = tk.Canvas(self, width=self.canvas_size, height=self.canvas_size, cursor="crosshair")
        self.canvas.pack(pady=10)

        # 2. 원형 스펙트럼 휠 이미지 생성 및 배치
        self.wheel_img = self._create_color_wheel(self.canvas_size)
        self.wheel_photo = ImageTk.PhotoImage(self.wheel_img)
        self.canvas.create_image(self.canvas_size//2, self.canvas_size//2, image=self.wheel_photo)

        # 3. 색상 선택자(흰색 링) 생성
        self.selector = self.canvas.create_oval(0, 0, 0, 0, outline="white", width=2)
        self._update_selector_pos()

        # 4. 마우스 클릭 및 드래그 이벤트 바인딩
        self.canvas.bind("<Button-1>", self._on_wheel_click)
        self.canvas.bind("<B1-Motion>", self._on_wheel_click)

        # 5. 밝기(명도) 조절 슬라이더 생성
        self.val_slider = tk.Scale(self, from_=0, to=100, orient="horizontal", label="밝기 (Value)", command=self._on_slider_move)
        self.val_slider.set(int(self.val * 100))
        self.val_slider.pack(fill="x", padx=20)

        # 6. 하단 미리보기 및 버튼 프레임
        bottom_frame = tk.Frame(self)
        bottom_frame.pack(pady=10)

        self.preview = tk.Label(bottom_frame, width=4, bg=initial_color, relief="solid", bd=1)
        self.preview.pack(side="left", padx=10)

        tk.Button(bottom_frame, text="확인", command=self._on_ok, width=6).pack(side="left", padx=5)
        tk.Button(bottom_frame, text="취소", command=self._on_cancel, width=6).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _hex_to_hsv(self, hex_color):
        hex_color = hex_color.strip().lstrip('#')
        if len(hex_color) != 6:
            hex_color = 'ffffff'
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        self.hue, self.sat, self.val = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)

    def _hsv_to_hex(self, h, s, v):
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def _create_color_wheel(self, size):
        """Pillow를 사용해 원형 무지개 그라데이션 이미지를 즉석 생성"""
        img = Image.new("RGB", (size, size), (240, 240, 240))
        pixels = img.load()
        center, radius = size / 2, size / 2
        for x in range(size):
            for y in range(size):
                dx, dy = x - center, y - center
                dist = math.hypot(dx, dy)
                if dist <= radius:
                    angle = math.atan2(dy, dx)
                    h = (angle / (2 * math.pi)) % 1.0
                    s = dist / radius
                    r, g, b = colorsys.hsv_to_rgb(h, s, 1.0)
                    pixels[x, y] = (int(r*255), int(g*255), int(b*255))
        return img

    def _update_selector_pos(self):
        center = self.canvas_size / 2
        radius = (self.canvas_size / 2) * self.sat
        angle = self.hue * 2 * math.pi
        x = center + radius * math.cos(angle)
        y = center + radius * math.sin(angle)
        r = 5
        self.canvas.coords(self.selector, x-r, y-r, x+r, y+r)

    def _on_wheel_click(self, event):
        center = self.canvas_size / 2
        dx, dy = event.x - center, event.y - center
        dist = math.hypot(dx, dy)
        radius = self.canvas_size / 2

        # 캔버스 밖으로 마우스가 나가도 원 안쪽 테두리로 고정
        if dist > radius:
            dx, dy = dx * (radius / dist), dy * (radius / dist)
            dist = radius

        angle = math.atan2(dy, dx)
        self.hue = (angle / (2 * math.pi)) % 1.0
        self.sat = dist / radius

        self._update_color()
        self._update_selector_pos()

    def _on_slider_move(self, val):
        self.val = float(val) / 100.0
        self._update_color()

    def _update_color(self):
        hex_color = self._hsv_to_hex(self.hue, self.sat, self.val)
        self.preview.config(bg=hex_color)
        self.result_color = hex_color

    def _on_ok(self):
        self.confirmed = True
        self.destroy()

    def _on_cancel(self):
        self.destroy()


def pick_color(css_var_name: str, button: tk.Button):
    """사각 버튼을 눌렀을 때 커스텀 원형 스펙트럼을 호출합니다."""
    current_colors = load_css_colors(TARGET_CSS)
    print(current_colors )
    initial_color = current_colors.get(css_var_name, "#ffffff")

    # ❗ OS 컬러 피커 대신 위에서 만든 '커스텀 원형 팝업 창' 호출
    picker = CircularColorPicker(root, initial_color=initial_color, title=f"{css_var_name} 선택")
    root.wait_window(picker)

    # 확인 버튼을 눌렀을 때만 색상 업데이트 적용
    if picker.confirmed:
        new_color = picker.result_color
        button.config(bg=new_color)
        update_css_color(css_var_name, new_color)


# --------------------------
# 메인 UI 구성 (사각 버튼 유지)
# --------------------------
current_theme = load_css_colors(TARGET_CSS)

root = tk.Tk()
root.title("🎨 CSS 실시간 테마 디버거")
root.geometry("420x550")
root.attributes("-topmost", True)

tk.Label(
    root, text="CSS 실시간 색상 수정기", font=("Helvetica", 14, "bold"), pady=10
).pack()
tk.Label(
    root,
    text=(
        "사각 버튼을 누르면 원형 스펙트럼 팝업이 나옵니다.\n"
        "수정 시 style.css가 실시간 동기화됩니다."
    ),
    fg="gray",
).pack(pady=5)

# 동적으로 CSS 변수 전체 사각 버튼 UI 생성
for css_var_name, color in current_theme.items():
    if not color.startswith("#"):
        continue

    frame = tk.Frame(root, pady=4)
    frame.pack(fill="x", padx=25)

    lbl = tk.Label(
        frame,
        text=f"{css_var_name}: ",
        width=20,
        anchor="w",
        font=("Helvetica", 9, "bold"),
    )
    lbl.pack(side="left")

    # 메인 윈도우는 원래 요청하셨던 '사각형' 버튼 유지
    btn = tk.Button(
        frame, bg=color, width=15, relief="solid", bd=1, cursor="hand2"
    )
    btn.config(command=lambda k=css_var_name, b=btn: pick_color(k, b))
    btn.pack(side="right", expand=True, fill="x")

root.mainloop()