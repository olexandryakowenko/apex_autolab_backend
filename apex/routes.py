from flask import Blueprint, jsonify, request, render_template
from .db import get_db, one, transaction, now
from .validation import Problem, body, text, identifier, phone, plate, vin, pagination, query, day
from . import orders

bp = Blueprint('api', __name__)

@bp.get('/')
def index():
    return render_template('index.html')

@bp.get('/api/health')
def health():
    get_db().execute('SELECT 1').fetchone()
    return jsonify(status='ok', version='1.0.0')

def listing(sql, args):
    limit, offset = pagination()
    rows = get_db().execute(sql+' LIMIT ? OFFSET ?', (*args,limit+1,offset)).fetchall()
    return jsonify(data=[dict(r) for r in rows[:limit]],limit=limit,offset=offset,has_more=len(rows)>limit)

def client_values(data, partial=False):
    out={}
    for k in data:
        if k=='phone': out[k]=phone(data[k])
        else: out[k]=text(data[k],k,120 if k=='name' else 2000,k=='name')
    return out

@bp.route('/api/clients', methods=['GET','POST'])
def clients():
    if request.method=='GET':
        q=query().casefold()
        # Python casefold gives Unicode-aware matching in SQLite's custom function.
        return listing('SELECT * FROM clients WHERE instr(casefold(name),?)>0 OR instr(phone,?)>0 ORDER BY id DESC',(q,q))
    data=client_values(body({'name','phone','notes'},{'name','phone'}))
    with transaction() as db:
        ident=db.execute('INSERT INTO clients(name,phone,notes,created_at) VALUES(?,?,?,?)',
                         (data['name'],data['phone'],data.get('notes',''),now())).lastrowid
    return jsonify(data=one('clients',ident)),201

@bp.route('/api/clients/<int:ident>', methods=['GET','PATCH','DELETE'])
def client_item(ident):
    if request.method=='GET': return jsonify(data=one('clients',ident))
    with transaction() as db:
        one('clients',ident)
        if request.method=='DELETE':
            if db.execute('SELECT 1 FROM vehicles WHERE client_id=? UNION ALL SELECT 1 FROM orders WHERE client_id=?',(ident,ident)).fetchone():
                raise Problem('referenced_client','Клієнт має пов’язані автомобілі або наряди.',409)
            db.execute('DELETE FROM clients WHERE id=?',(ident,))
            return '',204
        data=client_values(body({'name','phone','notes'}))
        if not data: raise Problem('empty_patch','Немає полів для оновлення.')
        db.execute('UPDATE clients SET '+','.join(f'{k}=?' for k in data)+' WHERE id=?',(*data.values(),ident))
    return jsonify(data=one('clients',ident))

def vehicle_values(data):
    out={}
    if 'plate' in data: out['plate_original'],out['plate']=plate(data['plate'])
    if 'vin' in data: out['vin']=vin(data['vin'])
    for k in ('make','model'):
        if k in data: out[k]=text(data[k],k,100)
    if 'client_id' in data:
        out['client_id']=identifier(data['client_id'],'client_id',True)
        if out['client_id'] is not None: one('clients',out['client_id'])
    return out

@bp.route('/api/vehicles', methods=['GET','POST'])
def vehicles():
    if request.method=='GET':
        q=query()
        try: normalized=plate(q)[1] if q else ''
        except Problem: normalized=q.upper()
        return listing('SELECT * FROM vehicles WHERE instr(plate,?)>0 OR instr(COALESCE(vin,\'\'),?)>0 ORDER BY id DESC',(normalized,q.upper()))
    data=vehicle_values(body({'plate','vin','make','model','client_id'},{'plate'}))
    with transaction() as db:
        ident=db.execute('INSERT INTO vehicles(plate_original,plate,vin,make,model,client_id,created_at) VALUES(?,?,?,?,?,?,?)',
                         (data['plate_original'],data['plate'],data.get('vin'),data.get('make',''),data.get('model',''),data.get('client_id'),now())).lastrowid
    return jsonify(data=one('vehicles',ident)),201

@bp.route('/api/vehicles/<int:ident>', methods=['GET','PATCH','DELETE'])
def vehicle_item(ident):
    if request.method=='GET': return jsonify(data=one('vehicles',ident))
    with transaction() as db:
        current=one('vehicles',ident)
        if request.method=='DELETE':
            if db.execute('SELECT 1 FROM orders WHERE vehicle_id=?',(ident,)).fetchone():
                raise Problem('referenced_vehicle','Автомобіль має історію нарядів.',409)
            db.execute('DELETE FROM vehicles WHERE id=?',(ident,))
            return '',204
        data=vehicle_values(body({'plate','vin','make','model','client_id'}))
        if not data: raise Problem('empty_patch','Немає полів для оновлення.')
        if data.get('plate',current['plate']) != current['plate'] and db.execute("SELECT 1 FROM orders WHERE vehicle_id=? AND status IN ('draft','ready','in_progress')",(ident,)).fetchone():
            raise Problem('active_order','Змініть номер після закриття активного наряду.',409)
        db.execute('UPDATE vehicles SET '+','.join(f'{k}=?' for k in data)+' WHERE id=?',(*data.values(),ident))
    return jsonify(data=one('vehicles',ident))

@bp.get('/api/vehicles/<int:ident>/orders')
def vehicle_orders(ident):
    one('vehicles',ident)
    return listing('SELECT * FROM orders WHERE vehicle_id=? ORDER BY id DESC',(ident,))

@bp.route('/api/orders', methods=['GET','POST'])
def order_list():
    if request.method=='POST':
        data=body({'plate','client_id','description','notes','confirmed'},{'plate','confirmed'})
        ident,created=orders.receive(data)
        return jsonify(data=orders.detail(ident),created=created),201 if created else 200
    q=query()
    try: q=plate(q)[1] if q else ''
    except Problem: q=q.upper()
    clauses=['instr(plate_snapshot,?)>0'];args=[q]
    if 'status' in request.args:
        if request.args['status'] not in orders.TRANSITIONS: raise Problem('invalid_status','Невідомий статус.')
        clauses.append('status=?');args.append(request.args['status'])
    start=day(request.args['date_from']) if 'date_from' in request.args else None
    end=day(request.args['date_to']) if 'date_to' in request.args else None
    if start and end and start>end: raise Problem('invalid_range','Початок періоду пізніший за кінець.')
    if start: clauses.append('substr(created_at,1,10)>=?');args.append(start)
    if end: clauses.append('substr(created_at,1,10)<=?');args.append(end)
    return listing('SELECT * FROM orders WHERE '+' AND '.join(clauses)+' ORDER BY id DESC',args)

@bp.route('/api/orders/<int:ident>', methods=['GET','PATCH'])
def order_item(ident):
    if request.method=='GET': return jsonify(data=orders.detail(ident))
    return jsonify(data=orders.update(ident,body({'client_id','description','notes'})))

@bp.patch('/api/orders/<int:ident>/status')
def order_status(ident):
    return jsonify(data=orders.transition(ident,body({'status','reason','confirmed'},{'status'})))
