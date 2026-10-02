import re
from datetime import date
from flask import request

class Problem(Exception):
    def __init__(self, code, message, status=422, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details

def body(allowed, required=()):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise Problem('invalid_json', 'Потрібен JSON-об’єкт.', 400)
    if set(data) - set(allowed):
        raise Problem('unknown_fields', 'Невідомі поля.', details=sorted(set(data)-set(allowed)))
    if set(required) - set(data):
        raise Problem('missing_fields', 'Відсутні обов’язкові поля.', details=sorted(set(required)-set(data)))
    return data

def text(value, field, maximum=1000, required=False):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise Problem('invalid_field', f'Некоректне поле {field}.')
    value = value.strip()
    if required and not value:
        raise Problem('invalid_field', f'Заповніть поле {field}.')
    return value

def identifier(value, field='id', nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not int or not 1 <= value <= 9223372036854775807:
        raise Problem('invalid_id', f'Некоректний {field}.')
    return value

def phone(value):
    value = text(value, 'phone', 40, True)
    if not re.fullmatch(r'\+?[0-9 ()-]+', value):
        raise Problem('invalid_phone', 'Телефон повинен містити 7–15 цифр.')
    result = re.sub(r'\D', '', value)
    if not 7 <= len(result) <= 15:
        raise Problem('invalid_phone', 'Телефон повинен містити 7–15 цифр.')
    return result

MAP = str.maketrans('АВЕКМНОРСТУХІ', 'ABEKMHOPCTYXI')
def plate(value):
    original = text(value, 'plate', 40, True)
    normalized = re.sub(r'[\s-]', '', original.upper()).translate(MAP)
    if not re.fullmatch('[A-Z0-9]{3,12}', normalized):
        raise Problem('invalid_plate', 'Номер: 3–12 латинських літер або цифр.')
    return original, normalized

def vin(value):
    if value is None or value == '':
        return None
    value = text(value, 'vin', 17).upper()
    if not re.fullmatch('[A-HJ-NPR-Z0-9]{17}', value):
        raise Problem('invalid_vin', 'VIN повинен містити 17 символів без I, O, Q.')
    return value

def confirmed(value):
    if value is not True:
        raise Problem('confirmation_required', 'Потрібне явне підтвердження оператором.')

def pagination():
    try:
        limit, offset = int(request.args.get('limit', 50)), int(request.args.get('offset', 0))
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000000:
            raise ValueError
        return limit, offset
    except ValueError:
        raise Problem('invalid_pagination', 'limit: 1–100; offset: невід’ємне ціле.')

def query():
    return text(request.args.get('q', ''), 'q', 200)

def day(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise Problem('invalid_date', 'Дата має формат YYYY-MM-DD.')
