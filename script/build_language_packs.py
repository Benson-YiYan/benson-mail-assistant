"""Build data-only packs and offline test fixtures from reviewed source translations."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LANGUAGES=('zh','en','es')

def payload(platform,code):
    folder=ROOT/('macos/Resources' if platform=='macos' else 'windows/native')
    catalog={'exact':{},'templates':[]} if code=='zh' else json.loads((folder/f'ui-{code}.json').read_text())
    docs=ROOT/('macos/Resources' if platform=='macos' else 'windows/docs')
    quick=docs/f'Quick-start-{code}.txt'
    return {'schema_version':1,'language':code,'platform':platform,**catalog,'guides':{
        'mail_account':(docs/f'Mail-account-setup-{code}.txt').read_text(),
        'quick_start':quick.read_text()}}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--release-directory',type=Path)
    parser.add_argument('--version',default=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d%H%M'))
    parser.add_argument('--tag',default='v20261020')
    args=parser.parse_args()
    entries={}
    for platform in ('windows','macos'):
        english=payload(platform,'en'); spanish=payload(platform,'es')
        if set(english['exact'])!=set(spanish['exact']):
            raise ValueError(f'{platform}: Spanish and English translation keys differ')
        if [r['pattern'] for r in english['templates']]!=[r['pattern'] for r in spanish['templates']]:
            raise ValueError(f'{platform}: Spanish template patterns differ')
        for code in LANGUAGES:
            data=(json.dumps(payload(platform,code),ensure_ascii=False,separators=(',',':'))+'\n').encode()
            path=args.output/platform/(code+'.json'); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
            if args.release_directory:
                name=f'BensonMail-Language-{platform}-{code}-{args.version}.json'
                args.release_directory.mkdir(parents=True,exist_ok=True)
                (args.release_directory/name).write_bytes(data)
                entries[platform+'-'+code]={'file':name,'version':args.version,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                    'mirrors':[f'https://github.com/Benson-YiYan/benson-mail-assistant/releases/download/{args.tag}/{name}']}
    if entries:
        (args.output/'language-catalog.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'ok':True,'packs':6,'output':str(args.output),'version':args.version}))

if __name__=='__main__': main()
