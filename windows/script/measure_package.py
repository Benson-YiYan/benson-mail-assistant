"""Measure actual unpacked payload bytes, independent of installer compression."""
import argparse
from collections import defaultdict
import json
from pathlib import Path


def measure(folder):
    root = Path(folder)
    files = [path for path in root.rglob('*') if path.is_file()]
    totals = defaultdict(int)
    sizes = []
    for path in files:
        size = path.stat().st_size
        relative = path.relative_to(root)
        category = ('python_worker' if relative.parts[0] == '_internal' or path.name == 'MailWorker.exe' else
                    'app_and_uninstaller' if path.name.startswith(('BensonMail-', 'Uninstall-BensonMail-')) and path.suffix == '.exe' else
                    'native_runtime_and_winui' if path.suffix.lower() in ('.dll', '.pri', '.pdb', '.json') else 'resources_and_guides')
        totals[category] += size
        sizes.append({'path': relative.as_posix(), 'bytes': size})
    return {'bytes': sum(row['bytes'] for row in sizes), 'files': len(files),
            'components': dict(totals), 'largest_files': sorted(sizes, key=lambda row: row['bytes'], reverse=True)[:30]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder'); parser.add_argument('output')
    parser.add_argument('--baseline'); parser.add_argument('--baseline-commit')
    args=parser.parse_args()
    report=measure(args.folder)
    root=Path(args.folder)
    runtime_config=json.loads((root/'BensonMail.runtimeconfig.json').read_text(encoding='utf-8'))
    runtime_options=runtime_config['runtimeOptions']
    frameworks=runtime_options.get('frameworks', [])
    if runtime_options.get('framework'):
        frameworks.append(runtime_options['framework'])
    assert any(item['name']=='Microsoft.NETCore.App' and item['version']=='8.0.32'
               for item in frameworks), 'Framework-dependent .NET 8.0.32 runtime configuration missing'
    assert runtime_options.get('rollForward')=='LatestPatch', 'Runtime must accept newer .NET 8.0 patches only'
    assert not runtime_options.get('includedFrameworks'), 'Self-contained .NET framework metadata still present'
    for filename in ('coreclr.dll', 'hostfxr.dll', 'hostpolicy.dll', 'System.Private.CoreLib.dll',
                     'Microsoft.UI.Xaml.dll', 'Microsoft.WindowsAppRuntime.dll'):
        assert not (root/filename).exists(), 'Shared runtime unexpectedly bundled: '+filename
    assert (root/'Microsoft.WindowsAppRuntime.Bootstrap.dll').is_file(), 'Official WinAppSDK bootstrapper missing'
    report['deployment']='Framework-dependent .NET 8 x64 and Windows App SDK 1.8'
    if args.baseline_commit: report['baseline_commit']=args.baseline_commit
    if args.baseline:
        baseline=json.loads(Path(args.baseline).read_text(encoding='utf-8'))
        report['baseline']=baseline
        report['saved_bytes']=baseline['bytes']-report['bytes']
        report['saved_percent']=round(report['saved_bytes']*100/baseline['bytes'],2)
        if report['saved_bytes'] < 20*1024*1024:
            raise AssertionError('Slim package must save at least 20 MiB compared with the recorded previous release')
        for filename in ('System.Windows.Forms.dll','PresentationFramework.dll','PresentationCore.dll'):
            assert not (root/filename).exists(), 'Unneeded Windows Desktop runtime still present: '+filename
        for name in ('_tcl_data','_tk_data','tkinter','PIL','pystray'):
            assert not (root/'_internal'/name).exists(), 'Legacy GUI dependency still present: '+name
        assert not list(root.rglob('*.pdb')), 'Debug symbols unexpectedly included'
        report['checks']=['Measured current payload bytes against the recorded previous release baseline',
                          'Shared .NET 8 and Windows App SDK runtime payloads absent; official bootstrapper retained',
                          'Legacy Python GUI resources and debug symbols absent']
    target=Path(args.output); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('bytes','files','components','saved_bytes','saved_percent') if key in report}))


if __name__=='__main__': main()
