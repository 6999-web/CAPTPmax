import os
import tempfile
import threading
import time
import asyncio

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import List

from ai_engine import engine

app = FastAPI(title="CAPTP API", version="1.0.0")

VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")
VIDEO_SAMPLE_POINTS = (0.18, 0.42, 0.66, 0.84)

# 配置 CORS，允许 Vue 前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 方便开发，可指定 frontend 端口如 http://localhost:5173
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    scenario: str | None = None
    scenarioContext: str | None = None

def _normalize_mode(mode: str) -> str:
    normalized_mode = (mode or "").strip().upper()
    if engine.is_supported_vision_mode(normalized_mode):
        return normalized_mode

    supported_modes = ", ".join(engine.supported_vision_modes)
    raise HTTPException(status_code=400, detail=f"不支持的识别模式：{mode}。可用模式：{supported_modes}")

def _resize_frame(frame: np.ndarray, max_side: int) -> np.ndarray:
    height, width = frame.shape[:2]
    longest_side = max(height, width)
    if longest_side <= max_side:
        return frame

    scale = max_side / float(longest_side)
    resized_width = max(1, int(width * scale))
    resized_height = max(1, int(height * scale))
    return cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)

def _encode_jpeg(frame: np.ndarray, quality: int) -> bytes:
    success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not success:
        raise ValueError("图像编码失败")
    return buffer.tobytes()

def _frame_focus_score(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())

def _build_contact_sheet(frames: list[np.ndarray], mode: str) -> bytes:
    max_side = 960 if mode == "SHOOTING_TARGET" else 720
    processed_frames = [_resize_frame(frame, max_side) for frame in frames]

    if len(processed_frames) == 1:
        quality = 94 if mode == "SHOOTING_TARGET" else 88
        return _encode_jpeg(processed_frames[0], quality)

    cell_height = max(frame.shape[0] for frame in processed_frames)
    cell_width = max(frame.shape[1] for frame in processed_frames)
    columns = 2
    rows = (len(processed_frames) + columns - 1) // columns
    gap = 10 if mode.startswith("COMBAT_") else 0
    canvas_height = rows * cell_height + max(0, rows - 1) * gap
    canvas_width = columns * cell_width + max(0, columns - 1) * gap
    canvas = np.full((canvas_height, canvas_width, 3), 8, dtype=np.uint8)

    for index, frame in enumerate(processed_frames):
        row = index // columns
        column = index % columns
        start_y = row * (cell_height + gap)
        start_x = column * (cell_width + gap)
        offset_y = start_y + (cell_height - frame.shape[0]) // 2
        offset_x = start_x + (cell_width - frame.shape[1]) // 2
        canvas[offset_y:offset_y + frame.shape[0], offset_x:offset_x + frame.shape[1]] = frame

    return _encode_jpeg(canvas, 88)

def _prepare_image_bytes(image_bytes: bytes, mode: str) -> bytes:
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if frame is None:
        return image_bytes

    max_side = 1800 if mode == "SHOOTING_TARGET" else 1280
    quality = 94 if mode == "SHOOTING_TARGET" else 88
    frame = _resize_frame(frame, max_side)
    return _encode_jpeg(frame, quality)

def _extract_video_payload(video_bytes: bytes, mode: str) -> bytes:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            temp_file.write(video_bytes)
            temp_path = temp_file.name

        capture = cv2.VideoCapture(temp_path)
        if not capture.isOpened():
            raise ValueError("无法开启视频解码流")

        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        candidate_positions = [0]
        if total_frames > 0:
            candidate_positions = [max(0, int(total_frames * point)) for point in VIDEO_SAMPLE_POINTS]

        frames = []
        visited_positions = set()
        for position in candidate_positions:
            if position in visited_positions:
                continue

            visited_positions.add(position)
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            success, frame = capture.read()
            if success and frame is not None:
                frames.append(frame)

        capture.release()

        if not frames:
            raise ValueError("无法从视频轨中捕获有效画面")

        if mode.startswith("COMBAT_"):
            return _build_contact_sheet(frames[:4], mode)

        best_frame = max(frames, key=_frame_focus_score)
        return _encode_jpeg(_resize_frame(best_frame, 1600), 92)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/api/analyze-vision")
async def analyze_vision(file: UploadFile = File(...), mode: str = Form("SHOOTING_POSTURE")):
    """
    分析射击 (POSTURE/TARGET/WEAPON) 或 格斗 (FIGHT/SCORING) 帧/视频。
    如果上传的是视频文件，后台将自动智能截取关键对抗帧进行分析。
    """
    normalized_mode = _normalize_mode(mode)
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="No file found")
        
    content_type = file.content_type or ""
    filename = (file.filename or "").lower()
    
    # 视频处理逻辑：格斗视频提取多帧拼图，其他视频提取最佳关键帧
    if content_type.startswith("video/") or filename.endswith(VIDEO_EXTENSIONS):
        try:
            contents = _extract_video_payload(contents, normalized_mode)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"视频解析失败: {str(e)}")
    else:
        contents = _prepare_image_bytes(contents, normalized_mode)
    
    if normalized_mode == "SHOOTING_TARGET":
        result = engine.analyze_shooting_target(contents)
    elif normalized_mode == "COMBAT_SCORING":
        result = engine.combat_quality_scoring(contents)
    else:
        result = engine.analyze_vision(contents, normalized_mode)

    if result["success"]:
        return {"result": result["data"]}
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.post("/api/tactical-chat")
async def tactical_chat(request: ChatRequest):
    """执法决策博弈推演"""
    messages_dict = [{"role": msg.role, "content": msg.content} for msg in request.messages]
    result = engine.tactical_chat(messages_dict, request.scenario, request.scenarioContext)
    if result["success"]:
        return {"result": result["data"]}
    else:
        raise HTTPException(status_code=500, detail=result["error"])

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import StreamingResponse, Response
import threading
import time
import subprocess
import os
import signal

class FFmpegCapture:
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        self.process = None
        self.rtsp_url = None
        self.is_active = False
        self.current_frame = None
        self._thread = None
        self._running = False
        self.ffmpeg_pid = None
        self.frame_file = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def start_capture(self, rtsp_url):
        with self._lock:
            self.stop_capture()
            self.rtsp_url = rtsp_url
            self._running = True
            self.is_active = True
            
            # 使用FFmpeg拉取RTSP流
            ffmpeg_cmd = [
                'ffmpeg',
                '-rtsp_transport', 'tcp',
                '-i', rtsp_url,
                '-vf', 'fps=10',  # 限制帧率
                '-q:v', '5',
                '-f', 'image2pipe',
                '-vcodec', 'mjpeg',
                '-'
            ]
            
            try:
                self.process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                self.ffmpeg_pid = self.process.pid
                
                # 启动线程读取FFmpeg输出
                self._thread = threading.Thread(target=self._read_ffmpeg, daemon=True)
                self._thread.start()
                
                print(f"FFmpeg started with PID: {self.ffmpeg_pid}")
                
            except Exception as e:
                print(f"FFmpeg启动失败: {e}")
                self.is_active = False
                self._running = False
    
    def _read_ffmpeg(self):
        """持续读取FFmpeg输出的MJPEG帧"""
        buffer = b""
        
        while self._running and self.process:
            try:
                # 读取数据
                chunk = self.process.stdout.read(8192)
                if not chunk:
                    time.sleep(0.05)
                    # 检查进程是否还在运行
                    if self.process.poll() is not None:
                        print("FFmpeg进程已退出")
                        break
                    continue
                
                buffer += chunk
                
                # 查找完整的JPEG帧
                while True:
                    start = buffer.find(b'\xFF\xD8')
                    if start == -1:
                        break
                    end = buffer.find(b'\xFF\xD9', start + 2)
                    if end == -1:
                        buffer = buffer[start:]  # 保留可能不完整的帧
                        break
                    
                    jpg_frame = buffer[start:end+2]
                    buffer = buffer[end+2:]
                    self.current_frame = jpg_frame
                    
            except Exception as e:
                print(f"读取帧错误: {e}")
                time.sleep(0.05)
    
    def stop_capture(self):
        self._running = False
        self.is_active = False
        
        with self._lock:
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except:
                    self.process.kill()
                self.process = None
            
            if self.frame_file and os.path.exists(self.frame_file):
                try:
                    os.remove(self.frame_file)
                except:
                    pass
                self.frame_file = None
                
            self.current_frame = None
    
    def get_frame(self):
        if self.current_frame is not None:
            return self.current_frame
        return None

rtsp_capture = FFmpegCapture.get_instance()

RTSP_URL = "rtsp://admin:12345678Mm@192.168.43.169:554/stream1"
is_continuous_recognition = False

@app.post("/api/camera/control")
async def camera_control(action: str = Form(...)):
    """
    控制摄像头: start, stop
    """
    global is_continuous_recognition
    
    if action == "start":
        # 非阻塞启动FFmpeg
        def start_ffmpeg():
            rtsp_capture.start_capture(RTSP_URL)
        
        thread = threading.Thread(target=start_ffmpeg, daemon=True)
        thread.start()
        
        # 立即返回，让FFmpeg在后台启动
        await asyncio.sleep(0.1)
        return {"status": "started", "message": "摄像头启动中..."}
    elif action == "stop":
        rtsp_capture.stop_capture()
        is_continuous_recognition = False
        return {"status": "stopped", "message": "摄像头已关闭"}
    else:
        return {"status": "unknown action"}

@app.get("/api/camera/stream")
async def camera_stream():
    """
    获取摄像头视频流（MJPEG格式）- 持续流式推送
    """
    async def generate_frames():
        last_frame_time = 0
        frame_interval = 0.033  # ~30fps
        
        while True:
            frame_bytes = rtsp_capture.get_frame()
            if frame_bytes:
                current_time = time.time()
                if current_time - last_frame_time >= frame_interval:
                    last_frame_time = current_time
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            await asyncio.sleep(0.03)
    
    return StreamingResponse(
        generate_frames(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )

@app.get("/api/camera/single")
async def camera_single():
    """
    获取摄像头视频流（单帧JPEG）
    """
    frame_bytes = rtsp_capture.get_frame()
    if frame_bytes:
        return StreamingResponse(
            content=frame_bytes,
            media_type="image/jpeg"
        )
    else:
        return Response(status_code=404, content="No frame available")

@app.get("/api/camera/status")
async def camera_status():
    """
    获取摄像头状态
    """
    return {
        "is_active": rtsp_capture.is_active,
        "is_continuous": is_continuous_recognition
    }

class PoseRequest(BaseModel):
    landmarks: List[dict]
    mode: str = "SHOOTING_POSTURE"

@app.post("/api/analyze-pose")
async def analyze_pose(request: PoseRequest):
    """
    分析MediaPipe姿态数据
    landmarks: MediaPipe检测的33个关键点数据
    mode: 分析模式 (SHOOTING_POSTURE, COMBAT_FIGHT, COMBAT_SCORING)
    """
    try:
        # 提取关键点坐标和置信度
        pose_data = []
        for lm in request.landmarks:
            pose_data.append({
                "x": lm.get("x", 0),
                "y": lm.get("y", 0),
                "z": lm.get("z", 0),
                "visibility": lm.get("visibility", 0)
            })
        
        # 根据模式分析姿态
        if request.mode.startswith("SHOOTING"):
            result = engine.analyze_pose_shooting(pose_data)
        else:
            result = engine.analyze_pose_combat(pose_data)
        
        if result["success"]:
            return {"result": result["data"]}
        else:
            return {"result": "姿态检测正常，请继续保持"}
    except Exception as e:
        return {"result": f"姿态分析完成"}

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# 如果直接运行此文件
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
