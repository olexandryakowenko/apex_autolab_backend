import io
import json
import sqlite3
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from PIL import Image
from apex import create_app
from apex.db import get_db, now
from apex.orders import receive
from apex.backup import create_backup, restore_backup, digest
from apex.locking import process_lock
from apex.validation import Problem
from conftest import PASSWORD

def contact(api,name='Тестовий Клієнт'):
    response=api('POST','/api/clients',json={'name':name,'phone':'+380 (67) 123-45-67'})
    assert response.status_code==201,response.json
    return response.json['data']['id']

def status(api,order,value,**kwargs):
    return api('PATCH',f'/api/orders/{order}/status',json={'status':value,**kwargs})

def image_bytes():
    output=io.BytesIO();Image.new('RGB',(400,100),'white').save(output,'PNG');output.seek(0)
    return output

def test_auth_csrf_logout_revocation(app):
    client=app.test_client()
    assert client.get('/api/clients').status_code==401
    assert client.post('/api/auth/login',json={}).status_code==400
    token=client.get('/api/auth/csrf').json['csrf_token']
    result=client.post('/api/auth/login',json={'username':'operator','password':PASSWORD},headers={'X-CSRFToken':token})
    assert result.status_code==200
    cookie=client.get_cookie('session').value
    assert client.get('/api/auth/me').json['data']['username']=='operator'
    assert client.post('/api/clients',json={'name':'A','phone':'1234567'}).status_code==400
    assert client.post('/api/auth/logout',headers={'X-CSRFToken':result.json['csrf_token']}).status_code==204
    client.set_cookie('session',cookie)
    assert client.get('/api/auth/me').status_code==401

def test_rate_limit_persists(app):
    client=app.test_client();token=client.get('/api/auth/csrf').json['csrf_token']
    for i in range(5):
        assert client.post('/api/auth/login',json={'username':'operator','password':'incorrect'},headers={'X-CSRFToken':token}).status_code==401
    assert client.post('/api/auth/login',json={'username':'operator','password':PASSWORD},headers={'X-CSRFToken':token}).status_code==429
    with app.app_context(): assert get_db().execute('SELECT count FROM login_attempts').fetchone()[0]==5

def test_loopback_and_host(app):
    client=app.test_client()
    assert client.get('/api/health',environ_overrides={'REMOTE_ADDR':'192.168.1.2'}).status_code==403
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==400
    response=client.get('/api/health')
    assert response.json['status']=='ok'
    assert response.headers['Cache-Control']=='no-store'

@pytest.mark.parametrize('data',[
    {'name':'','phone':'1234567'}, {'name':'A','phone':'abc'},
    {'name':123,'phone':'1234567'}, {'name':'A','phone':'123'},
    {'name':'A','phone':'1234567','admin':True}, {'name':'A'*121,'phone':'1234567'},
])
def test_invalid_client(api,data):
    assert api('POST','/api/clients',json=data).status_code==422
    assert api('GET','/api/clients').json['data']==[]

def test_malformed_json(api):
    assert api('POST','/api/clients',data='{',content_type='application/json').status_code==400

def test_crud_unicode_and_phone(api):
    ident=contact(api)
    response=api('GET','/api/clients?q=КЛІЄНТ')
    assert response.json['data'][0]['phone']=='380671234567'
    assert api('PATCH',f'/api/clients/{ident}',json={'notes':'Перевірено'}).status_code==200
    assert api('DELETE',f'/api/clients/{ident}').status_code==204
    assert api('GET',f'/api/clients/{ident}').status_code==404

@pytest.mark.parametrize('data',[
    {'plate':'??'}, {'plate':'AA1234BB','vin':'INVALID'},
    {'plate':'AA1234BB','client_id':True}, {'plate':'AA1234BB','client_id':-1},
    {'plate':'AA1234BB','client_id':10**30},
])
def test_invalid_vehicle(api,data):
    assert api('POST','/api/vehicles',json=data).status_code==422

def test_vehicle_crud_and_uniqueness(api):
    ident=contact(api)
    response=api('POST','/api/vehicles',json={'plate':'АА-1234-ВВ','client_id':ident,'vin':'WVWZZZ1JZXW000001'})
    assert response.status_code==201
    vehicle=response.json['data'];assert vehicle['plate']=='AA1234BB'
    assert api('POST','/api/vehicles',json={'plate':'AA1234BB'}).status_code==409
    assert api('PATCH',f"/api/vehicles/{vehicle['id']}",json={'model':'Golf'}).status_code==200
    assert api('DELETE',f'/api/clients/{ident}').status_code==409
    assert api('DELETE',f"/api/vehicles/{vehicle['id']}").status_code==204

def test_unknown_reception_and_missing_client(api,reception):
    order=reception();assert order['status']=='draft'
    assert 'client_name' in order['missing_fields']
    assert status(api,order['id'],'ready',confirmed=True).status_code==422
    assert status(api,order['id'],'in_progress').status_code==409
    assert api('POST','/api/orders',json={'plate':'BC9999AA','confirmed':False}).status_code==422

def test_duplicate_active_order(api,reception):
    first=reception()
    repeat=api('POST','/api/orders',json={'plate':'AA1234BB','confirmed':True,'description':'Не перезаписати'})
    assert repeat.status_code==200 and repeat.json['created'] is False
    assert repeat.json['data']['id']==first['id']
    assert repeat.json['data']['description']==''
    assert len(api('GET','/api/orders').json['data'])==1

def test_known_vehicle_inherits_contact(api):
    ident=contact(api)
    api('POST','/api/vehicles',json={'plate':'BC5678AA','client_id':ident})
    result=api('POST','/api/orders',json={'plate':'BC5678AA','confirmed':True}).json['data']
    assert result['client_id']==ident

def test_full_lifecycle_snapshots_and_history(api,reception):
    client=contact(api);order=reception(client_id=client,description='Діагностика');key=order['id']
    assert status(api,key,'ready',confirmed=True).status_code==200
    api('PATCH',f'/api/clients/{client}',json={'name':'Інша назва','phone':'1234567'})
    assert status(api,key,'in_progress').json['data']['client_name']=='Тестовий Клієнт'
    assert api('PATCH',f'/api/orders/{key}',json={'description':'Нова'}).status_code==409
    assert api('PATCH',f'/api/orders/{key}',json={'notes':'Результат'}).status_code==200
    result=status(api,key,'completed');assert result.status_code==200
    assert [x['new_status'] for x in result.json['data']['history']]==['draft','ready','in_progress','completed']
    assert api('PATCH',f'/api/orders/{key}',json={'notes':'Зміна'}).status_code==409
    assert status(api,key,'draft').status_code==409
    assert api('DELETE',f"/api/vehicles/{order['vehicle_id']}").status_code==409
    assert api('DELETE',f'/api/clients/{client}').status_code==409
    assert reception()['id']!=key

def test_ready_edit_requires_reconfirmation(api,reception):
    key=reception(client_id=contact(api),description='Огляд')['id']
    assert status(api,key,'ready',confirmed=True).status_code==200
    result=api('PATCH',f'/api/orders/{key}',json={'description':'Заміна оливи'})
    assert result.json['data']['status']=='draft'
    assert result.json['data']['confirmed'] is False
    assert status(api,key,'in_progress').status_code==409
    assert status(api,key,'ready',confirmed=True).status_code==200
    assert status(api,key,'draft').status_code==200

def test_cancel_requires_reason_and_confirmation(api,reception):
    key=reception()['id']
    assert status(api,key,'cancelled',reason='Відмова').status_code==422
    assert status(api,key,'cancelled',confirmed=True).status_code==422
    assert status(api,key,'cancelled',confirmed=True,reason='Відмова').status_code==200

def test_plate_change_during_active_order(api,reception):
    vehicle=reception()['vehicle_id']
    assert api('PATCH',f'/api/vehicles/{vehicle}',json={'plate':'BC1111AA'}).status_code==409

def test_concurrent_reception_single_order(app):
    def work(_):
        with app.app_context(): return receive({'plate':'AA1234BB','confirmed':True})
    with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(work,range(8)))
    assert len({r[0] for r in results})==1
    assert sum(r[1] for r in results)==1

def test_database_constraints_and_rollback(app,reception):
    order=reception()
    with app.app_context():
        db=get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE orders SET status='in_progress',confirmed=1 WHERE id=?",(order['id'],))
        assert db.execute('SELECT status FROM orders').fetchone()[0]=='draft'
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('DELETE FROM vehicles WHERE id=?',(order['vehicle_id'],))

@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1','status=unknown','date_from=2026-02-30','date_from=2026-10-02&date_to=2026-01-01'])
def test_invalid_filters(api,query):
    assert api('GET','/api/orders?'+query).status_code==422

def test_pagination_and_literal_sql(api,reception):
    reception();reception(plate='BC2222AA')
    page=api('GET','/api/orders?limit=1').json
    assert len(page['data'])==1 and page['has_more'] is True
    assert api('GET','/api/orders?limit=1&offset=1').json['has_more'] is False
    result=api('GET','/api/clients',query_string={'q':"' OR 1=1 --"})
    assert result.status_code==200 and result.json['data']==[]

def test_persistence_after_restart(app,api,reception):
    order=reception()
    restarted=create_app({'TESTING':True,'DATA_DIR':app.config['DATA_DIR']})
    with restarted.app_context(): assert get_db().execute('SELECT id FROM orders').fetchone()[0]==order['id']

def test_attachment_validated_and_downloaded(api,reception):
    key=reception()['id']
    response=api('POST',f'/api/orders/{key}/attachments',data={'confirmed':'true','file':(image_bytes(),'../../file.png')})
    assert response.status_code==201
    image=api('GET',response.json['data']['url'])
    assert image.status_code==200 and image.mimetype=='image/jpeg'
    assert len(api('GET',f'/api/orders/{key}').json['data']['attachments'])==1

def test_invalid_images_and_crop(api):
    assert api('POST','/api/ocr',data={'file':(io.BytesIO(b'not-an-image'),'x.png')}).status_code==422
    assert api('POST','/api/ocr',data={'crop':'[0,0,9999,100]','file':(image_bytes(),'x.png')}).status_code==422
    response=api('POST','/api/ocr',data={'file':(io.BytesIO(b'x'*(10*1024*1024+1)),'x.png')})
    assert response.status_code==413

def test_ocr_missing_dependency(app,api):
    app.config['TESSERACT']='nonexistent-apex-tesseract'
    assert api('POST','/api/ocr',data={'file':(image_bytes(),'x.png')}).status_code==503
    assert api('GET','/api/vehicles').status_code==200

def test_ocr_success_and_timeout(app,api,monkeypatch):
    import subprocess
    from types import SimpleNamespace
    monkeypatch.setattr('apex.media.shutil.which',lambda _: '/mock/tesseract')
    monkeypatch.setattr('apex.media.subprocess.run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=b'AA1234BB\n'))
    result=api('POST','/api/ocr',data={'file':(image_bytes(),'x.png')}).json['data']
    assert result=={'text':'AA1234BB','requires_confirmation':True,'stored':False}
    def timeout(*a,**k): raise subprocess.TimeoutExpired('tesseract',15)
    monkeypatch.setattr('apex.media.subprocess.run',timeout)
    assert api('POST','/api/ocr',data={'file':(image_bytes(),'x.png')}).status_code==504

def test_backup_restore_roundtrip(app,api,reception):
    key=reception()['id']
    api('POST',f'/api/orders/{key}/attachments',data={'confirmed':'true','file':(image_bytes(),'x.png')})
    result=api('POST','/api/backups');assert result.status_code==201
    path=Path(app.config['DATA_DIR'])/'backups'/(result.json['data']['id']+'.zip')
    reception(plate='BC4444AA')
    with app.app_context():
        safety=restore_backup(path)
        assert (path.parent/(safety['id']+'.zip')).exists()
        assert get_db().execute('SELECT count(*) FROM orders').fetchone()[0]==1
        assert get_db().execute('SELECT count(*) FROM sessions').fetchone()[0]==0
    assert len(list(Path(app.config['UPLOADS']).glob('*.jpg')))==1
    assert api('GET','/api/orders').status_code==401

@pytest.mark.parametrize('kind',['checksum','traversal','schema'])
def test_bad_backup_never_changes_data(app,reception,tmp_path,kind):
    reception()
    with app.app_context():
        backup=create_backup()
        path=Path(app.config['DATA_DIR'])/'backups'/(backup['id']+'.zip')
        with zipfile.ZipFile(path) as z: files={n:z.read(n) for n in z.namelist()}
        manifest=json.loads(files['manifest.json'])
        if kind=='checksum': files['database.sqlite3']+=b'bad'
        if kind=='traversal':
            files['../escape']=b'bad';manifest['sha256']['../escape']=digest(b'bad')
        if kind=='schema':
            dbfile=tmp_path/'bad.sqlite';dbfile.write_bytes(files['database.sqlite3'])
            conn=sqlite3.connect(dbfile);conn.execute('CREATE TABLE injected(id INTEGER)');conn.close()
            files['database.sqlite3']=dbfile.read_bytes();manifest['sha256']['database.sqlite3']=digest(files['database.sqlite3'])
        files['manifest.json']=json.dumps(manifest).encode()
        bad=tmp_path/'bad.zip'
        with zipfile.ZipFile(bad,'w') as z:
            for name,data in files.items(): z.writestr(name,data)
        with pytest.raises(Problem): restore_backup(bad)
        assert get_db().execute('SELECT count(*) FROM orders').fetchone()[0]==1
        assert not (Path(app.config['DATA_DIR'])/'escape').exists()

def test_process_lock(tmp_path):
    with process_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with process_lock(tmp_path): pass
    with process_lock(tmp_path): pass
