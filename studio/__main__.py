"""Run: python3 -m studio [--port 8768] [--open]."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import webbrowser
from .server import Server


def main():
    parser=argparse.ArgumentParser(description='Atelier, studio de montage · studio local')
    parser.add_argument('command',nargs='?',choices=['serve','doctor'],default='serve')
    parser.add_argument('--port',type=int,default=8768)
    parser.add_argument('--data-dir',default=os.environ.get('STUDIO_DATA_DIR',str(Path(__file__).resolve().parent.parent/'.studio-data')))
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    if args.command=='doctor':
        from . import setup
        # Same checklist as the Réglages page: required tools, transcription, fonts.
        items=setup.requirements(Path(args.data_dir))
        missing=[i['label'] for i in items if i['required'] and not i['available']]
        report={'ready':not missing,'missing':missing,'requirements':[{k:i.get(k) for k in ('label','group','required','available','detail','install')} for i in items]}
        print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(1 if missing else 0)
    server=Server(('127.0.0.1',args.port),args.data_dir)
    url=f'http://localhost:{server.server_port}'
    print(f'Atelier, studio de montage · {url}\nProjets : {server.store.root}\nCtrl+C pour arrêter.',flush=True)
    if args.open:threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(f'Erreur : {exc}',file=sys.stderr);sys.exit(1)
