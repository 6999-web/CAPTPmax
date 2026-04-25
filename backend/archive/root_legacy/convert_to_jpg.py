from PIL import Image
import os

src = r"C:\Users\xxzx-admin\Desktop\新建文件夹 (2)\system_workflow_1775392451184.png"
dst = r"C:\Users\xxzx-admin\Desktop\新建文件夹 (2)\system_workflow_1775392451184.jpg"

if not os.path.exists(src):
    raise FileNotFoundError(f"Source file not found: {src}")

im = Image.open(src).convert('RGB')
im.save(dst, 'JPEG')
print('Conversion succeeded: saved to', dst)
