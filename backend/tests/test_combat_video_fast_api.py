from __future__ import annotations

import io

import cv2
import numpy as np
from fastapi.testclient import TestClient

from cv.types import FramePoseResult, FrameWeaponResult
from main import app
from schemas import AnalyzeMode, AnalyzeResult, CombatActionItem, CombatResult, HitEvent, MetaResult, ShootingResult
from services.pipeline import CombatSegmentArtifacts, VisionPipeline, pipeline


def _encode_jpeg_bytes(frame: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def _dummy_result() -> AnalyzeResult:
    return AnalyzeResult(
        shooting=ShootingResult(),
        combat=CombatResult(supported_actions=[]),
        meta=MetaResult(device="cpu", analysis_phase="final", is_final=True),
        reasoning=None,
        attribution=None,
    )


def test_combat_video_fast_api(monkeypatch):
    seen = {}

    def fake_fast(segment_frames, manifest, mode, strategy, duration_seconds, client_extract_ms=0.0):
        seen["segments"] = [len(item) for item in segment_frames]
        seen["manifest_ids"] = [item.segment_id for item in manifest]
        seen["mode"] = mode
        seen["strategy"] = strategy.value
        seen["duration_seconds"] = duration_seconds
        seen["client_extract_ms"] = client_extract_ms
        return _dummy_result()

    monkeypatch.setattr(pipeline, "analyze_combat_video_fast", fake_fast)
    client = TestClient(app)
    frame = np.zeros((96, 96, 3), dtype=np.uint8)
    files = [
        ("frames", ("seg-0-a.jpg", io.BytesIO(_encode_jpeg_bytes(frame)), "image/jpeg")),
        ("frames", ("seg-0-b.jpg", io.BytesIO(_encode_jpeg_bytes(frame)), "image/jpeg")),
        ("frames", ("seg-1-a.jpg", io.BytesIO(_encode_jpeg_bytes(frame)), "image/jpeg")),
    ]
    manifest = [
        {
            "segment_id": 0,
            "start_seconds": 0.0,
            "end_seconds": 6.0,
            "frame_times_seconds": [0.1, 1.1],
            "filenames": ["seg-0-a.jpg", "seg-0-b.jpg"],
        },
        {
            "segment_id": 1,
            "start_seconds": 5.0,
            "end_seconds": 10.0,
            "frame_times_seconds": [5.3],
            "filenames": ["seg-1-a.jpg"],
        },
    ]
    response = client.post(
        "/api/v2/analyze/combat-video-fast",
        files=files,
        data={
            "mode": "combat_full",
            "strategy": "five_way",
            "duration_seconds": "10.0",
            "client_extract_ms": "321.5",
            "manifest": __import__("json").dumps(manifest),
        },
    )

    assert response.status_code == 200
    assert seen == {
        "segments": [2, 1],
        "manifest_ids": [0, 1],
        "mode": AnalyzeMode.combat_full,
        "strategy": "five_way",
        "duration_seconds": 10.0,
        "client_extract_ms": 321.5,
    }


def test_merge_combat_segments_dedupes_overlaps():
    p = VisionPipeline()
    frame = np.zeros((48, 48, 3), dtype=np.uint8)
    merged = p._merge_combat_segments(
        [
        CombatSegmentArtifacts(
            segment_id=0,
            frames=[frame, frame],
            frame_times_seconds=[0.5, 1.0],
            pose_seq=[FramePoseResult(fallback_used=True), FramePoseResult(fallback_used=True)],
            weapon_seq=[FrameWeaponResult(fallback_used=True), FrameWeaponResult(fallback_used=True)],
            actions=[CombatActionItem(action="straight_punch", confidence=0.6, actor_id=0, frame_index=1)],
            hits=[HitEvent(attacker_id=0, defender_id=1, target="head", confidence=0.51, frame_index=1)],
            fallback_used=True,
            performance={},
        ),
        CombatSegmentArtifacts(
            segment_id=1,
            frames=[frame, frame],
            frame_times_seconds=[1.2, 1.8],
            pose_seq=[FramePoseResult(fallback_used=True), FramePoseResult(fallback_used=True)],
            weapon_seq=[FrameWeaponResult(fallback_used=True), FrameWeaponResult(fallback_used=True)],
            actions=[CombatActionItem(action="straight_punch", confidence=0.9, actor_id=0, frame_index=0)],
            hits=[HitEvent(attacker_id=0, defender_id=1, target="head", confidence=0.83, frame_index=0)],
            fallback_used=True,
            performance={},
        ),
        ],
        duration_seconds=2.0,
    )

    assert len(merged["actions"]) == 1
    assert merged["actions"][0].confidence == 0.9
    assert len(merged["hits"]) == 1
    assert merged["hits"][0].confidence == 0.83
    assert [item.frame_index for item in merged["actions"]] == sorted(item.frame_index for item in merged["actions"])
