from flask import Blueprint, request, jsonify, render_template, send_from_directory, current_app
from app.photogrammetry import PhotogrammetryProcessor
from pathlib import Path
import time
import threading
import uuid

bp = Blueprint('main', __name__)

processing_status = {}

@bp.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@bp.route('/style.css')
def serve_css():
    """Отдача CSS файла"""
    return send_from_directory('static/css', 'style.css')

@bp.route('/static/js/<path:filename>')
def serve_js(filename):
    """Отдача JS файлов"""
    return send_from_directory('static/js', filename)

@bp.route('/generate', methods=['POST'])
def generate():
    """
    Запуск 3D реконструкции по загруженным фотографиям
    """
    mode = request.args.get('mode', 'points')
    
    if 'images' not in request.files:
        return jsonify({'error': 'Нет файлов'}), 400
    
    files = request.files.getlist('images')
    if len(files) < 3:
        return jsonify({'error': 'Минимум 3 изображения'}), 400
    
    session_id = str(int(time.time()))
    upload_folder = Path(current_app.config['UPLOAD_FOLDER']) / session_id
    upload_folder.mkdir(exist_ok=True, parents=True)

    for file in files:
        if file.filename:
            filename = file.filename
            file.save(str(upload_folder / filename))

    processor = PhotogrammetryProcessor(session_id, upload_folder, mode)
    thread = threading.Thread(target=processor.process)
    thread.daemon = True
    thread.start()
    
    return jsonify({'session_id': session_id, 'message': 'Обработка начата'})

@bp.route('/status/<session_id>', methods=['GET'])
def get_status(session_id):
    status = processing_status.get(session_id, {
        'status': 'processing',
        'message': 'Инициализация...',
        'progress': 0
    })
    return jsonify(status)