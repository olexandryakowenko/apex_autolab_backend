import logging
import os
import secrets
import sqlite3
from pathlib import Path
from threading import RLock
from flask import Flask, g, jsonify, request
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.exceptions import HTTPException
from .db import initialize, close_db
from .validation import Problem

def create_app(config=None):
    app=Flask(__name__)
    root=Path(os.environ.get('APEX_DATA_DIR',Path(__file__).resolve().parent.parent/'instance')).resolve()
    app.config.update(DATA_DIR=str(root),MAX_CONTENT_LENGTH=11*1024*1024,SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=False,TRUSTED_HOSTS=['127.0.0.1','localhost'],
                      TESSERACT=os.environ.get('APEX_TESSERACT','tesseract'),OCR_TIMEOUT=15)
    if config: app.config.update(config)
    root=Path(app.config['DATA_DIR'])
    for path in (root,root/'state',root/'state'/'uploads',root/'backups'):
        path.mkdir(parents=True,exist_ok=True);path.chmod(0o700)
    app.config.update(DATABASE=str(root/'state'/'app.sqlite3'),UPLOADS=str(root/'state'/'uploads'))
    secret=root/'secret.key'
    if not secret.exists():
        with open(secret,'xb') as f: f.write(secrets.token_bytes(32))
        secret.chmod(0o600)
    app.config['SECRET_KEY']=secret.read_bytes()
    initialize(app.config['DATABASE'])
    Path(app.config['DATABASE']).chmod(0o600)
    app.extensions['write_lock']=RLock()

    @app.before_request
    def middleware():
        if request.remote_addr not in (None,'127.0.0.1','::1'):
            raise Problem('local_only','Дозволено лише локальний доступ.',403)
        if request.method not in ('GET','HEAD','OPTIONS'):
            app.extensions['write_lock'].acquire();g.write_locked=True
        from .auth import guard
        guard()

    CSRFProtect(app)
    from .auth import bp as auth_bp
    from .routes import bp as api_bp
    from .media import bp as media_bp
    from .backup import bp as backup_bp
    for bp in (auth_bp,api_bp,media_bp,backup_bp): app.register_blueprint(bp)

    @app.teardown_request
    def cleanup(error):
        close_db(error)
        if g.pop('write_locked',False): app.extensions['write_lock'].release()
    app.teardown_appcontext(close_db)

    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'none'; frame-ancestors 'none'"
        return response

    def error(code,message,status,details=None):
        return jsonify(error={'code':code,'message':message,'details':details}),status
    @app.errorhandler(Problem)
    def problem(exc): return error(exc.code,exc.message,exc.status,exc.details)
    @app.errorhandler(CSRFError)
    def csrf_error(exc): return error('csrf_failed','Відсутній або недійсний CSRF-токен.',400)
    @app.errorhandler(sqlite3.IntegrityError)
    def conflict(exc): return error('data_conflict','Порушення унікальності або зв’язків даних.',409)
    @app.errorhandler(sqlite3.OperationalError)
    def unavailable(exc): return error('database_unavailable','База тимчасово недоступна.',503)
    @app.errorhandler(HTTPException)
    def http_error(exc): return error('http_error',exc.name,exc.code)
    @app.errorhandler(Exception)
    def unexpected(exc):
        # Do not log request bodies, paths to uploads, or exception data containing PII.
        app.logger.error('Unhandled error type=%s',type(exc).__name__)
        return error('internal_error','Внутрішня помилка сервера.',500)
    return app
