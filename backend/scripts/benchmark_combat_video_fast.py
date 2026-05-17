from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from schemas import AnalyzeMode, CombatSegmentManifestItem, VideoAnalysisStrategy
from services.pipeline import pipeline


def extract_segment_frames(video_path: Path, segment_count: int = 5, frames_per_segment: int = 10, overlap_seconds: float = 1.0):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    duration_seconds = (total_frames / fps) if fps > 0 and total_frames > 0 else 0.0
    if duration_seconds <= 0:
        raise RuntimeError("Unable to read video duration")

    manifest: list[CombatSegmentManifestItem] = []
    segment_frames = []

    for segment_id in range(segment_count):
        base_start = (duration_seconds / segment_count) * segment_id
        base_end = duration_seconds if segment_id == segment_count - 1 else (duration_seconds / segment_count) * (segment_id + 1)
        start_seconds = max(0.0, base_start - (0.0 if segment_id == 0 else overlap_seconds))
        end_seconds = min(duration_seconds, base_end + (0.0 if segment_id == segment_count - 1 else overlap_seconds))
        span = max(0.05, end_seconds - start_seconds)

        times = []
        frames = []
        filenames = []
        for frame_id in range(frames_per_segment):
            ratio = 0.5 if frames_per_segment == 1 else frame_id / (frames_per_segment - 1)
            ts = min(duration_seconds - 0.05, max(0.0, start_seconds + span * ratio))
            frame_index = max(0, min(total_frames - 1, int(round(ts * fps)))) if fps > 0 and total_frames > 0 else frame_id
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frames.append(frame)
            times.append(ts)
            filenames.append(f"seg-{segment_id}-frame-{frame_id}.jpg")

        manifest.append(
            CombatSegmentManifestItem(
                segment_id=segment_id,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                frame_times_seconds=times,
                filenames=filenames,
            )
        )
        segment_frames.append(frames)

    cap.release()
    return duration_seconds, manifest, segment_frames


def main():
    parser = argparse.ArgumentParser(description="Benchmark five-way combat video analysis.")
    parser.add_argument("--video", default="飞书20260422-154708.mp4")
    parser.add_argument("--threshold-ms", type=float, default=15000.0)
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.is_absolute():
        video_path = Path.cwd() / video_path
    if not video_path.exists():
        raise SystemExit(f"Video not found: {video_path}")

    duration_seconds, manifest, segment_frames = extract_segment_frames(video_path)

    t0 = time.perf_counter()
    result = pipeline.analyze_combat_video_fast(
        segment_frames=segment_frames,
        manifest=manifest,
        mode=AnalyzeMode.combat_full,
        strategy=VideoAnalysisStrategy.five_way,
        duration_seconds=duration_seconds,
        client_extract_ms=0.0,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"video={video_path}")
    print(f"duration_seconds={duration_seconds:.2f}")
    print(f"elapsed_ms={elapsed_ms:.1f}")
    print(f"review_cards={len(result.combat.review_cards)}")
    print(f"actions={len(result.combat.actions)}")
    print(f"hits={len(result.combat.hit_events)}")
    print(f"performance={result.meta.performance}")

    if elapsed_ms > args.threshold_ms:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
