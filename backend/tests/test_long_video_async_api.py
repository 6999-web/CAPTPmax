from __future__ import annotations

import io
import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from main import app
from schemas import AnalyzeMode, AnalyzeResult, CombatResult, MetaResult, ShootingResult
from services.long_video_jobs import job_manager
from services.pipeline import VisionPipeline, pipeline


def _encode_jpeg_bytes(frame: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def _dummy_result(phase: str, is_final: bool) -> AnalyzeResult:
    return AnalyzeResult(
        shooting=ShootingResult(),
        combat=CombatResult(supported_actions=[]),
        meta=MetaResult(device="cpu", analysis_phase=phase, is_final=is_final),
        reasoning=None,
        attribution=None,
    )


def test_combat_preview_api(monkeypatch):
    frames_seen = {}

    def fake_preview(frames, mode, duration_seconds):
        frames_seen["count"] = len(frames)
        frames_seen["mode"] = mode
        frames_seen["duration"] = duration_seconds
        return _dummy_result("preview", False)

    monkeypatch.setattr(pipeline, "analyze_combat_preview", fake_preview)
    client = TestClient(app)
    frame = np.zeros((96, 96, 3), dtype=np.uint8)
    files = [
        ("frames", ("a.jpg", io.BytesIO(_encode_jpeg_bytes(frame)), "image/jpeg")),
        ("frames", ("b.jpg", io.BytesIO(_encode_jpeg_bytes(frame)), "image/jpeg")),
    ]
    response = client.post(
        "/api/v2/analyze/combat-preview",
        files=files,
        data={"mode": "combat_full", "duration_seconds": "12.5"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["analysis_phase"] == "preview"
    assert payload["meta"]["is_final"] is False
    assert frames_seen == {"count": 2, "mode": AnalyzeMode.combat_full, "duration": 12.5}


def test_long_video_job_lifecycle(monkeypatch):
    def fake_async_final(content, filename, content_type, mode, progress_callback=None):
        if progress_callback is not None:
            progress_callback(35)
            progress_callback(100)
        return _dummy_result("final", True)

    monkeypatch.setattr(pipeline, "analyze_long_video_async_final", fake_async_final)
    client = TestClient(app)
    video_bytes = b"fake-video"
    response = client.post(
        "/api/v2/analyze/long-video/jobs",
        files={"file": ("demo.mp4", io.BytesIO(video_bytes), "video/mp4")},
        data={"mode": "combat_full"},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    deadline = time.time() + 5
    status = None
    payload = None
    while time.time() < deadline:
        poll = client.get(f"/api/v2/analyze/long-video/jobs/{job_id}")
        assert poll.status_code == 200
        payload = poll.json()
        status = payload["status"]
        if status == "completed":
            break
        time.sleep(0.05)

    assert status == "completed"
    assert payload["progress"] == 100
    assert payload["result"]["meta"]["analysis_phase"] == "final"


def test_combat_mode_skips_shooting_work(monkeypatch):
    p = VisionPipeline()
    frames = [np.zeros((120, 160, 3), dtype=np.uint8) for _ in range(3)]
    calls = {"weapon": 0, "posture": 0, "event": 0, "reasoning": 0}

    def fail_weapon(frame):
        calls["weapon"] += 1
        raise AssertionError("weapon path should be skipped")

    def fail_posture(*args, **kwargs):
        calls["posture"] += 1
        raise AssertionError("shooting posture path should be skipped")

    def fail_event(*args, **kwargs):
        calls["event"] += 1
        raise AssertionError("shooting flow path should be skipped")

    def fail_reasoning(*args, **kwargs):
        calls["reasoning"] += 1
        raise AssertionError("reasoning path should be skipped")

    monkeypatch.setattr(p.weapon_engine, "infer", fail_weapon)
    monkeypatch.setattr(p.shooting_rules, "evaluate_posture", fail_posture)
    monkeypatch.setattr(p.shooting_rules, "infer_flow_event", fail_event)
    monkeypatch.setattr(p.reasoning, "enrich", fail_reasoning)

    out = p._analyze_sequence_internal(frames, mode=AnalyzeMode.combat_full, fps=12.0, analysis_phase="preview", is_final=False)
    assert out.meta.analysis_phase == "preview"
    assert out.reasoning is None
    assert calls == {"weapon": 0, "posture": 0, "event": 0, "reasoning": 0}


def test_pose_batch_infer_shape_and_fallback(monkeypatch):
    p = VisionPipeline()
    frames = [np.zeros((64, 64, 3), dtype=np.uint8), np.zeros((64, 64, 3), dtype=np.uint8)]

    def fake_predict(frames, **kwargs):
        raise RuntimeError("boom")

    if p.pose_engine._yolo is None:
        class StubModel:
            def predict(self, *args, **kwargs):
                return fake_predict(*args, **kwargs)

        p.pose_engine._yolo = StubModel()
    else:
        monkeypatch.setattr(p.pose_engine._yolo, "predict", fake_predict)
    results = p.pose_engine.infer_batch(frames)

    assert len(results) == 2
    assert all(item.fallback_used for item in results)
    assert all(item.persons for item in results)
