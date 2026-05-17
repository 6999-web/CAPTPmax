from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from settings import settings
from cv.types import FramePoseResult, HandLandmarkSet, PosePerson


@dataclass
class PoseEngineStatus:
    yolo_ready: bool
    mediapipe_ready: bool
    mmpose_ready: bool


class PoseEngine:
    def __init__(self) -> None:
        self._yolo = None
        self._mp_pose = None
        self._mp_hands = None
        self._mmpose_inferencer = None
        self._frame_counter = 0

        self._load_yolo_pose()
        self._load_mediapipe()
        self._load_mmpose()

    @property
    def status(self) -> PoseEngineStatus:
        return PoseEngineStatus(
            yolo_ready=self._yolo is not None,
            mediapipe_ready=self._mp_pose is not None and self._mp_hands is not None,
            mmpose_ready=self._mmpose_inferencer is not None,
        )

    def _load_yolo_pose(self) -> None:
        try:
            from ultralytics import YOLO

            self._yolo = YOLO(settings.yolo_pose_model)
        except Exception:
            self._yolo = None

    def _load_mediapipe(self) -> None:
        try:
            import mediapipe as mp

            self._mp_pose = mp.solutions.pose.Pose(
                model_complexity=max(0, min(2, settings.mediapipe_model_complexity)),
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._mp_hands = mp.solutions.hands.Hands(
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        except Exception:
            self._mp_pose = None
            self._mp_hands = None

    def _load_mmpose(self) -> None:
        if not settings.mmpose_config or not settings.mmpose_checkpoint:
            self._mmpose_inferencer = None
            return

        try:
            from mmpose.apis import MMPoseInferencer

            self._mmpose_inferencer = MMPoseInferencer(
                pose2d=settings.mmpose_config,
                pose2d_weights=settings.mmpose_checkpoint,
                device=settings.device,
            )
        except Exception:
            self._mmpose_inferencer = None

    def infer(self, frame: np.ndarray, frame_index: int = 0) -> FramePoseResult:
        self._frame_counter += 1
        if settings.mediapipe_frame_skip > 0 and (self._frame_counter % (settings.mediapipe_frame_skip + 1)) != 1:
            return self._build_fallback_result(frame)

        result = self._infer_pose_only(frame)

        if self._mp_hands is not None:
            self._infer_hands(frame, result)

        if not result.persons:
            return self._build_fallback_result(frame)

        return result

    def infer_batch(self, frames: list[np.ndarray]) -> list[FramePoseResult]:
        if not frames:
            return []

        if self._yolo is None:
            return [self._build_fallback_result(frame) for frame in frames]

        try:
            outputs = self._yolo.predict(
                frames,
                verbose=False,
                device=settings.device,
                imgsz=640,
                batch=8,
            )
        except Exception:
            return [self._build_fallback_result(frame) for frame in frames]

        results: list[FramePoseResult] = []
        for idx, frame in enumerate(frames):
            result = FramePoseResult()
            pred = outputs[idx] if idx < len(outputs) else None
            if pred is not None:
                self._populate_from_prediction(pred, result)
            if not result.persons:
                result = self._build_fallback_result(frame)
            results.append(result)
        return results

    def _infer_pose_only(self, frame: np.ndarray) -> FramePoseResult:
        result = FramePoseResult()
        if self._yolo is not None:
            try:
                outputs = self._yolo.predict(frame, verbose=False, device=settings.device)
                if outputs:
                    self._populate_from_prediction(outputs[0], result)
            except Exception:
                result.fallback_used = True
        return result

    def _infer_with_yolo(self, frame: np.ndarray, result: FramePoseResult) -> None:
        try:
            outputs = self._yolo.predict(frame, verbose=False, device=settings.device)
            if not outputs:
                return
            self._populate_from_prediction(outputs[0], result)
        except Exception:
            result.fallback_used = True

    def _populate_from_prediction(self, pred, result: FramePoseResult) -> None:
        boxes = pred.boxes
        keypoints = pred.keypoints
        if boxes is None or keypoints is None:
            return

        xyxy = boxes.xyxy.cpu().numpy() if boxes.xyxy is not None else []
        scores = boxes.conf.cpu().numpy() if boxes.conf is not None else []
        k_xy = keypoints.xy.cpu().numpy() if keypoints.xy is not None else []
        k_conf = keypoints.conf.cpu().numpy() if keypoints.conf is not None else []

        for i in range(len(xyxy)):
            x1, y1, x2, y2 = xyxy[i].astype(int).tolist()
            conf = float(scores[i]) if i < len(scores) else 0.0
            points_xy = k_xy[i] if i < len(k_xy) else np.zeros((17, 2), dtype=float)
            points_conf = k_conf[i] if i < len(k_conf) else np.zeros((17,), dtype=float)
            result.persons.append(
                PosePerson(
                    person_id=i,
                    bbox=(x1, y1, x2, y2),
                    score=conf,
                    keypoints_xy=np.asarray(points_xy, dtype=float),
                    keypoints_conf=np.asarray(points_conf, dtype=float),
                )
            )

    def _infer_hands(self, frame: np.ndarray, result: FramePoseResult) -> None:
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            hand_res = self._mp_hands.process(rgb)
            if not hand_res.multi_hand_landmarks:
                return

            h, w = frame.shape[:2]
            handedness = hand_res.multi_handedness or []
            for idx, lm in enumerate(hand_res.multi_hand_landmarks):
                pts = []
                for p in lm.landmark:
                    pts.append([p.x * w, p.y * h])
                label = "unknown"
                if idx < len(handedness):
                    label = handedness[idx].classification[0].label.lower()
                result.hands.append(
                    HandLandmarkSet(
                        hand_label=label,
                        points_xy=np.asarray(pts, dtype=float),
                        score=0.5,
                    )
                )
        except Exception:
            result.fallback_used = True

    def _build_fallback_result(self, frame: np.ndarray) -> FramePoseResult:
        result = FramePoseResult(fallback_used=True)
        h, w = frame.shape[:2]
        pseudo_kpts = np.zeros((17, 2), dtype=float)
        pseudo_conf = np.zeros((17,), dtype=float)
        pseudo_kpts[:, 0] = w * 0.5
        pseudo_kpts[:, 1] = h * 0.5
        result.persons.append(
            PosePerson(
                person_id=0,
                bbox=(0, 0, w, h),
                score=0.01,
                keypoints_xy=pseudo_kpts,
                keypoints_conf=pseudo_conf,
            )
        )
        return result

