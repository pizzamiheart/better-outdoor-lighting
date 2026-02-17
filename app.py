"""
Flask application for RAW Photo Batch Processor.
"""

import os
import uuid
import time
import json
import threading
from pathlib import Path
from flask import (
    Flask, render_template, request, jsonify,
    send_file, Response
)
from werkzeug.utils import secure_filename

from processor import (
    process_raw, export_jpg, get_landscape_lighting_preset,
    get_default_settings
)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max upload

# Directories
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / 'uploads'
PROCESSED_DIR = BASE_DIR / 'processed'
UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

# In-memory storage for file tracking and batch progress
files_store = {}  # {file_id: {'path': path, 'filename': name, 'uploaded_at': time}}
batch_progress = {}  # {batch_id: {'total': n, 'current': i, 'status': str, 'done': bool}}

ALLOWED_EXTENSIONS = {'.cr3', '.cr2', '.nef', '.arw', '.dng', '.raw'}


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def cleanup_old_files(max_age_hours: float = 1.0):
    """Remove files older than max_age_hours."""
    cutoff = time.time() - (max_age_hours * 3600)

    # Clean uploads
    for file_id, info in list(files_store.items()):
        if info.get('uploaded_at', 0) < cutoff:
            try:
                Path(info['path']).unlink(missing_ok=True)
            except Exception:
                pass
            del files_store[file_id]

    # Clean processed files
    for f in PROCESSED_DIR.glob('*'):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


@app.route('/')
def index():
    """Serve the main UI."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    """
    Upload a CR3 file and return preview.
    Returns: {file_id, preview_url, filename}
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Supported: CR3, CR2, NEF, ARW, DNG'}), 400

    # Generate unique ID and save file
    file_id = str(uuid.uuid4())[:8]
    original_name = secure_filename(file.filename)
    ext = Path(original_name).suffix.lower()
    saved_path = UPLOAD_DIR / f"{file_id}{ext}"

    file.save(str(saved_path))

    # Store file info
    files_store[file_id] = {
        'path': str(saved_path),
        'filename': original_name,
        'uploaded_at': time.time(),
    }

    # Clean old files periodically
    if len(files_store) % 10 == 0:
        cleanup_old_files()

    return jsonify({
        'file_id': file_id,
        'filename': original_name,
        'preview_url': f'/preview/{file_id}',
    })


@app.route('/preview/<file_id>')
def preview(file_id: str):
    """
    Get preview image for a file with optional settings.
    Query params: exposure, warmth, contrast, shadows, sharpness
    """
    if file_id not in files_store:
        return jsonify({'error': 'File not found'}), 404

    # Parse settings from query params
    settings = get_default_settings()
    for key in settings:
        if key in request.args:
            try:
                settings[key] = float(request.args[key])
            except ValueError:
                pass

    # Process image
    try:
        path = files_store[file_id]['path']
        pil_img = process_raw(path, settings, preview=True, max_width=1200)
        jpg_bytes = export_jpg(pil_img, quality=80)

        return Response(jpg_bytes, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500


@app.route('/export/<file_id>', methods=['POST'])
def export_single(file_id: str):
    """
    Export a single file at full resolution.
    Request body: {settings: {...}}
    Returns: {download_url}
    """
    if file_id not in files_store:
        return jsonify({'error': 'File not found'}), 404

    data = request.get_json() or {}
    settings = data.get('settings', get_landscape_lighting_preset())

    try:
        path = files_store[file_id]['path']
        original_name = files_store[file_id]['filename']

        # Process at full resolution
        pil_img = process_raw(path, settings, preview=False, max_width=2000)

        # Save to processed folder
        output_name = Path(original_name).stem + '_processed.jpg'
        output_path = PROCESSED_DIR / f"{file_id}_{output_name}"
        export_jpg(pil_img, str(output_path), quality=85)

        return jsonify({
            'download_url': f'/download/{file_id}',
            'filename': output_name,
        })
    except Exception as e:
        return jsonify({'error': f'Export failed: {str(e)}'}), 500


@app.route('/download/<file_id>')
def download(file_id: str):
    """Download a processed file."""
    # Find processed file
    for f in PROCESSED_DIR.glob(f'{file_id}_*'):
        return send_file(
            str(f),
            mimetype='image/jpeg',
            as_attachment=True,
            download_name=f.name.replace(f'{file_id}_', '')
        )

    return jsonify({'error': 'File not found'}), 404


@app.route('/batch/start', methods=['POST'])
def batch_start():
    """
    Start batch processing.
    Request body: {file_ids: [...], settings: {...}, custom_filename: str|null}
    Returns: {batch_id}
    """
    data = request.get_json() or {}
    file_ids = data.get('file_ids', [])
    settings = data.get('settings', get_landscape_lighting_preset())
    custom_filename = data.get('custom_filename')  # Optional custom name

    if not file_ids:
        return jsonify({'error': 'No files provided'}), 400

    # Validate all files exist
    valid_ids = [fid for fid in file_ids if fid in files_store]
    if not valid_ids:
        return jsonify({'error': 'No valid files found'}), 404

    batch_id = str(uuid.uuid4())[:8]
    batch_progress[batch_id] = {
        'total': len(valid_ids),
        'current': 0,
        'current_file': '',
        'status': 'starting',
        'done': False,
        'results': [],
    }

    # Start processing in background thread
    def process_batch():
        for i, file_id in enumerate(valid_ids):
            batch_progress[batch_id]['current'] = i
            batch_progress[batch_id]['current_file'] = files_store[file_id]['filename']
            batch_progress[batch_id]['status'] = 'processing'

            try:
                path = files_store[file_id]['path']
                original_name = files_store[file_id]['filename']

                # Process at full resolution
                pil_img = process_raw(path, settings, preview=False, max_width=2000)

                # Determine output filename
                if custom_filename:
                    # Use custom name with sequence number for batch
                    if len(valid_ids) > 1:
                        output_name = f"{custom_filename}-{i+1:02d}.jpg"
                    else:
                        output_name = f"{custom_filename}.jpg"
                else:
                    # Use original name
                    output_name = Path(original_name).stem + '_processed.jpg'

                output_path = PROCESSED_DIR / f"{file_id}_{output_name}"
                export_jpg(pil_img, str(output_path), quality=85)

                batch_progress[batch_id]['results'].append({
                    'file_id': file_id,
                    'filename': output_name,
                    'download_url': f'/download/{file_id}',
                    'success': True,
                })
            except Exception as e:
                batch_progress[batch_id]['results'].append({
                    'file_id': file_id,
                    'filename': files_store[file_id]['filename'],
                    'error': str(e),
                    'success': False,
                })

        batch_progress[batch_id]['current'] = len(valid_ids)
        batch_progress[batch_id]['status'] = 'complete'
        batch_progress[batch_id]['done'] = True

    thread = threading.Thread(target=process_batch)
    thread.daemon = True
    thread.start()

    return jsonify({'batch_id': batch_id, 'total': len(valid_ids)})


@app.route('/batch/progress/<batch_id>')
def batch_status(batch_id: str):
    """Get batch processing progress (SSE stream)."""
    def generate():
        while True:
            if batch_id not in batch_progress:
                yield f"data: {json.dumps({'error': 'Batch not found'})}\n\n"
                break

            progress = batch_progress[batch_id]
            yield f"data: {json.dumps(progress)}\n\n"

            if progress['done']:
                break

            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream')


@app.route('/batch/download/<batch_id>')
def batch_download_all(batch_id: str):
    """Get list of download URLs for completed batch."""
    if batch_id not in batch_progress:
        return jsonify({'error': 'Batch not found'}), 404

    progress = batch_progress[batch_id]
    if not progress['done']:
        return jsonify({'error': 'Batch not complete'}), 400

    return jsonify({
        'results': progress['results'],
        'success_count': sum(1 for r in progress['results'] if r['success']),
        'total': progress['total'],
    })


@app.route('/preset/landscape-lighting')
def preset_landscape():
    """Get landscape lighting preset values."""
    return jsonify(get_landscape_lighting_preset())


@app.route('/preset/default')
def preset_default():
    """Get default settings."""
    return jsonify(get_default_settings())


@app.route('/files')
def list_files():
    """List all uploaded files."""
    return jsonify({
        'files': [
            {'file_id': fid, 'filename': info['filename']}
            for fid, info in files_store.items()
        ]
    })


@app.route('/files/<file_id>', methods=['DELETE'])
def delete_file(file_id: str):
    """Delete an uploaded file."""
    if file_id not in files_store:
        return jsonify({'error': 'File not found'}), 404

    try:
        Path(files_store[file_id]['path']).unlink(missing_ok=True)
        # Also delete any processed versions
        for f in PROCESSED_DIR.glob(f'{file_id}_*'):
            f.unlink(missing_ok=True)
        del files_store[file_id]
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'success': True})


if __name__ == '__main__':
    print("Starting RAW Photo Batch Processor...")
    print("Open http://localhost:5001 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)
