"""Local-only Adobe remote scripting transport. No Blender API calls here."""
import base64
import http.client
import json
import os
import socket
from pathlib import Path
import subprocess
import time


class BridgeError(RuntimeError):
    pass


class ConnectionUnavailable(BridgeError):
    pass


def detect_executable():
    root = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
    candidates = [root / 'Adobe/Adobe Substance 3D Painter/Adobe Substance 3D Painter.exe']
    steam = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))
    candidates.extend((steam / 'Steam/steamapps/common').glob('*Painter*/*Painter*.exe'))
    return next((str(path) for path in candidates if path.is_file()), '')


class Client:
    def __init__(self, port=60041, timeout=5):
        self.port = int(port)
        self.timeout = timeout
        self.host = '127.0.0.1'

    def execute(self, expression):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        body = json.dumps({'python': base64.b64encode(expression.encode('utf-8')).decode('ascii')})
        try:
            connection.request('POST', '/run.json', body, {'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = response.read(1024 * 1024).decode('utf-8').strip()
            if response.status != 200:
                raise BridgeError(f'Painter HTTP {response.status}: {data[:300]}')
            # Remote Python returns expression text; our expressions serialize explicitly.
            result = json.loads(data)
            if isinstance(result, str):
                result = json.loads(result)
            if not isinstance(result, dict):
                raise BridgeError(f'Unexpected Painter response: {data[:300]}')
            if result.get('error'):
                raise BridgeError(str(result['error']))
            return result
        except (OSError, http.client.HTTPException) as error:
            raise ConnectionUnavailable(f'Cannot reach Painter at [{self.host}]:{self.port}. '
                              'Launch Painter with remote scripting enabled. ' + str(error)) from error
        except (ValueError, TypeError) as error:
            raise BridgeError(f'Invalid Painter response: {data[:300]}') from error
        finally:
            connection.close()

    def install(self):
        source = Path(__file__).with_name('painter_remote.py').read_text(encoding='utf-8')
        return self.execute(f"(exec({source!r}, globals()), _mbt_probe())[1]")

    def check_endpoint(self):
        errors = []
        for host in ('127.0.0.1', '::1'):
            try:
                with socket.create_connection((host, self.port), timeout=self.timeout):
                    self.host = host
                return
            except OSError as error:
                errors.append(str(error))
        raise ConnectionUnavailable(f'No Painter endpoint on IPv4/IPv6 localhost port {self.port}: '
                                    + '; '.join(errors))

    def handshake(self, progress):
        progress('Checking remote endpoint')
        self.check_endpoint()
        progress('Checking remote Python response')
        if self.execute('__import__("json").dumps({"mbt_ping": 1})').get('mbt_ping') != 1:
            raise BridgeError('Endpoint responded, but the Python handshake was not recognized')
        progress('Checking Painter project API')
        return self.install()


def launch(executable):
    path = Path(executable)
    if not path.is_file() or path.suffix.lower() != '.exe':
        raise BridgeError('Choose the Painter executable in MBToolkit preferences')
    # No shell, no project argument, no process termination.
    environment = {key: value for key, value in os.environ.items() if key.upper() != 'OCIO'}
    return subprocess.Popen([str(path), '--enable-remote-scripting'], cwd=str(path.parent), env=environment)


def connect(port, executable='', allow_launch=False, startup_timeout=90, progress=lambda message: None):
    client = Client(port)
    try:
        return client, client.handshake(progress)
    except ConnectionUnavailable:
        if not allow_launch:
            raise
    if int(port) != 60041:
        raise BridgeError('Automatic launch uses Painter\'s default port 60041; custom ports are connect-only')
    progress('Launching Painter (without inherited OCIO override)')
    process = launch(executable)
    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        try:
            client.check_endpoint()
        except ConnectionUnavailable as error:
            if process.poll() is not None:
                raise BridgeError('Painter launcher exited before connecting. If Painter is already running '
                                  'without remote scripting, close it yourself and try again.')
            time.sleep(1)
            progress('Waiting for Painter remote endpoint')
            continue
        # A responding endpoint with a script/API error is not a startup retry.
        return client, client.handshake(progress)
    raise BridgeError('Painter startup timed out. Check license/startup dialogs; Painter was left running.')


def send(client, job_path, timeout=180, progress=lambda message: None, update=False):
    progress('Creating Painter project (waiting for remote response)')
    previous_timeout = client.timeout
    client.timeout = timeout
    try:
        result = client.execute(f'{"_mbt_update" if update else "_mbt_create"}({str(job_path)!r})')
    finally:
        client.timeout = previous_timeout
    deadline = time.monotonic() + timeout
    while result.get('state') in {'CREATING', 'OPENING', 'RELOADING', 'RELOADED'}:
        progress('Waiting for Painter project edition state / save')
        if time.monotonic() >= deadline:
            raise BridgeError('Project creation timed out. Check Painter before retrying; no request was resent.')
        time.sleep(0.5)
        result = client.execute('_mbt_status()')
    if result.get('state') != 'COMPLETE':
        raise BridgeError(str(result))
    return result


def export_maps(client, job_path, timeout=180):
    previous = client.timeout
    client.timeout = timeout
    try:
        result = client.execute(f'_mbt_export({str(job_path)!r})')
    finally:
        client.timeout = previous
    if result.get('state') != 'EXPORTED':
        raise BridgeError(str(result))
    return result


def bake(client, job_path, cancel=None, progress=lambda message: None, timeout=1800):
    if cancel is not None and cancel.is_set():
        raise BridgeError('Workflow cancelled before baking; no export/import was started')
    progress('Configuring Painter baking')
    result = client.execute(f'_mbt_bake({str(job_path)!r})')
    deadline = time.monotonic() + timeout
    cancellation_sent = False
    while result.get('state') == 'BAKING':
        if time.monotonic() >= deadline:
            raise BridgeError('Bake status uncertain: timed out. Inspect Painter; no export/import was started.')
        if cancel is not None and cancel.is_set() and not cancellation_sent:
            response = client.execute('_mbt_cancel_bake()')
            cancellation_sent = response.get('cancel_requested', False)
        progress(('Cancellation requested — ' if cancellation_sent else '') +
                 f"Baking — {float(result.get('progress', 0)) * 100:.0f}%")
        time.sleep(0.5)
        result = client.execute('_mbt_bake_status()')
    if result.get('state') != 'BAKED':
        raise BridgeError('Bake ' + str(result) + '; no export/import was started')
    if cancel is not None and cancel.is_set():
        raise BridgeError('Cancelled workflow after baking; no export/import was started')
    progress('Saving baked Painter project')
    saved = client.execute(f'_mbt_save_baked({str(job_path)!r})')
    while saved.get('state') == 'WAITING':
        if time.monotonic() >= deadline:
            raise BridgeError('Post-bake save timed out; no export/import was started')
        time.sleep(0.5)
        saved = client.execute(f'_mbt_save_baked({str(job_path)!r})')
    if saved.get('state') != 'SAVED':
        raise BridgeError('Bake save not confirmed; no export/import was started')
    if cancel is not None and cancel.is_set():
        raise BridgeError('Workflow cancelled before export/import')
    progress('Exporting baked textures')
    return export_maps(client, job_path)