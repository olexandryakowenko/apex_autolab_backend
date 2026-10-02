import pytest
from apex import create_app
from apex.auth import create_operator

PASSWORD='Test-only-password-2026!'

@pytest.fixture
def app(tmp_path):
    app=create_app({'TESTING':True,'DATA_DIR':str(tmp_path/'data')})
    with app.app_context(): create_operator('operator',PASSWORD)
    return app

@pytest.fixture
def api(app):
    client=app.test_client()
    csrf=client.get('/api/auth/csrf').json['csrf_token']
    result=client.post('/api/auth/login',json={'username':'operator','password':PASSWORD},headers={'X-CSRFToken':csrf})
    assert result.status_code==200
    token=result.json['csrf_token']
    def call(method,path,**kwargs):
        kwargs.setdefault('headers',{'X-CSRFToken':token})
        return client.open(path,method=method,**kwargs)
    call.client=client
    return call

@pytest.fixture
def reception(api):
    def create(**extra):
        result=api('POST','/api/orders',json={'plate':'АА 1234 ВВ','confirmed':True,**extra})
        assert result.status_code in (200,201),result.json
        return result.json['data']
    return create
