"""  ==========================================
위 코드는 아래와 같습니다.
1. app에서 사용할 css의 색깔을 변경할 수 있습니다.

위 코드는 다음을 위해 작성되었습니다.  
1. 정의된 css파일의 색상을 불러오고 app.py에서 사용할 색상들을 빠르게 변경할 수 있습니다..
"""
from pathlib import Path
import re
import math
import colorsys
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent.parent
TARGET_CSS = ROOT / "style.css"


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
        colors[key] = parse_color_to_rgba(val.strip())

    return colors


def update_css_color(css_var_name: str, new_color: str):
    """style.css 파일 내 특정 CSS 변수 값을 수정합니다."""
    try:
        if not TARGET_CSS.exists():
            print(f"⚠️ {TARGET_CSS.name} 파일이 존재하지 않습니다.")
            return

        with open(TARGET_CSS, "r", encoding="utf-8") as f:
            content = f.read()

        pattern = rf"({re.escape(css_var_name)}\s*:\s*)([^;]+)(\s*;)"

        if re.search(pattern, content):
            rgba_val = parse_color_to_rgba(new_color)
            modified_content = re.sub(pattern, rf"\1{rgba_val}\3", content)
            with open(TARGET_CSS, "w", encoding="utf-8") as f:
                f.write(modified_content)
            print(f"✅ {TARGET_CSS.name} 내 {css_var_name} 값을 {rgba_val}로 수정했습니다.")
        else:
            print(f"⚠️ {TARGET_CSS.name} 내에서 {css_var_name} 변수를 찾지 못했습니다.")

    except Exception as e:
        print(f"❌ 파일 수정 중 오류 발생: {e}")


def is_valid_color(color_value: str) -> bool:
    """색상 값이 유효한 형식인지 확인"""
    color_value = color_value.strip()
    
    if re.match(r'^#[0-9a-fA-F]{6}$', color_value):
        return True
    
    rgba_match = re.match(r'^rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)$', color_value)
    if rgba_match:
        r, g, b, a = rgba_match.groups()
        return 0 <= int(r) <= 255 and 0 <= int(g) <= 255 and 0 <= int(b) <= 255 and 0 <= float(a) <= 1
    
    rgb_match = re.match(r'^rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$', color_value)
    if rgb_match:
        r, g, b = rgb_match.groups()
        return 0 <= int(r) <= 255 and 0 <= int(g) <= 255 and 0 <= int(b) <= 255
    
    return False


def parse_color_to_rgba(color_value: str) -> str:
    """
    모든 형식의 색상 문자열(#HEX, rgb, rgba)을 파싱하여 rgba(r, g, b, a) 포맷 문자열로 반환합니다.
    """
    color_value = color_value.strip()

    if color_value.startswith('#') and len(color_value) == 7:
        r = int(color_value[1:3], 16)
        g = int(color_value[3:5], 16)
        b = int(color_value[5:7], 16)
        return f"rgba({r}, {g}, {b}, 1.0)"

    rgba_match = re.match(r'rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)', color_value)
    if rgba_match:
        r, g, b, a = rgba_match.groups()
        return f"rgba({int(r)}, {int(g)}, {int(b)}, {float(a)})"

    rgb_match = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', color_value)
    if rgb_match:
        r, g, b = rgb_match.groups()
        return f"rgba({int(r)}, {int(g)}, {int(b)}, 1.0)"

    return "rgba(255, 255, 255, 1.0)"


def rgba_to_hex_and_alpha(rgba_str: str) -> tuple[str, float]:
    """Tkinter UI(Hex) 및 슬라이더(Alpha) 처리를 위해 rgba 문자열을 추출합니다."""
    rgba_str = parse_color_to_rgba(rgba_str)
    rgba_match = re.match(r'rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)', rgba_str)
    if rgba_match:
        r, g, b, a = rgba_match.groups()
        return f"#{int(r):02x}{int(g):02x}{int(b):02x}", float(a)
    return "#ffffff", 1.0


class CircularColorPicker(tk.Toplevel):
    """원형 스펙트럼 색상 선택기"""
    def __init__(self, parent, initial_rgba="rgba(255, 255, 255, 1.0)", title="Choose Color"):
        super().__init__(parent)
        self.title(title)
        self.geometry("260x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        hex_color, alpha = rgba_to_hex_and_alpha(initial_rgba)

        self.confirmed = False
        self.result_hex = hex_color
        self.result_alpha = alpha
        self.hue = 0.0
        self.sat = 0.0
        self.val = 1.0

        self._hex_to_hsv(hex_color)

        self.canvas_size = 200
        self.canvas = tk.Canvas(self, width=self.canvas_size, height=self.canvas_size, cursor="crosshair")
        self.canvas.pack(pady=10)

        self.wheel_img = self._create_color_wheel(self.canvas_size)
        self.wheel_photo = ImageTk.PhotoImage(self.wheel_img)
        self.canvas.create_image(self.canvas_size//2, self.canvas_size//2, image=self.wheel_photo)

        self.selector = self.canvas.create_oval(0, 0, 0, 0, outline="white", width=2)
        self._update_selector_pos()

        self.canvas.bind("<Button-1>", self._on_wheel_click)
        self.canvas.bind("<B1-Motion>", self._on_wheel_click)

        self.val_slider = tk.Scale(
            self, from_=0, to=100, orient="horizontal", 
            label="밝기 (Value)", command=self._on_slider_move
        )
        self.val_slider.set(int(self.val * 100))
        self.val_slider.pack(fill="x", padx=20)

        self.alpha_slider = tk.Scale(
            self, from_=0, to=100, orient="horizontal", 
            label="투명도 (Alpha)", command=self._on_alpha_slider_move
        )
        self.alpha_slider.set(int(alpha * 100))
        self.alpha_slider.pack(fill="x", padx=20)

        bottom_frame = tk.Frame(self)
        bottom_frame.pack(pady=10)

        self.preview = tk.Label(bottom_frame, width=4, bg=self.result_hex, relief="solid", bd=1)
        self.preview.pack(side="left", padx=10)

        tk.Button(bottom_frame, text="확인", command=self._on_ok, width=6).pack(side="left", padx=5)
        tk.Button(bottom_frame, text="취소", command=self._on_cancel, width=6).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def get_rgba_result(self) -> str:
        """선택 완료된 결과값을 rgba 문자열로 반환"""
        hex_str = self.result_hex.lstrip('#')
        r, g, b = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
        return f"rgba({r}, {g}, {b}, {round(self.result_alpha, 2)})"

    def _hex_to_hsv(self, hex_color):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            hex_color = 'ffffff'
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        self.hue, self.sat, self.val = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)

    def _hsv_to_hex(self, h, s, v):
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def _create_color_wheel(self, size):
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

    def _on_alpha_slider_move(self, val):
        self.result_alpha = float(val) / 100.0
        self._update_color()

    def _update_color(self):
        hex_color = self._hsv_to_hex(self.hue, self.sat, self.val)
        self.preview.config(bg=hex_color)
        self.result_hex = hex_color

    def _on_ok(self):
        self.confirmed = True
        self.destroy()

    def _on_cancel(self):
        self.destroy()


def pick_color(css_var_name: str, button: tk.Button, entry: tk.Entry):
    """색상 선택기 팝업"""
    current_val = entry.get().strip()
    rgba_str = parse_color_to_rgba(current_val)

    picker = CircularColorPicker(root, initial_rgba=rgba_str, title=f"{css_var_name} 선택")
    root.wait_window(picker)

    if picker.confirmed:
        new_rgba = picker.get_rgba_result()
        hex_bg, _ = rgba_to_hex_and_alpha(new_rgba)
        
        button.config(bg=hex_bg)
        entry.delete(0, tk.END)
        entry.insert(0, new_rgba)
        
        update_css_color(css_var_name, new_rgba)


def on_entry_change(css_var_name: str, entry: tk.Entry, button: tk.Button, event=None):
    """Entry 필드에서 색상 값 직접 입력 시 반응"""
    color_value = entry.get().strip()
    
    if not color_value:
        return
    
    if not is_valid_color(color_value):
        entry.config(bg="#ffcccc")
        return
    
    entry.config(bg="white")
    rgba_str = parse_color_to_rgba(color_value)
    hex_bg, _ = rgba_to_hex_and_alpha(rgba_str)
    
    button.config(bg=hex_bg)
    entry.delete(0, tk.END)
    entry.insert(0, rgba_str)
    
    update_css_color(css_var_name, rgba_str)


# ============================================================================
# 메인 UI (스크롤 가능)
# ============================================================================

CONFIG = {
    "window": {
        "width": 500,
        "height": 600,
        "title": "🎨 CSS 실시간 테마 디버거",
        "always_on_top": True
    }
}

root = tk.Tk()
root.title(CONFIG["window"]["title"])
root.geometry(f"{CONFIG['window']['width']}x{CONFIG['window']['height']}")
root.attributes("-topmost", CONFIG["window"]["always_on_top"])

tk.Label(
    root, text="CSS 실시간 색상 수정기", font=("Helvetica", 14, "bold"), pady=10
).pack()
tk.Label(
    root,
    text="#RRGGBB 또는 rgba(r,g,b,a) 형식으로 입력하면 바로 변경됩니다.\n버튼 클릭이나 입력 필드에 색상을 입력해주세요.",
    fg="gray",
).pack(pady=5)

canvas = tk.Canvas(root, bg="white")
scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
scrollable_frame = tk.Frame(canvas, bg="white")

scrollable_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)

canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

def _on_mousewheel(event):
    canvas.yview_scroll(int(-1*(event.delta/120)), "units")

canvas.bind_all("<MouseWheel>", _on_mousewheel)

current_theme = load_css_colors(TARGET_CSS)

for css_var_name, color in current_theme.items():
    frame = tk.Frame(scrollable_frame, bg="white", pady=4)
    frame.pack(fill="x", padx=15)

    lbl = tk.Label(
        frame,
        text=f"{css_var_name}:",
        width=20,
        anchor="w",
        font=("Helvetica", 9, "bold"),
        bg="white"
    )
    lbl.pack(side="left")

    rgba_str = parse_color_to_rgba(color)
    hex_bg, _ = rgba_to_hex_and_alpha(rgba_str)
    
    btn = tk.Button(
        frame, bg=hex_bg, width=8, relief="solid", bd=1, cursor="hand2"
    )
    btn.pack(side="left", padx=5)

    entry = tk.Entry(frame, width=35, font=("Courier", 9))
    entry.insert(0, rgba_str)
    entry.pack(side="left", padx=5, fill="x", expand=True)
    
    entry.bind("<Return>", lambda e, k=css_var_name, en=entry, b=btn: on_entry_change(k, en, b, e))
    entry.bind("<FocusOut>", lambda e, k=css_var_name, en=entry, b=btn: on_entry_change(k, en, b, e))

    btn.config(command=lambda k=css_var_name, b=btn, e=entry: pick_color(k, b, e))

canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

root.mainloop()