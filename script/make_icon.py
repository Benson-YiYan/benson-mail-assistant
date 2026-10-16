from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from benson_mail.app_icon import icon_image

assets = root / 'assets'
assets.mkdir(exist_ok=True)
image = icon_image()
image.save(assets / 'mail.png')
image.save(assets / 'mail.ico', sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
