from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from cv.video_input import VideoInputService


def test_sample_video_bundle_slowfast_profile():
    service = VideoInputService()
    temp_path = Path(tempfile.gettempdir()) / "captp_slowfast_test.mp4"

    writer = cv2.VideoWriter(str(temp_path), cv2.VideoWriter_fourcc(*"mp4v"), 12.0, (96, 96))
    for idx in range(36):
        frame = np.full((96, 96, 3), idx * 4, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    try:
        bundle = service.sample_video_bundle(temp_path.read_bytes(), max_frames=18, profile="slowfast")
    finally:
        temp_path.unlink(missing_ok=True)

    assert bundle["sample_profile"] == "slowfast"
    assert bundle["frames"]
    assert len(bundle["frames"]) <= 18


def test_video_sampling_budget_by_duration():
    service = VideoInputService()
    assert service.long_video_frame_budget(45.0) == 48
    assert service.long_video_frame_budget(180.0) == 72
    assert service.long_video_frame_budget(301.0) == 96
