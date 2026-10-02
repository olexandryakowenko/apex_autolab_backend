#!/usr/bin/env python3
"""Local backend entry point. Never run restore while the server is active."""
import argparse
import getpass
import json
import os
from pathlib import Path
from apex import create_app
from apex.locking import process_lock
from apex.validation import Problem

def main():
    parser=argparse.ArgumentParser(description='APEX AutoLab Reception — локальний Back-end')
    parser.add_argument('--data-dir',default=os.environ.get('APEX_DATA_DIR',str(Path(__file__).parent/'instance')))
    commands=parser.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init-admin');init.add_argument('--username',default='operator')
    serve=commands.add_parser('serve');serve.add_argument('--port',type=int,default=8765)
    commands.add_parser('backup')
    restore=commands.add_parser('restore');restore.add_argument('archive');restore.add_argument('--confirm',action='store_true')
    args=parser.parse_args()
    if args.command=='restore' and not args.confirm:
        parser.error('Відновлення замінює поточні дані. Перевірте архів і додайте --confirm. Поточну базу буде збережено окремо.')
    if args.command=='serve' and not 1024<=args.port<=65535: parser.error('Порт: 1024–65535.')
    try:
        with process_lock(args.data_dir):
            app=create_app({'DATA_DIR':str(Path(args.data_dir).resolve())})
            if args.command=='serve':
                from waitress import serve
                print(f'API: http://127.0.0.1:{args.port} (Ctrl+C — зупинити)',flush=True)
                serve(app,host='127.0.0.1',port=args.port,threads=4,max_request_body_size=11*1024*1024)
            else:
                with app.app_context():
                    if args.command=='init-admin':
                        from apex.auth import create_operator
                        password=getpass.getpass('Пароль (від 12 символів): ')
                        if password!=getpass.getpass('Повторіть пароль: '): parser.error('Паролі не збігаються.')
                        create_operator(args.username,password)
                        print('Оператора створено.')
                    elif args.command=='backup':
                        from apex.backup import create_backup
                        print(json.dumps(create_backup(),ensure_ascii=False))
                    else:
                        from apex.backup import restore_backup
                        safety=restore_backup(Path(args.archive).resolve())
                        print('Відновлено. Страхувальна копія:',safety['id'])
    except (Problem,RuntimeError) as exc:
        parser.exit(1,str(exc.message if isinstance(exc,Problem) else exc)+'\n')

if __name__=='__main__': main()
