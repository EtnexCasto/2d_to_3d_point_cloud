from flask import Flask
from flask_cors import CORS
import os
from pathlib import Path

def create_app():
    """Фабрика приложений Flask"""
    app = Flask(__name__, 
                static_folder='static',
                template_folder='templates')
    
    # Конфигурация
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'data/uploads')
    app.config['PROCESSING_FOLDER'] = os.environ.get('PROCESSING_FOLDER', 'data/processing')
    app.config['OUTPUT_FOLDER'] = os.environ.get('OUTPUT_FOLDER', 'data/outputs')
    app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
    
    CORS(app)
    
    for folder in [app.config['UPLOAD_FOLDER'], 
                   app.config['PROCESSING_FOLDER'], 
                   app.config['OUTPUT_FOLDER']]:
        Path(folder).mkdir(exist_ok=True, parents=True)
    
    
    from app.server import bp
    app.register_blueprint(bp)
    
    return app