"""Real Waitress HTTP smoke test; disposable data, no customer records."""
import io
import json
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import http.cookiejar
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from apex import create_app
from apex.auth import create_operator
from PIL import Image,ImageDraw,ImageFont

def run():
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)/'data'
        app=create_app({'DATA_DIR':str(root)})
        password='Disposable-smoke-password-2026'
        with app.app_context(): create_operator('smoke',password)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        process=subprocess.Popen([sys.executable,str(ROOT/'manage.py'),'--data-dir',str(root),'serve','--port',str(port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        base=f'http://127.0.0.1:{port}'
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def call(path,method='GET',data=None,token=None,raw=None,content_type=None):
            headers={}
            if data is not None: raw=json.dumps(data).encode();headers['Content-Type']='application/json'
            if content_type: headers['Content-Type']=content_type
            if token: headers['X-CSRFToken']=token
            with opener.open(urllib.request.Request(base+path,data=raw,method=method,headers=headers),timeout=20) as response:
                return response.status,json.load(response)
        try:
            for _ in range(50):
                try:
                    health=call('/api/health');break
                except (OSError,urllib.error.URLError):
                    if process.poll() is not None: raise RuntimeError('Server failed to start')
                    time.sleep(.1)
            else: raise RuntimeError('Startup timeout')
            token=call('/api/auth/csrf')[1]['csrf_token']
            token=call('/api/auth/login','POST',{'username':'smoke','password':password},token)[1]['csrf_token']
            contact=call('/api/clients','POST',{'name':'Тестовий контакт','phone':'1234567890'},token)[1]['data']['id']
            created=call('/api/orders','POST',{'plate':'AA1234BB','confirmed':True,'client_id':contact,'description':'Тест'},token)
            key=created[1]['data']['id']
            duplicate=call('/api/orders','POST',{'plate':'AA1234BB','confirmed':True},token)
            assert created[0]==201 and duplicate[0]==200 and duplicate[1]['data']['id']==key
            states=[]
            for state in ['ready','in_progress','completed']:
                states.append(call(f'/api/orders/{key}/status','PATCH',{'status':state,'confirmed':True},token)[1]['data']['status'])
            backup=call('/api/backups','POST',{},token)
            # A synthetic printed plate verifies the executable pipeline only.
            fontpath=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
            font=ImageFont.truetype(str(fontpath),72) if fontpath.exists() else ImageFont.load_default(size=72)
            im=Image.new('RGB',(640,130),'white');ImageDraw.Draw(im).text((35,15),'AA1234BB',font=font,fill='black')
            out=io.BytesIO();im.save(out,'PNG');boundary='APEXSMOKE2026'
            raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+out.getvalue()+f'\r\n--{boundary}--\r\n'.encode())
            before=time.perf_counter()
            ocr=call('/api/ocr','POST',token=token,raw=raw,content_type='multipart/form-data; boundary='+boundary)
            elapsed=time.perf_counter()-before
            assert ocr[1]['data']['text']=='AA1234BB',ocr
            # Attempt to restore while the server owns the process lock.
            archive=root/'backups'/(backup[1]['data']['id']+'.zip')
            blocked=subprocess.run([sys.executable,str(ROOT/'manage.py'),'--data-dir',str(root),'restore',str(archive),'--confirm'],capture_output=True)
            assert blocked.returncode!=0
            result={'platform':platform.platform(),'python':platform.python_version(),'health_http':health[0],
                    'created_http':created[0],'duplicate_http':duplicate[0],'states':states,'backup_http':backup[0],
                    'online_restore_blocked':True,'synthetic_ocr_expected':'AA1234BB','synthetic_ocr_actual':ocr[1]['data']['text'],
                    'synthetic_ocr_seconds':round(elapsed,3),'real_vehicle_photo_dataset_tested':False}
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return result
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()

if __name__=='__main__':
    result=run()
    if len(sys.argv)>1: Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
