"""生成 app_icon.ico：黑色圆角背景 + 蓝色 'fm' 文字，居中对齐"""
from PIL import Image, ImageDraw, ImageFont
import struct, io

SIZES = [256, 64, 48, 32, 16]

def make_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    # 黑色圆角背景
    draw = ImageDraw.Draw(img)
    r = int(size * 0.2)
    draw.rounded_rectangle([0, 0, size-1, size-1], radius=r, fill=(20, 20, 20, 255))

    # 蓝色 "fm" 文字
    font_size = int(size * 0.5)
    try:
        font = ImageFont.truetype("msyhbd.ttc", font_size)
    except:
        try:
            font = ImageFont.truetype("msyh.ttc", font_size)
        except:
            font = ImageFont.truetype("arial.ttf", font_size)

    text = "fm"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)  # 白色文字

    return img

# 生成各尺寸
images = [make_icon(s) for s in SIZES]

# 保存为 ICO
icon_path = r"C:\Users\sss\WorkBuddy\2026-05-25-17-31-11\app_icon.ico"
images[0].save(icon_path, format='ICO', sizes=[(s, s) for s in SIZES],
               append_images=images[1:])
print(f"Icon saved: {icon_path}")
print(f"Sizes: {SIZES}")
