"""Bounded local PDF/image extraction. Optional OCR never sends files to a service."""
import io
import os
import sys
from pathlib import Path
import shutil
import subprocess
import tempfile

MAX_BYTES = 20 * 1024 * 1024
MAX_TEXT = 100000
MAX_OCR_PAGES = 20

def _executable(name):
    return shutil.which(name) or next((str(Path(base) / name) for base in ('/opt/homebrew/bin', '/usr/local/bin') if (Path(base) / name).is_file()), None)

def _native_ocr_attempt(path, page=None):
    if sys.platform == 'darwin':
        helper = Path(os.environ.get('BENSON_MAIL_OCR', '')) if os.environ.get('BENSON_MAIL_OCR') else Path(sys.executable).resolve().parent.parent / 'MailOCR'
        if not helper.is_file(): return None
        args = [str(helper), str(path)] + ([str(page)] if page is not None else [])
        result = subprocess.run(args, capture_output=True, timeout=30)
        if result.returncode: return None
        text = result.stdout.decode('utf-8', errors='replace').strip()
        return '[OCR text; recognition may contain errors]\n' + text[:MAX_TEXT] if text else '[OCR found no readable text.]'
    if os.name == 'nt':
        # Windows 10/11 built-in OCR. Only a fixed script runs; paths pass through env.
        environment = dict(os.environ, BENSON_MAIL_OCR_IMAGE=str(path), BENSON_MAIL_OCR_PAGE=str(page or ''))
        import base64
        command = base64.b64encode(_WINDOWS_OCR_SCRIPT.encode('utf-16le')).decode('ascii')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', command], capture_output=True, timeout=35, env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode: return None
        text = result.stdout.decode('utf-8', errors='replace').strip()
        return '[OCR text; recognition may contain errors]\n' + text[:MAX_TEXT] if text else '[OCR found no readable text.]'
    return None


def _native_ocr(path, page=None):
    try:
        return _native_ocr_attempt(path, page)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ocr(path):
    native = _native_ocr(path)
    if native is not None: return native

    executable = _executable('tesseract')
    if not executable: return '[OCR unavailable: a local Tesseract OCR engine is not installed. Image content was not read.]'
    languages = subprocess.run([executable, '--list-langs'], capture_output=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    available = languages.stdout.decode('utf-8', errors='replace').splitlines()
    selected = [language for language in ('eng', 'spa', 'chi_sim') if language in available]
    args = [executable, str(path), 'stdout']
    if selected: args += ['-l', '+'.join(selected)]
    result = subprocess.run(args, capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode: return '[OCR failed: image text is unavailable.]'
    text = result.stdout.decode('utf-8', errors='replace').strip()
    return '[OCR text; recognition may contain errors]\n' + text[:MAX_TEXT] if text else '[OCR found no readable text.]'

def enhanced_text(name, data):
    """Return None for formats handled by existing Office/text parser."""
    suffix = Path(name).suffix.lower()
    if suffix not in ('.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'): return None
    if len(data) > MAX_BYTES: return '[Attachment exceeds 20 MB; contents were not read.]'
    try:
        if suffix != '.pdf':
            with tempfile.TemporaryDirectory(prefix='Mail-OCR-') as folder:
                path = Path(folder) / ('image' + suffix); path.write_bytes(data)
                return '[image:1]\n' + _ocr(path)
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data)); parts = []; size = 0; ocr_count = 0
        with tempfile.TemporaryDirectory(prefix='Mail-PDF-') as folder:
            source = Path(folder) / 'document.pdf'
            renderer = _executable('pdftoppm')
            for index, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ''
                if not text.strip():
                    if not source.exists(): source.write_bytes(data)
                    native = _native_ocr(source, index) if ocr_count < MAX_OCR_PAGES else None
                    if native is not None:
                        ocr_count += 1
                        text = native
                    elif renderer and _executable('tesseract') and ocr_count < MAX_OCR_PAGES:
                        if not source.exists(): source.write_bytes(data)
                        ocr_count += 1
                        base = Path(folder) / 'page'
                        result = subprocess.run([renderer, '-f', str(index), '-l', str(index), '-singlefile', '-scale-to', '2400', '-png', str(source), str(base)], capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        text = _ocr(base.with_suffix('.png')) if result.returncode == 0 else '[Page rendering failed; scanned content was not read.]'
                    else:
                        text = '[Scanned page: no text layer. Native OCR is unavailable or its language support is missing; optional local Tesseract and pdftoppm can also be used. At most 20 scanned pages are processed.]'
                part = f'[page:{index}]\n{text}'
                remaining = MAX_TEXT-size
                parts.append(part[:remaining]); size += len(part)
                if size >= MAX_TEXT:
                    parts.append('[Extraction truncated after 100000 characters; later content was not provided.]'); break
        return '\n\n'.join(parts)
    except Exception:
        return '[Attachment extraction failed: unreadable, encrypted, damaged or processing timed out. Contents were not inferred from the filename.]'

_WINDOWS_OCR_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument,Windows.Data.Pdf,ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfPageRenderOptions,Windows.Data.Pdf,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap,Windows.Foundation,ContentType=WindowsRuntime]
function Await($operation, $type) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
    $task = $method.MakeGenericMethod($type).Invoke($null, @($operation))
    $task.Wait()
    $task.Result
}
function AwaitAction($operation) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } | Select-Object -First 1
    $task = $method.Invoke($null, @($operation)); $task.Wait()
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:BENSON_MAIL_OCR_IMAGE)) ([Windows.Storage.StorageFile])
if ($env:BENSON_MAIL_OCR_PAGE) {
    $document = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
    $page = $document.GetPage([uint32]([int]$env:BENSON_MAIL_OCR_PAGE - 1))
    $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
    $options.DestinationWidth = [uint32][Math]::Min(2400, $page.Size.Width * 3)
    AwaitAction ($page.RenderToStreamAsync($stream, $options))
    $stream.Seek(0)
} else {
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
}
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { throw 'OCR language support is not installed.' }
$ocr = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
[Console]::Write($ocr.Text)
$stream.Dispose()
if ($page) { $page.Dispose() }
"""
