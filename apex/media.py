import io
import json
import shutil
import subprocess
import uuid
import warnings
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
from .db import one, transaction, now
from .orders import CLOSED
from .validation import Problem

bp=Blueprint('media',__name__)
MAX_BYTES=10*1024*1024
MAX_PIXELS=20_000_000

def uploaded_image():
    upload=request.files.get('file')
    if not upload: raise Problem('file_required','Завантажте зображення в поле file.')
    raw=upload.stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise Problem('file_too_large','Фото перевищує 10 МБ.',413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            im=Image.open(io.BytesIO(raw))
            if im.format not in ('JPEG','PNG') or im.width*im.height>MAX_PIXELS:
                raise Problem('invalid_image','Потрібне JPEG/PNG до 20 мегапікселів.')
            im.load()
            return ImageOps.exif_transpose(im).convert('RGB')
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise Problem('invalid_image','Не вдалося прочитати зображення.')

@bp.post('/api/ocr')
def recognize():
    im=uploaded_image()
    if 'crop' in request.form:
        try:
            area=json.loads(request.form['crop'])
            if not isinstance(area,list) or len(area)!=4 or any(type(v) is not int for v in area): raise ValueError
            l,t,r,b=area
            if not (0<=l<r<=im.width and 0<=t<b<=im.height): raise ValueError
            im=im.crop(area)
        except (ValueError,TypeError): raise Problem('invalid_crop','crop: [left,top,right,bottom] у межах фото.')
    executable=shutil.which(current_app.config['TESSERACT'])
    if not executable: raise Problem('ocr_unavailable','Tesseract не встановлено. Введіть номер вручну.',503)
    im=ImageOps.autocontrast(ImageOps.grayscale(im))
    im.thumbnail((2400,800))
    scale=min(600/im.width,800/im.height)
    if scale>1:
        im=im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))))
    buf=io.BytesIO();im.save(buf,format='PNG')
    try:
        result=subprocess.run([executable,'stdin','stdout','-l','eng','--psm','7','-c','tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'],
                              input=buf.getvalue(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=current_app.config['OCR_TIMEOUT'],check=False)
    except subprocess.TimeoutExpired: raise Problem('ocr_timeout','Час OCR вичерпано. Введіть номер вручну.',504)
    except OSError: raise Problem('ocr_unavailable','Не вдалося запустити OCR.',503)
    if result.returncode: raise Problem('ocr_failed','OCR завершився помилкою. Введіть номер вручну.',503)
    value=''.join(result.stdout.decode('utf-8',errors='replace').split())[:40]
    return jsonify(data={'text':value,'requires_confirmation':True,'stored':False})

@bp.post('/api/orders/<int:ident>/attachments')
def attach(ident):
    order=one('orders',ident)
    if order['status'] in CLOSED: raise Problem('closed_order','Закритий наряд не редагується.',409)
    if request.form.get('confirmed')!='true': raise Problem('confirmation_required','Підтвердіть збереження фото.')
    im=uploaded_image()
    filename=uuid.uuid4().hex+'.jpg'
    path=Path(current_app.config['UPLOADS'])/filename
    buf=io.BytesIO();im.save(buf,format='JPEG',quality=90)
    if buf.tell()>MAX_BYTES: raise Problem('file_too_large','Зображення після обробки перевищує 10 МБ.',413)
    try:
        path.write_bytes(buf.getvalue());path.chmod(0o600)
        with transaction() as db:
            # Recheck inside transaction for use outside the normal request mutex.
            if one('orders',ident)['status'] in CLOSED: raise Problem('closed_order','Закритий наряд не редагується.',409)
            key=db.execute('INSERT INTO attachments(order_id,filename,mime_type,bytes,created_at) VALUES(?,?,?,?,?)',
                           (ident,filename,'image/jpeg',path.stat().st_size,now())).lastrowid
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return jsonify(data={'id':key,'order_id':ident,'url':f'/api/attachments/{key}'}),201

@bp.get('/api/attachments/<int:ident>')
def attachment(ident):
    row=one('attachments',ident)
    path=Path(current_app.config['UPLOADS'])/row['filename']
    if not path.is_file(): raise Problem('missing_file','Файл вкладення відсутній.',404)
    return send_file(path,mimetype='image/jpeg',as_attachment=True,download_name=f'photo-{ident}.jpg')
