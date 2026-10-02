"""Validated snapshots; restore is an offline CLI operation, never a zip extractall."""
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path
from flask import Blueprint, current_app, jsonify, send_file
from .db import connect, close_db, now
from .validation import Problem

bp=Blueprint('backups',__name__,url_prefix='/api/backups')
MAX_ARCHIVE=512*1024*1024
def digest(data): return hashlib.sha256(data).hexdigest()

def create_backup():
    root=Path(current_app.config['DATA_DIR'])
    with current_app.extensions['write_lock'], tempfile.TemporaryDirectory(dir=root) as tmp:
        snapshot=Path(tmp)/'database.sqlite3'
        source=connect(current_app.config['DATABASE']);target=sqlite3.connect(snapshot)
        try: source.backup(target)
        finally: target.close();source.close()
        db=connect(snapshot)
        try:
            db.execute('DELETE FROM sessions');db.execute('DELETE FROM login_attempts')
            filenames=[x[0] for x in db.execute('SELECT filename FROM attachments')]
        finally: db.close()
        files={'database.sqlite3':snapshot.read_bytes()}
        for filename in filenames:
            if not re.fullmatch(r'[0-9a-f]{32}\.jpg',filename): raise Problem('backup_failed','Некоректне посилання на вкладення.',409)
            path=Path(current_app.config['UPLOADS'])/filename
            if not path.is_file(): raise Problem('backup_failed','Відсутнє вкладення. Копію не створено.',409)
            files['uploads/'+filename]=path.read_bytes()
        if sum(map(len,files.values()))>MAX_ARCHIVE:
            raise Problem('backup_limit','Прототип підтримує архіви до 512 МБ.',413)
        manifest={'schema_version':1,'created_at':now(),'sha256':{k:digest(v) for k,v in files.items()}}
        ident=uuid.uuid4().hex
        out=root/'backups'/(ident+'.zip')
        partial=out.with_suffix('.tmp')
        try:
            with zipfile.ZipFile(partial,'w',zipfile.ZIP_DEFLATED) as archive:
                for name,data in files.items(): archive.writestr(name,data)
                archive.writestr('manifest.json',json.dumps(manifest))
            partial.replace(out);out.chmod(0o600)
        finally: partial.unlink(missing_ok=True)
        return {'id':ident,'created_at':manifest['created_at'],'bytes':out.stat().st_size}

def restore_backup(archive_path):
    """Caller must hold the process lock and explicitly confirm replacement."""
    root=Path(current_app.config['DATA_DIR']);state=root/'state'
    close_db()
    path=Path(archive_path)
    if not path.is_file() or path.stat().st_size>MAX_ARCHIVE:
        raise Problem('invalid_archive','Архів відсутній або завеликий.')
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        staged=Path(tmp)/'state';staged.mkdir(mode=0o700);(staged/'uploads').mkdir(mode=0o700)
        try:
            with zipfile.ZipFile(path) as archive:
                infos=archive.infolist();names=[x.filename for x in infos]
                if len(names)!=len(set(names)) or len(names)>10000 or sum(x.file_size for x in infos)>MAX_ARCHIVE:
                    raise ValueError
                if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size>2_000_000: raise ValueError
                manifest=json.loads(archive.read('manifest.json'))
                if manifest['schema_version']!=1 or not isinstance(manifest['sha256'],dict): raise ValueError
                if set(names)!=set(manifest['sha256'])|{'manifest.json'}: raise ValueError
                if 'database.sqlite3' not in manifest['sha256']: raise ValueError
                for name,checksum in manifest['sha256'].items():
                    if name!='database.sqlite3' and not re.fullmatch(r'uploads/[0-9a-f]{32}\.jpg',name): raise ValueError
                    data=archive.read(name)
                    if digest(data)!=checksum: raise ValueError
                    destination=staged/('app.sqlite3' if name=='database.sqlite3' else name)
                    destination.write_bytes(data);destination.chmod(0o600)
            db=connect(staged/'app.sqlite3')
            try:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError
                if db.execute('SELECT version FROM meta').fetchone()[0]!=1: raise ValueError
                expected={'meta','users','sessions','login_attempts','clients','vehicles','orders','attachments','status_history'}
                actual={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not expected<=actual: raise ValueError
                files={x[0] for x in db.execute('SELECT filename FROM attachments')}
                if files!={p.name for p in (staged/'uploads').iterdir()}: raise ValueError
                # Only our own schema may be restored; prevents malicious triggers/views.
                original=connect(current_app.config['DATABASE'])
                try:
                    sql="SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"
                    if [tuple(x) for x in db.execute(sql)] != [tuple(x) for x in original.execute(sql)]: raise ValueError
                finally: original.close()
                db.execute('DELETE FROM sessions');db.execute('DELETE FROM login_attempts')
            finally: db.close()
        except (zipfile.BadZipFile,KeyError,ValueError,TypeError,sqlite3.Error,OSError,RuntimeError) as exc:
            raise Problem('invalid_archive','Архів пошкоджений або має несумісну структуру.') from exc
        safety=create_backup()
        old=root/('state-old-'+uuid.uuid4().hex)
        state.rename(old)
        try: staged.rename(state)
        except BaseException:
            old.rename(state)
            raise
        shutil.rmtree(old)
        return safety

@bp.route('',methods=['GET','POST'])
def backups():
    from flask import request
    if request.method=='POST': return jsonify(data=create_backup()),201
    items=[]
    for p in sorted((Path(current_app.config['DATA_DIR'])/'backups').glob('*.zip'),key=lambda p:p.stat().st_mtime,reverse=True):
        items.append({'id':p.stem,'bytes':p.stat().st_size,'modified_unix':p.stat().st_mtime})
    return jsonify(data=items)

@bp.get('/<ident>')
def backup_file(ident):
    if not re.fullmatch('[0-9a-f]{32}',ident): raise Problem('not_found','Копію не знайдено.',404)
    path=Path(current_app.config['DATA_DIR'])/'backups'/(ident+'.zip')
    if not path.is_file(): raise Problem('not_found','Копію не знайдено.',404)
    return send_file(path,as_attachment=True,download_name='apex-backup-'+ident+'.zip')
