from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np


VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")


class VideoInputService:
    def decode_image(self, data: bytes) -> np.ndarray:
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Invalid image input")
        return frame

    def capture_rtsp_frame(self, url: str) -> np.ndarray:
        cap = cv2.VideoCapture(url)
        try:
            if not cap.isOpened():
                raise ValueError("Unable to open RTSP stream")
            ok, frame = cap.read()
            if not ok or frame is None:
                raise ValueError("Unable to read frame from RTSP stream")
            return frame
        finally:
            cap.release()

    def sample_video_frames(
        self,
        data: bytes,
        max_frames: int = 24,
        max_duration_seconds: float | None = None,
    ) -> tuple[list[np.ndarray], float]:
        bundle = self.sample_video_bundle(data, max_frames=max_frames, max_duration_seconds=max_duration_seconds)
        return bundle["frames"], bundle["fps"]

    def inspect_video(self, data: bytes) -> dict:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp:
            temp.write(data)
            path = Path(temp.name)

        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                raise ValueError("Unable to open video stream")

            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            cap.release()
            duration_seconds = (total / fps) if fps > 0 and total > 0 else 0.0
            return {"total_frames": total, "fps": fps, "duration_seconds": duration_seconds}
        finally:
            path.unlink(missing_ok=True)

    def sample_video_bundle(
        self,
        data: bytes,
        max_frames: int = 24,
        profile: str = "uniform",
        sequential: bool = False,
        max_duration_seconds: float | None = None,
    ) -> dict:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp:
            temp.write(data)
            path = Path(temp.name)

        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                raise ValueError("Unable to open video stream")

            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            duration_seconds = (total / fps) if fps > 0 and total > 0 else 0.0
            effective_total = total
            effective_duration_seconds = duration_seconds
            if max_duration_seconds is not None and max_duration_seconds > 0:
                effective_duration_seconds = min(duration_seconds, float(max_duration_seconds)) if duration_seconds > 0 else float(max_duration_seconds)
                if fps > 0 and total > 0:
                    effective_total = min(total, max(1, int(fps * float(max_duration_seconds))))
            indices = self._build_indices(total=effective_total, max_frames=max_frames, profile=profile)

            frames = self._collect_frames(cap=cap, indices=indices, sequential=sequential)

            cap.release()
            if not frames:
                raise ValueError("No valid frame decoded from video")

            return {
                "frames": frames,
                "fps": fps,
                "total_frames": effective_total,
                "duration_seconds": effective_duration_seconds,
                "sample_profile": profile,
                "indices": indices,
            }
        finally:
            path.unlink(missing_ok=True)

    def long_video_frame_budget(self, duration_seconds: float) -> int:
        if duration_seconds <= 60.0:
            return 48
        if duration_seconds <= 300.0:
            return 72
        return 96

    def _collect_frames(self, cap: cv2.VideoCapture, indices: list[int], sequential: bool) -> list[np.ndarray]:
        frames: list[np.ndarray] = []
        if not indices:
            return frames

        if not sequential:
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, frame = cap.read()
                if ok and frame is not None:
                    frames.append(frame)
            return frames

        target_positions = sorted(set(max(0, idx) for idx in indices))
        target_iter = iter(target_positions)
        current_target = next(target_iter, None)
        frame_index = 0

        while current_target is not None:
            ok = cap.grab()
            if not ok:
                break
            if frame_index < current_target:
                frame_index += 1
                continue

            ok, frame = cap.retrieve()
            if ok and frame is not None:
                frames.append(frame)
            frame_index += 1
            current_target = next(target_iter, None)

        return frames

    def _build_indices(self, total: int, max_frames: int, profile: str) -> list[int]:
        if total <= 0:
            return list(range(max_frames))

        if profile == "budgeted":
            return self._build_budgeted_indices(total=total, max_frames=max_frames)
        if profile != "slowfast":
            step = max(1, total // max_frames)
            return list(range(0, total, step))[:max_frames]

        slow_count = max(8, max_frames // 3)
        fast_count = max_frames - slow_count
        slow_step = max(1, total // slow_count)
        slow_indices = list(range(0, total, slow_step))[:slow_count]

        anchor_count = max(1, fast_count // 4)
        anchor_step = max(1, total // (anchor_count + 1))
        anchors = [min(total - 1, anchor_step * (idx + 1)) for idx in range(anchor_count)]

        fast_indices: list[int] = []
        for anchor in anchors:
            for offset in (-2, -1, 0, 1):
                if len(fast_indices) >= fast_count:
                    break
                frame_index = min(total - 1, max(0, anchor + offset))
                fast_indices.append(frame_index)

        merged = sorted(set(slow_indices + fast_indices))
        if len(merged) > max_frames:
            merged = merged[:max_frames]
        return merged

    def _build_budgeted_indices(self, total: int, max_frames: int) -> list[int]:
        if total <= 0:
            return list(range(max_frames))

        anchor_count = max(1, int(round(max_frames * 0.7)))
        dense_count = max(0, max_frames - anchor_count)
        anchor_step = max(1, total // anchor_count)
        anchors = list(range(0, total, anchor_step))[:anchor_count]
        if not anchors:
            anchors = [0]

        dense_indices: list[int] = []
        if dense_count:
            motion_anchor_step = max(1, len(anchors) // max(1, dense_count))
            motion_anchors = anchors[::motion_anchor_step][:dense_count]
            for idx, anchor in enumerate(motion_anchors):
                offset = 1 + (idx % 3)
                dense_indices.append(min(total - 1, anchor + offset))

        merged = sorted(set(anchors + dense_indices))
        while len(merged) < max_frames and merged[-1] < total - 1:
            merged.append(min(total - 1, merged[-1] + 1))
        return merged[:max_frames]

    def infer_source_type(self, filename: str, content_type: str) -> str:
        lower = (filename or "").lower()
        if (content_type or "").startswith("video/") or lower.endswith(VIDEO_EXTENSIONS):
            return "video"
        return "image"

