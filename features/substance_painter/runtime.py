"""Network work off the UI thread; Blender state touched only by a main-thread timer."""
import queue
import threading
import time
import bpy
from ...core.addon import get_prefs
from . import bridge, jobs

_pending = None
_generation = 0
_cancel = None


def cancel():
    if _cancel is not None:
        _cancel.set()


def busy():
    return _pending is not None


def start(context, action):
    global _pending, _cancel
    if busy():
        raise jobs.PainterError('A Painter connection/send request is already running')
    prefs = get_prefs(context)
    if prefs is None:
        raise jobs.PainterError('Enable MBToolkit to access Painter preferences')
    executable = bpy.path.abspath(prefs.painter_executable) if prefs.painter_executable else bridge.detect_executable()
    port = prefs.painter_port
    job_path = ''
    if action in {'SEND', 'BAKE_NEW', 'AUTO'}:
        context.scene.mbt_painter.report = 'Preparing mesh snapshots'
        jobs.prepare(context, automatic=action == 'AUTO')
        job_path = context.scene.mbt_painter.last_job
    elif action in {'EXPORT', 'BAKE'}:
        if context.mode != 'OBJECT':
            raise jobs.PainterError('Switch to Object Mode before export/import')
        job_path = bpy.path.abspath(context.scene.mbt_painter.last_job)
        jobs.read_job(job_path)
        if action == 'BAKE':
            jobs.update_bake_settings(job_path, context.scene.mbt_painter)
    scene = context.scene
    scene.mbt_painter.report = 'Connecting to Painter...'
    started = time.monotonic()
    stage = 'Connecting to Painter'
    results = queue.Queue()
    generation = _generation
    _pending = results
    cancellation = threading.Event()
    _cancel = cancellation if action in {'BAKE', 'BAKE_NEW', 'AUTO'} else None

    def progress(message):
        results.put((False, message))

    def work():
        try:
            client, info = bridge.connect(port, executable, allow_launch=action in {'SEND', 'CONNECT', 'BAKE_NEW', 'AUTO'}, progress=progress)
            if not info.get('can_create'):
                raise bridge.BridgeError('Painter is missing required APIs: ' + ', '.join(info.get('missing', [])))
            if cancellation.is_set():
                raise bridge.BridgeError('Workflow cancelled before project creation/baking')
            if action in {'SEND', 'BAKE_NEW', 'AUTO'}:
                result = bridge.send(client, job_path, progress=progress, update=action == 'AUTO')
                message = 'Painter project saved: ' + result['project_file'] + '. Baking has not been run.'
            if action in {'BAKE', 'BAKE_NEW', 'AUTO'}:
                if cancellation.is_set():
                    raise bridge.BridgeError('Workflow cancelled before baking')
                result = bridge.bake(client, job_path, cancel=cancellation, progress=progress)
                results.put((True, result))
                return
            elif action == 'EXPORT':
                progress('Exporting PBR textures from Painter')
                result = bridge.export_maps(client, job_path)
                results.put((True, result))
                return
            elif action != 'SEND':
                message = f"Connected to Painter (Python API {info['version']}); project open: {info['project_open']}; busy: {info['busy']}"
            results.put((True, message))
        except Exception as error:
            results.put((True, 'Failed — Painter: ' + str(error)))

    def poll():
        global _pending, _cancel
        nonlocal stage
        if generation != _generation:
            return None
        done = False
        while True:
            try:
                done, stage = results.get_nowait()
            except queue.Empty:
                break
            if done:
                break
        message = stage if done else f'{stage} ({int(time.monotonic() - started)}s)'
        if done:
            _pending = None
            _cancel = None
        try:
            if scene.name in bpy.data.scenes:
                if done and isinstance(message, dict):
                    try:
                        if scene != bpy.context.scene or bpy.path.abspath(scene.mbt_painter.last_job) != job_path:
                            raise jobs.PainterError('Active scene/job changed during export; import was skipped')
                        jobs.record_export(job_path, message)
                        if cancellation.is_set():
                            raise jobs.PainterError('Workflow cancelled during export; textures recorded but material import was skipped')
                        from . import materials
                        message = 'Exported from Painter. ' + materials.import_maps(bpy.context)
                    except Exception as error:
                        message = 'Export/import failed: ' + str(error)
                scene.mbt_painter.report = message
        except ReferenceError:
            pass  # File reload/deleted scene while the remote request was running.
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return None if done else 0.2

    threading.Thread(target=work, daemon=True).start()
    bpy.app.timers.register(poll, first_interval=0.2)


def cleanup():
    global _pending, _generation, _cancel
    cancel()
    _generation += 1
    _pending = None
    _cancel = None