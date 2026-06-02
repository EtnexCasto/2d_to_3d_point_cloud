import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// --- 3D Viewer ---
const viewer = document.getElementById('viewer');
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, viewer.clientWidth/viewer.clientHeight, 0.1, 50);
camera.position.set(3, 2, 4);
const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
renderer.setSize(viewer.clientWidth, viewer.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
viewer.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotate = false;
controls.autoRotateSpeed = 0.5;
scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(5, 10, 7);
scene.add(dirLight);
scene.add(new THREE.GridHelper(3, 20, 0x333355, 0x1a1a2e));
scene.add(new THREE.AxesHelper(1.5));
let currentObject = null;

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
    camera.aspect = viewer.clientWidth / viewer.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(viewer.clientWidth, viewer.clientHeight);
});

function clearScene() {
    if (currentObject) {
        scene.remove(currentObject);
        if (currentObject.geometry) currentObject.geometry.dispose();
        if (currentObject.material) {
            if (Array.isArray(currentObject.material)) {
                currentObject.material.forEach(m => m.dispose());
            } else {
                currentObject.material.dispose();
            }
        }
        currentObject = null;
    }
}

function displayPointCloud(points) {
    clearScene();
    if (!points || points.length === 0) return;
    const positions = new Float32Array(points.length * 3);
    const colors = new Float32Array(points.length * 3);
    let cx = 0, cy = 0, cz = 0;
    points.forEach(p => { cx += p.x; cy += p.y; cz += p.z; });
    cx /= points.length; cy /= points.length; cz /= points.length;
    for (let i = 0; i < points.length; i++) {
        positions[i*3]   = points[i].x - cx;
        positions[i*3+1] = points[i].y - cy;
        positions[i*3+2] = points[i].z - cz;
        colors[i*3]     = points[i].r / 255;
        colors[i*3+1]   = points[i].g / 255;
        colors[i*3+2]   = points[i].b / 255;
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    const mat = new THREE.PointsMaterial({ size: 0.02, vertexColors: true, sizeAttenuation: true });
    currentObject = new THREE.Points(geom, mat);
    scene.add(currentObject);
    updateStats(points.length);
}

function updateStats(count) {
    document.getElementById('pointCount').textContent = count;
    document.getElementById('modeLabel').textContent = 'Облако точек';
    document.getElementById('stats').style.display = 'block';
}

// --- UI логика ---
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const thumbnailsDiv = document.getElementById('thumbnails');
const generateBtn = document.getElementById('generateBtn');
const clearBtn = document.getElementById('clearBtn');
const progressDiv = document.getElementById('progress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
let uploadedFiles = [];
let currentSessionId = null;
let statusInterval = null;

dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => addFiles(e.target.files));
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.style.borderColor = 'var(--accent)'; });
dropZone.addEventListener('dragleave', e => { dropZone.style.borderColor = 'rgba(255,255,255,0.2)'; });
dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.style.borderColor = 'rgba(255,255,255,0.2)';
    addFiles(e.dataTransfer.files);
});

function addFiles(files) {
    for (let f of files) {
        if (!f.type.startsWith('image/')) continue;
        uploadedFiles.push(f);
        const reader = new FileReader();
        reader.onload = e => {
            const img = document.createElement('img');
            img.src = e.target.result;
            img.className = 'thumb';
            img.title = f.name;
            img.onclick = () => {
                uploadedFiles = uploadedFiles.filter(fl => fl !== f);
                img.remove();
                updateUI();
            };
            thumbnailsDiv.appendChild(img);
        };
        reader.readAsDataURL(f);
    }
    updateUI();
}

function updateUI() {
    generateBtn.disabled = uploadedFiles.length < 3;
    clearBtn.style.display = uploadedFiles.length ? 'block' : 'none';
}

clearBtn.addEventListener('click', () => {
    uploadedFiles = [];
    thumbnailsDiv.innerHTML = '';
    updateUI();
    if (statusInterval) clearInterval(statusInterval);
    progressDiv.classList.remove('active');
    currentSessionId = null;
});

function startStatusPolling() {
    if (statusInterval) clearInterval(statusInterval);
    
    statusInterval = setInterval(async () => {
        try {
            const response = await fetch(`/status/${currentSessionId}`);
            const status = await response.json();
            
            const progress = status.progress || 0;
            progressFill.style.width = `${progress}%`;
            progressText.textContent = status.message || 'Обработка...';
            
            if (status.status === 'completed') {
                clearInterval(statusInterval);
                progressDiv.classList.remove('active');
                displayPointCloud(status.result.points);
                showToast('✅ 3D-модель готова!');
                generateBtn.disabled = false;
            } else if (status.status === 'error') {
                clearInterval(statusInterval);
                progressDiv.classList.remove('active');
                showToast('❌ ' + status.message);
                generateBtn.disabled = false;
            }
        } catch (error) {
            console.error('Status check error:', error);
        }
    }, 2000);
}

generateBtn.addEventListener('click', async () => {
    if (uploadedFiles.length < 3) return;
    
    const selectedMode = 'points';
    const formData = new FormData();
    uploadedFiles.forEach(f => formData.append('images', f));
    
    generateBtn.disabled = true;
    progressDiv.classList.add('active');
    progressFill.style.width = '0%';
    progressText.textContent = 'Отправка на сервер...';
    
    try {
        const url = `/generate?mode=${selectedMode}`;
        const response = await fetch(url, { method: 'POST', body: formData });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Ошибка сервера');
        }
        const data = await response.json();
        currentSessionId = data.session_id;
        startStatusPolling();
    } catch (e) {
        showToast('❌ ' + e.message);
        progressDiv.classList.remove('active');
        generateBtn.disabled = false;
    }
});

function showToast(msg) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
}

// Экспорт для глобального доступа
window.displayPointCloud = displayPointCloud;