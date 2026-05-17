from __future__ import annotations

import base64
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from schemas import AnalyzeMode, CombatSegmentManifestItem, RtspAnalyzeRequest, TacticalChatRequest, VideoAnalysisStrategy
from services.long_video_jobs import job_manager
from services.pipeline import pipeline
from services.reference_images import resolve_reference_image
from services.shooting_training import ShootingCoachSession
from settings import settings


DOCX_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
TACTICAL_CASES_DIR = settings.backend_root / "assets" / "cases"
PROJECT_ROOT = settings.backend_root.parent

app = FastAPI(title="CAPTP API", version="2.0.0")
shooting_coach_sessions: dict[int, ShootingCoachSession] = {}
reference_image_resolution = resolve_reference_image()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _decode_data_url(data: str) -> bytes:
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


def _encode_frame_b64(frame: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise HTTPException(status_code=500, detail="Unable to encode RTSP frame")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def _mode_from_legacy(mode: str) -> AnalyzeMode:
    normalized = (mode or "").strip().upper()
    if normalized in {"SHOOTING_POSTURE", "SHOOTING_WEAPON"}:
        return AnalyzeMode.shooting_posture
    if normalized in {"SHOOTING_TARGET", "SHOOTING_FLOW"}:
        return AnalyzeMode.shooting_flow
    if normalized == "COMBAT_FIGHT":
        return AnalyzeMode.combat_action
    return AnalyzeMode.combat_full


def _format_legacy_text(result) -> str:
    shooting = result.shooting
    combat = result.combat
    lines = [
        "综合评估结果",
        f"- 姿势合规: {'是' if shooting.posture_compliance else '否'} (score={shooting.posture_score:.2f})",
        f"- 射击流程阶段: {shooting.flow_stage.value}",
        f"- 流程序列正确: {'是' if shooting.flow_order_ok else '否'}",
    ]

    if shooting.violations:
        lines.append("- 姿势或安全问题:")
        for violation in shooting.violations:
            lines.append(f"  * [{violation.severity}] {violation.code}: {violation.description}")

    if combat.actions:
        lines.append("- 格斗动作:")
        for action in combat.actions[:6]:
            lines.append(f"  * {action.action} (conf={action.confidence:.2f})")

    if combat.quartets:
        lines.append("- 格斗四元组:")
        for quartet in combat.quartets[:4]:
            lines.append(f"  * <{quartet.action} | {quartet.effect} | {quartet.reason} | {quartet.suggestion}>")

    lines.append(f"- 体力状态: {combat.fatigue.level} (score={combat.fatigue.score:.2f})")
    lines.append(f"- 稳定性: {combat.stability:.2f}")
    lines.append(f"- 识别人数: {result.meta.persons}, 设备: {result.meta.device}, fallback={result.meta.fallback_used}")
    if result.reasoning:
        lines.append("- 推理补充:")
        lines.append(result.reasoning)
    return "\n".join(lines)


@app.post("/api/v2/analyze/file")
async def analyze_file_v2(file: UploadFile = File(...), mode: AnalyzeMode = Form(AnalyzeMode.combat_full)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    result = pipeline.analyze_file(content=content, filename=file.filename or "", content_type=file.content_type or "", mode=mode)
    return result.model_dump()


@app.post("/api/v2/analyze/long-video")
async def analyze_long_video_v2(file: UploadFile = File(...), mode: AnalyzeMode = Form(AnalyzeMode.combat_full)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = pipeline.analyze_long_video(content=content, filename=file.filename or "", content_type=file.content_type or "", mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/api/v2/analyze/combat-preview")
async def analyze_combat_preview_v2(
    frames: list[UploadFile] = File(...),
    mode: AnalyzeMode = Form(AnalyzeMode.combat_full),
    duration_seconds: float = Form(0.0),
):
    decoded_frames = []
    for frame_file in frames:
        content = await frame_file.read()
        if not content:
            continue
        decoded_frames.append(pipeline.video_input.decode_image(content))

    if not decoded_frames:
        raise HTTPException(status_code=400, detail="No valid preview frames")

    result = pipeline.analyze_combat_preview(decoded_frames, mode=mode, duration_seconds=duration_seconds)
    return result.model_dump()


@app.post("/api/v2/analyze/combat-video-fast")
async def analyze_combat_video_fast_v2(
    frames: list[UploadFile] = File(...),
    mode: AnalyzeMode = Form(AnalyzeMode.combat_full),
    strategy: VideoAnalysisStrategy = Form(VideoAnalysisStrategy.adaptive),
    duration_seconds: float = Form(0.0),
    client_extract_ms: float = Form(0.0),
    manifest: str = Form("[]"),
):
    try:
        manifest_items = [CombatSegmentManifestItem.model_validate(item) for item in json.loads(manifest)]
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid combat manifest") from exc

    decoded_by_name: dict[str, np.ndarray] = {}
    for frame_file in frames:
        content = await frame_file.read()
        if not content:
            continue
        decoded = pipeline.video_input.decode_image(content)
        if frame_file.filename:
            decoded_by_name[frame_file.filename] = decoded

    if not decoded_by_name:
        raise HTTPException(status_code=400, detail="No valid combat frames")

    segment_frames: list[list[np.ndarray]] = []
    for item in manifest_items:
        grouped_frames = []
        for filename in item.filenames:
            frame = decoded_by_name.get(filename)
            if frame is None:
                raise HTTPException(status_code=400, detail=f"Missing frame {filename} in manifest")
            grouped_frames.append(frame)
        segment_frames.append(grouped_frames)

    try:
        result = pipeline.analyze_combat_video_fast(
            segment_frames=segment_frames,
            manifest=manifest_items,
            mode=mode,
            strategy=strategy,
            duration_seconds=duration_seconds,
            client_extract_ms=client_extract_ms,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/api/v2/analyze/long-video/jobs")
async def create_long_video_job_v2(file: UploadFile = File(...), mode: AnalyzeMode = Form(AnalyzeMode.combat_full)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    job = job_manager.create_job(content=content, filename=file.filename or "", content_type=file.content_type or "", mode=mode)
    return job.model_dump()


@app.get("/api/v2/analyze/long-video/jobs/{job_id}")
async def get_long_video_job_v2(job_id: str):
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()


@app.post("/api/v2/analyze/frame")
async def analyze_frame_v2(
    file: UploadFile = File(...),
    mode: AnalyzeMode = Form(AnalyzeMode.combat_full),
    frame_index: int = Form(0),
    fps: float = Form(0.0),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty frame")

    frame = pipeline.video_input.decode_image(content)
    result = pipeline.analyze_frame(frame=frame, mode=mode, frame_index=frame_index, fps=fps)
    return result.model_dump()


@app.post("/api/v2/analyze/rtsp-frame")
async def analyze_rtsp_frame_v2(request: RtspAnalyzeRequest):
    if not request.url.strip():
        raise HTTPException(status_code=400, detail="RTSP URL is required")

    try:
        frame = pipeline.video_input.capture_rtsp_frame(request.url.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = pipeline.analyze_frame(frame=frame, mode=request.mode, frame_index=request.frame_index, fps=request.fps)
    return {
        "analysis": result.model_dump(),
        "frame_b64": _encode_frame_b64(frame),
    }


@app.websocket("/api/v2/stream/analyze")
async def analyze_stream_v2(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            mode = AnalyzeMode(data.get("mode", AnalyzeMode.combat_full))
            frame_b64 = data.get("frame")
            frame_index = int(data.get("frame_index", 0))
            fps = float(data.get("fps", 0.0))

            if not frame_b64:
                await websocket.send_json({"error": "missing frame"})
                continue

            frame_bytes = _decode_data_url(frame_b64)
            frame = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                await websocket.send_json({"error": "invalid frame"})
                continue

            result = pipeline.analyze_frame(frame=frame, mode=mode, frame_index=frame_index, fps=fps)
            await websocket.send_json(result.model_dump())
    except WebSocketDisconnect:
        return


@app.websocket("/api/v2/stream/shooting-coach")
async def shooting_coach_stream(websocket: WebSocket):
    await websocket.accept()
    session = ShootingCoachSession(standard_ref_url=reference_image_resolution.selected_url)
    shooting_coach_sessions[id(websocket)] = session
    try:
        await websocket.send_json({"event": "stage:update", "data": {"stage": session.machine.stage.value}})
        while True:
            packet = await websocket.receive_json()
            events = session.process_packet(packet)
            for event in events:
                await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    finally:
        shooting_coach_sessions.pop(id(websocket), None)


@app.get("/api/v2/health/models")
def model_health():
    return pipeline.model_health()


@app.get("/api/v2/reference-image")
def reference_image():
    return {
        "url": reference_image_resolution.selected_url,
        "fallback_used": reference_image_resolution.fallback_used,
        "reason": reference_image_resolution.reason,
    }


@app.post("/api/analyze-vision")
async def analyze_vision(file: UploadFile = File(...), mode: str = Form("SHOOTING_POSTURE")):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="No file found")

    result = pipeline.analyze_file(content=content, filename=file.filename or "", content_type=file.content_type or "", mode=_mode_from_legacy(mode))
    return {"result": _format_legacy_text(result)}


@app.post("/api/tactical-chat")
async def tactical_chat(request: TacticalChatRequest):
    scenario = (request.scenario or "常规道路拦截盘查").strip()
    last_user = next((message.content for message in reversed(request.messages) if message.role == "user"), "请说明你当前的处置动作。")
    response = (
        f"现场反馈：基于场景《{scenario}》，你当前处置已经形成初步控制。\n"
        "处置点评：重点应当是先稳控、再分工，避免过早贴近高风险对象。\n"
        f"下一问题：在你刚才“{last_user[:40]}”之后，准备如何安排证据固定和通道管制责任人？"
    )
    return {"result": response}


def _pick_case_docx() -> Path | None:
    if not TACTICAL_CASES_DIR.exists():
        return None
    docx_files = sorted(TACTICAL_CASES_DIR.glob("*.docx"))
    if not docx_files:
        return None
    return docx_files[0]


def _extract_docx_lines(file_path: Path) -> list[str]:
    with zipfile.ZipFile(file_path) as archive:
        xml_bytes = archive.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    lines: list[str] = []
    for paragraph in root.findall(".//w:p", DOCX_NAMESPACE):
        pieces = [node.text or "" for node in paragraph.findall(".//w:t", DOCX_NAMESPACE)]
        merged = "".join(pieces).strip()
        if merged:
            lines.append(merged)
    return lines


def _parse_tactical_cases(lines: list[str]) -> list[dict]:
    title_pattern = re.compile(r"""^[“"'‘]?\d{1,2}\.\s?\d{1,2}[”"'’]?""")
    question_bank = [
        "请先概括该案例的核心警情和第一处置目标。",
        "如果你是第一到场警力，你会如何做首轮口头控制和分工？",
        "在不贸然强攻的前提下，你准备如何创造接触窗口并控制升级风险？",
        "结合本案，请复盘一条关键成功经验和一条可优化策略。",
    ]

    def is_case_title(text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        return bool(title_pattern.match(compact))

    def normalize_title(text: str) -> str:
        normalized = text.strip().replace("“", "").replace("”", "").replace("‘", "").replace("’", "").replace('"', "").replace("'", "")
        return re.sub(r"(\d)\.\s+(\d)", r"\1.\2", normalized)

    title_indices = [index for index, line in enumerate(lines) if is_case_title(line)]
    cases = []
    for case_index, start_index in enumerate(title_indices):
        end_index = title_indices[case_index + 1] if case_index + 1 < len(title_indices) else len(lines)
        material_lines = [line.strip() for line in lines[start_index + 1 : end_index] if line.strip()]
        cases.append(
            {
                "id": f"case-{case_index + 1}",
                "title": normalize_title(lines[start_index]),
                "material": "\n".join(material_lines[:12]),
                "questions": question_bank,
            }
        )

    if cases:
        for case in cases:
            normalized_title = re.sub(r"\s+", "", case["title"])
            if normalized_title.startswith("3.21"):
                case["material"] = "1.mp4"
                case["mediaType"] = "video"
                case["mediaUrl"] = "/api/tactical-media/1.mp4"
        return cases

    return [
        {
            "id": "case-1",
            "title": "题库案例",
            "material": "\n".join(lines[:8]),
            "questions": ["你会如何做第一轮处置？"],
        }
    ]


@app.get("/api/tactical-cases")
def tactical_cases():
    file_path = _pick_case_docx()
    if file_path is None:
        raise HTTPException(status_code=404, detail="未找到战术题库文档")

    lines = _extract_docx_lines(file_path)
    return {"source": file_path.name, "cases": _parse_tactical_cases(lines)}


@app.get("/api/tactical-media/{filename}")
def tactical_media(filename: str):
    if Path(filename).name != filename or not filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Invalid media filename")

    media_path = (PROJECT_ROOT / filename).resolve()
    if media_path.parent != PROJECT_ROOT.resolve() or not media_path.exists():
        raise HTTPException(status_code=404, detail="Media not found")

    return FileResponse(media_path, media_type="video/mp4", filename=media_path.name)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "2.0.0", "device": settings.device}


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
