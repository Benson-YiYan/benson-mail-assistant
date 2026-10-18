"""Validate packaged update preparation in a disposable synthetic install location."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

project=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project/'Runtime'))
from update_install import architectures
app=Path(sys.argv[1]).resolve();image=Path(sys.argv[2]).resolve();evidence=Path(sys.argv[3]).resolve()
evidence.mkdir(parents=True,exist_ok=True)
info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
arch=architectures(app/'Contents/MacOS/BensonMailMac')[0]
worker=app/'Contents/Resources/worker/MailWorker'
checks=[]
with tempfile.TemporaryDirectory(prefix='BensonMail-update-fixture-') as temporary:
 root=Path(temporary);workspace=root/'workspace';workspace.mkdir()
 target=root/'Synthetic original.app';target.mkdir();(target/'sentinel').write_text('original app remains')
 home=root/'isolated-data';home.mkdir();(home/'settings.json').write_text('{"enabled":true,"fixture":"configuration retained"}')
 request=dict(workspace=str(workspace),target=str(target),dmg=str(image),version=info['CFBundleVersion'],arch=arch,parent_pid=os.getpid(),marker=str(home/'worker-installation.json'),sha256=hashlib.sha256(image.read_bytes()).hexdigest(),size=image.stat().st_size)
 input_file=workspace/'request.json';output=workspace/'result.json'
 def prepare(value):
  input_file.write_text(json.dumps(value))
  result=subprocess.run([str(worker),'--home',str(home),'--update-install','prepare',str(input_file),str(output)],capture_output=True,text=True,timeout=180)
  return result,json.loads(output.read_text())
 bad=dict(request,sha256='0'*64)
 process,result=prepare(bad)
 assert process.returncode and not result['ok'] and 'SHA256 mismatch' in result['error'],result
 assert (target/'sentinel').read_text()=='original app remains'
 checks.append('packaged helper rejects wrong image SHA before mounting and preserves synthetic original')
 process,result=prepare(request)
 assert process.returncode==0 and result['ok'],result
 plan=json.loads(Path(result['plan']).read_text());stage=Path(plan['stage'])
 assert stage.is_dir() and plan['version']==info['CFBundleVersion'] and plan['arch']==arch
 assert plan['nonce'] and Path(result['helper']).is_file()
 relocated=subprocess.run([result['helper'],'--home',str(home),'--diagnose'],capture_output=True,text=True,check=True,timeout=30)
 assert json.loads(relocated.stdout)['frozen'] is True
 assert architectures(stage/'Contents/MacOS/BensonMailMac')==architectures(app/'Contents/MacOS/BensonMailMac')
 assert not os.path.ismount(workspace/'mount')
 assert (target/'sentinel').read_text()=='original app remains'
 assert json.loads((home/'settings.json').read_text())['enabled'] is True
 checks.append('actual DMG mounted read-only, checked bundle/version/architecture/deep signature, staged beside synthetic target, then detached')
 subprocess.run([str(worker),'--home',str(home),'--update-install','abort',result['plan']],check=True,capture_output=True,timeout=30)
 assert not stage.exists() and target.is_dir()
 checks.append('aborting preparation removes only staging; original app and fixture configuration preserved')
(evidence/'update-prepare-result.json').write_text(json.dumps(dict(ok=True,architecture=arch,version=info['CFBundleVersion'],checks=checks),indent=2))
print(json.dumps(dict(ok=True,architecture=arch,checks=checks),indent=2))
