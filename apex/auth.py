import hashlib
import secrets
import time
from flask import Blueprint, g, jsonify, request, session
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db, transaction, now
from .validation import Problem, body, text

bp = Blueprint('auth', __name__, url_prefix='/api/auth')
PUBLIC = {'auth.csrf', 'auth.login', 'api.health', 'api.index', 'static'}

def guard():
    if request.endpoint is None or request.endpoint in PUBLIC:
        return
    token = session.get('login_token', '')
    row = get_db().execute('SELECT users.id,users.username FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires_at>?',
                          (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    if row is None:
        raise Problem('unauthorized', 'Потрібно увійти.', 401)
    g.user = dict(row)

@bp.get('/csrf')
def csrf():
    return jsonify(csrf_token=generate_csrf())

@bp.post('/login')
def login():
    data = body({'username','password'}, {'username','password'})
    username = text(data['username'], 'username', 64, True)
    password = text(data['password'], 'password', 256, True)
    address = request.remote_addr or 'local'
    with transaction() as db:
        attempt = db.execute('SELECT * FROM login_attempts WHERE address=?', (address,)).fetchone()
        if attempt and time.time()-attempt['started'] < 300 and attempt['count'] >= 5:
            raise Problem('rate_limited', 'Забагато спроб. Повторіть через 5 хвилин.', 429)
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        valid = user and check_password_hash(user['password_hash'], password)
        if not valid:
            if not attempt or time.time()-attempt['started'] >= 300:
                db.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,1,?)', (address,time.time()))
            else:
                db.execute('UPDATE login_attempts SET count=count+1 WHERE address=?', (address,))
        else:
            db.execute('DELETE FROM login_attempts WHERE address=?', (address,))
            db.execute('DELETE FROM sessions WHERE expires_at<=?', (time.time(),))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),user['id'],time.time()+28800))
    if not valid:
        raise Problem('invalid_credentials', 'Невірне ім’я або пароль.', 401)
    session.clear()
    session['login_token'] = token
    return jsonify(data={'id':user['id'],'username':user['username']}, csrf_token=generate_csrf())

@bp.post('/logout')
def logout():
    with transaction() as db:
        db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(session['login_token'].encode()).hexdigest(),))
    session.clear()
    return '', 204

@bp.get('/me')
def me():
    return jsonify(data=g.user)

def create_operator(username, password):
    username = text(username, 'username', 64, True)
    if len(password) < 12 or len(password) > 256 or password != password.strip():
        raise Problem('weak_password', 'Пароль: 12–256 символів без крайніх пробілів.')
    with transaction() as db:
        if db.execute('SELECT 1 FROM users').fetchone():
            raise Problem('operator_exists', 'Оператор уже створений.', 409)
        db.execute('INSERT INTO users VALUES(1,?,?,?)', (username,generate_password_hash(password),now()))
