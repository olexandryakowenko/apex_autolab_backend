from pathlib import Path

def test_public_shell_and_assets_keep_api_private(app):
    client=app.test_client()
    response=client.get('/')
    assert response.status_code==200 and response.mimetype=='text/html'
    assert b'APEX AUTOLAB' in response.data
    assert b'js/app.js' in response.data
    assert client.get('/static/js/app.js').status_code==200
    assert client.get('/static/css/app.css').status_code==200
    assert client.get('/api/clients').status_code==401
    assert client.get('/api/orders').status_code==401

def test_browser_policy_restricts_scripts_and_external_connections(app):
    response=app.test_client().get('/')
    policy=response.headers['Content-Security-Policy']
    assert "script-src 'self'" in policy
    assert "connect-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert 'unsafe-inline' not in policy
    assert 'unsafe-eval' not in policy
    assert response.headers['Cache-Control']=='no-store'

def test_ui_does_not_publish_runtime_data(app):
    client=app.test_client()
    for url in ('/instance/secret.key','/instance/state/app.sqlite3','/static/../instance/secret.key'):
        assert client.get(url).status_code in (401,404)
