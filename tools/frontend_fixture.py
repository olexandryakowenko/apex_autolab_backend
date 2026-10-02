"""Disposable HTTP server for browser tests; never points at instance/."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from apex import create_app
from apex.auth import create_operator
from waitress import create_server
from PIL import Image, ImageDraw, ImageFont

root=Path(sys.argv[1]).resolve()
app=create_app({'DATA_DIR':str(root/'data')})
with app.app_context(): create_operator('operator','Frontend-test-2026!')
image=Image.new('RGB',(520,120),'white')
ImageDraw.Draw(image).text((20,20),'AA1234BB',fill='black',font=ImageFont.load_default(size=70))
image.save(root/'plate.png')
server=create_server(app,host='127.0.0.1',port=0,threads=4)
print('READY '+str(server.effective_port),flush=True)
server.run()
