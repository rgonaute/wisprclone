"""Generate the WisprClone app icon (a simple mic dot on a dark rounded square)."""
from pathlib import Path

from PIL import Image, ImageDraw


def build(path) -> Path:
    path = Path(path)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # dark rounded background
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=48, fill=(15, 18, 31, 255))
    # microphone body (rounded pill)
    d.rounded_rectangle([104, 60, 152, 150], radius=24, fill=(0, 255, 132, 255))
    # stand
    d.arc([84, 120, 172, 190], start=0, end=180, width=10, fill=(0, 255, 132, 255))
    d.line([128, 190, 128, 210], width=10, fill=(0, 255, 132, 255))
    d.line([104, 212, 152, 212], width=10, fill=(0, 255, 132, 255))
    img.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


if __name__ == "__main__":
    out = build(Path(__file__).with_name("wisprclone.ico"))
    print("wrote", out)
