"""One envelope symbol for the EXE, windows, taskbar and tray."""
from pathlib import Path
import sys
from PIL import Image, ImageDraw


def icon_image(size=256):
    image = Image.new('RGBA', (256, 256))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=55, fill='#2058a5')
    draw.rounded_rectangle((42, 68, 214, 190), radius=14, fill='#ffffff')
    draw.line((48, 181, 104, 132), fill='#c6daf4', width=8)
    draw.line((208, 181, 152, 132), fill='#c6daf4', width=8)
    draw.line((47, 77, 128, 140, 209, 77), fill='#2058a5', width=9, joint='curve')
    return image.resize((size, size), Image.Resampling.LANCZOS)


def apply_window_icon(root):
    from PIL import ImageTk
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    if sys.platform == 'win32':
        root.iconbitmap(str(base / 'assets/mail.ico'))
    photo = ImageTk.PhotoImage(icon_image(64), master=root)
    root.iconphoto(True, photo)
    root._mail_icon = photo


def set_process_identity(uninstaller=False):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'BensonMail.Uninstaller' if uninstaller else 'BensonMail.Assistant')
