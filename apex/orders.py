"""Business rules for reception and immutable completed orders."""
import uuid
from .db import get_db, one, transaction, now
from .validation import Problem, identifier, confirmed, plate, text

ACTIVE = ('draft','ready','in_progress')
CLOSED = ('completed','cancelled')
TRANSITIONS = {'draft':{'ready','cancelled'}, 'ready':{'draft','in_progress','cancelled'},
               'in_progress':{'completed','cancelled'}, 'completed':set(), 'cancelled':set()}

def missing(order):
    fields = []
    if not order['client_id']:
        fields.extend(['client_id','client_name','client_phone'])
    else:
        client = one('clients', order['client_id'])
        if not client['name'].strip(): fields.append('client_name')
        if not 7 <= len(client['phone']) <= 15: fields.append('client_phone')
    if not order['description'].strip(): fields.append('description')
    return fields

def detail(ident):
    order = one('orders', ident)
    order['confirmed'] = bool(order['confirmed'])
    order['missing_fields'] = missing(order) if order['status']=='draft' else []
    order['history'] = [dict(x) for x in get_db().execute('SELECT * FROM status_history WHERE order_id=? ORDER BY id', (ident,))]
    order['attachments'] = [dict(x) for x in get_db().execute('SELECT id,order_id,mime_type,bytes,created_at FROM attachments WHERE order_id=? ORDER BY id',(ident,))]
    return order

def receive(data):
    confirmed(data.get('confirmed'))
    original, normalized = plate(data['plate'])
    description = text(data.get('description',''), 'description', 2000)
    notes = text(data.get('notes',''), 'notes', 4000)
    if 'client_id' in data:
        identifier(data['client_id'], 'client_id', True)
        if data['client_id'] is not None: one('clients', data['client_id'])
    with transaction() as db:
        vehicle = db.execute('SELECT * FROM vehicles WHERE plate=?', (normalized,)).fetchone()
        if vehicle:
            active = db.execute("SELECT id FROM orders WHERE vehicle_id=? AND status IN ('draft','ready','in_progress')", (vehicle['id'],)).fetchone()
            if active:
                return active['id'], False
            vehicle_id, client_id = vehicle['id'], vehicle['client_id']
        else:
            vehicle_id = db.execute('INSERT INTO vehicles(plate_original,plate,created_at) VALUES(?,?,?)', (original,normalized,now())).lastrowid
            client_id = None
        client_id = data.get('client_id', client_id)
        stamp = now()
        ident = db.execute('INSERT INTO orders(number,vehicle_id,client_id,plate_snapshot,description,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                           ('APX-'+uuid.uuid4().hex.upper(),vehicle_id,client_id,normalized,description,notes,stamp,stamp)).lastrowid
        db.execute('INSERT INTO status_history(order_id,new_status,created_at) VALUES(?,?,?)', (ident,'draft',stamp))
    return ident, True

def update(ident, data):
    with transaction() as db:
        order = one('orders', ident)
        if order['status'] in CLOSED:
            raise Problem('closed_order', 'Закритий наряд не редагується.', 409)
        if order['status']=='in_progress' and set(data)-{'notes'}:
            raise Problem('immutable_fields', 'У роботі можна змінювати лише примітки.', 409)
        values = {}
        for field, maximum in [('description',2000),('notes',4000)]:
            if field in data: values[field] = text(data[field],field,maximum)
        if 'client_id' in data:
            values['client_id'] = identifier(data['client_id'],'client_id',True)
            if values['client_id'] is not None: one('clients', values['client_id'])
        if not values:
            raise Problem('empty_patch', 'Немає полів для оновлення.')
        if {'client_id','description'} & set(values):
            values.update(confirmed=0, client_name=None, client_phone=None)
            if order['status']=='ready':
                values['status'] = 'draft'
                db.execute('INSERT INTO status_history(order_id,previous_status,new_status,reason,created_at) VALUES(?,?,?,?,?)',
                           (ident,'ready','draft','Зміна даних потребує підтвердження.',now()))
        values['updated_at'] = now()
        db.execute('UPDATE orders SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?', (*values.values(),ident))
    return detail(ident)

def transition(ident, data):
    status = text(data['status'], 'status', 30, True)
    if status not in TRANSITIONS:
        raise Problem('invalid_status', 'Невідомий статус.')
    reason = text(data.get('reason',''), 'reason', 1000)
    with transaction() as db:
        order = one('orders', ident)
        if status not in TRANSITIONS[order['status']]:
            raise Problem('invalid_transition', 'Такий перехід статусу заборонено.', 409)
        if status=='cancelled':
            confirmed(data.get('confirmed'))
            if not reason: raise Problem('reason_required', 'Вкажіть причину скасування.')
        if status=='ready':
            confirmed(data.get('confirmed'))
            fields = missing(order)
            if fields: raise Problem('incomplete_order', 'Заповніть дані перед початком робіт.', details=fields)
            client = one('clients', order['client_id'])
            db.execute('UPDATE orders SET client_name=?,client_phone=?,confirmed=1 WHERE id=?', (client['name'],client['phone'],ident))
        if status=='in_progress':
            if not (order['confirmed'] and order['client_id'] and order['client_name'] and order['client_phone'] and order['description']):
                raise Problem('incomplete_order', 'Дані клієнта не підтверджено.')
        if status=='draft':
            db.execute('UPDATE orders SET status=?,confirmed=0,client_name=NULL,client_phone=NULL WHERE id=?', ('draft',ident))
        stamp = now()
        db.execute('UPDATE orders SET status=?,updated_at=? WHERE id=?',(status,stamp,ident))
        db.execute('INSERT INTO status_history(order_id,previous_status,new_status,reason,created_at) VALUES(?,?,?,?,?)',
                   (ident,order['status'],status,reason,stamp))
    return detail(ident)
