from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


Point = Tuple[float, float]

STANDARD_SHOOTING_IMAGES = {
    "insert_mag": "https://commons.wikimedia.org/wiki/Special:FilePath/Defenders_maintain_readiness_with_new_M18_pistol_(6291084).jpg",
    "check_weapon": "https://commons.wikimedia.org/wiki/Special:FilePath/USAG_Benelux_MPs_M9_and_M16A2_practice_at_TSC_Benelux_Firing_Range_141114-A-BD610-051.jpg",
    "fire": "https://commons.wikimedia.org/wiki/Special:FilePath/Sailors_fire_an_M9_service_pistol._(30502990122).jpg",
}


class Stage(str, Enum):
    A_RECEIVE_WEAPON = "A_RECEIVE_WEAPON"
    B_INITIAL_CHECK = "B_INITIAL_CHECK"
    C_PREPARE_FIRE = "C_PREPARE_FIRE"
    D_FIRE = "D_FIRE"
    E_FINAL_CHECK = "E_FINAL_CHECK"
    DONE = "DONE"


class Action(str, Enum):
    RECEIVE_WEAPON = "receive_weapon"
    REMOVE_MAG = "remove_mag"
    CHECK_CHAMBER = "check_chamber"
    SAFE_ON = "safe_on"
    INSERT_MAG = "insert_mag"
    HOLSTER_OR_READY = "holster_or_ready"
    ISO_GRIP = "iso_grip"
    RACK_SLIDE = "rack_slide"
    FIRE = "fire"
    FINAL_REMOVE_MAG = "final_remove_mag"
    FINAL_CHECK_CHAMBER = "final_check_chamber"


REQUIRED_ACTIONS: Dict[Stage, List[Action]] = {
    Stage.A_RECEIVE_WEAPON: [Action.RECEIVE_WEAPON],
    Stage.B_INITIAL_CHECK: [Action.REMOVE_MAG, Action.CHECK_CHAMBER, Action.SAFE_ON],
    Stage.C_PREPARE_FIRE: [Action.INSERT_MAG, Action.HOLSTER_OR_READY, Action.ISO_GRIP, Action.RACK_SLIDE],
    Stage.D_FIRE: [Action.FIRE],
    Stage.E_FINAL_CHECK: [Action.FINAL_REMOVE_MAG, Action.FINAL_CHECK_CHAMBER],
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _decode_data_url(data: str) -> bytes:
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


def _encode_jpeg_b64(frame: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        return ""
    return base64.b64encode(encoded.tobytes()).decode("utf-8")


def _angle(a: Point, b: Point, c: Point) -> float:
    bax = a[0] - b[0]
    bay = a[1] - b[1]
    bcx = c[0] - b[0]
    bcy = c[1] - b[1]
    dot = bax * bcx + bay * bcy
    n1 = float(np.hypot(bax, bay))
    n2 = float(np.hypot(bcx, bcy))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    cosv = max(-1.0, min(1.0, dot / (n1 * n2)))
    return float(np.degrees(np.arccos(cosv)))


def solve_isosceles_posture(keypoints: Dict[str, Point]) -> Dict[str, float | bool]:
    ls, rs = keypoints["left_shoulder"], keypoints["right_shoulder"]
    le, re = keypoints["left_elbow"], keypoints["right_elbow"]
    lw, rw = keypoints["left_wrist"], keypoints["right_wrist"]

    left_elbow_angle = _angle(ls, le, lw)
    right_elbow_angle = _angle(rs, re, rw)
    left_arm_len = float(np.hypot(ls[0] - lw[0], ls[1] - lw[1]))
    right_arm_len = float(np.hypot(rs[0] - rw[0], rs[1] - rw[1]))
    longer = max(left_arm_len, right_arm_len)
    arm_len_ratio = (min(left_arm_len, right_arm_len) / longer) if longer > 0 else 0.0
    shoulder_delta_y = abs(ls[1] - rs[1])

    is_isosceles = (
        150.0 <= left_elbow_angle <= 175.0
        and 150.0 <= right_elbow_angle <= 175.0
        and arm_len_ratio >= 0.9
        and shoulder_delta_y <= 20.0
    )
    return {
        "left_elbow_angle": round(left_elbow_angle, 2),
        "right_elbow_angle": round(right_elbow_angle, 2),
        "arm_len_ratio": round(arm_len_ratio, 3),
        "shoulder_delta_y": round(shoulder_delta_y, 2),
        "is_isosceles": is_isosceles,
    }


@dataclass
class Violation:
    code: str
    reason: str
    stage: Stage
    ts: str = field(default_factory=_now_iso)


@dataclass
class TransitionResult:
    stage: Stage
    advanced: bool
    accepted: bool
    violation: Optional[Violation] = None


class TrainingWorkflowMachine:
    def __init__(self) -> None:
        self.stage: Stage = Stage.A_RECEIVE_WEAPON
        self._done_actions: set[Action] = set()
        self.violations: List[Violation] = []

    def consume(self, action: Action) -> TransitionResult:
        if self.stage == Stage.DONE:
            violation = Violation("FLOW_ENDED", "流程已结束，不应再有动作输入", self.stage)
            self.violations.append(violation)
            return TransitionResult(self.stage, False, False, violation)

        expected = REQUIRED_ACTIONS[self.stage]
        completed = len([it for it in expected if it in self._done_actions])
        next_expected = expected[min(completed, len(expected) - 1)]

        if self.stage == Stage.E_FINAL_CHECK and action == Action.FINAL_CHECK_CHAMBER and Action.FINAL_REMOVE_MAG not in self._done_actions:
            violation = Violation("FINAL_ORDER_ERROR", "终点验枪顺序错误：必须先卸弹匣，后查弹膛", self.stage)
            self.violations.append(violation)
            return TransitionResult(self.stage, False, False, violation)

        if action != next_expected:
            violation = Violation("ORDER_ERROR", f"动作顺序错误，期望 {next_expected.value}，实际 {action.value}", self.stage)
            self.violations.append(violation)
            return TransitionResult(self.stage, False, False, violation)

        self._done_actions.add(action)
        if all(it in self._done_actions for it in expected):
            self._done_actions.clear()
            self.stage = self._next_stage(self.stage)
            return TransitionResult(self.stage, True, True, None)
        return TransitionResult(self.stage, False, True, None)

    @staticmethod
    def _next_stage(stage: Stage) -> Stage:
        order = [Stage.A_RECEIVE_WEAPON, Stage.B_INITIAL_CHECK, Stage.C_PREPARE_FIRE, Stage.D_FIRE, Stage.E_FINAL_CHECK, Stage.DONE]
        return order[order.index(stage) + 1]


class FrameRingBuffer:
    def __init__(self, maxlen: int = 24) -> None:
        self._frames: deque[np.ndarray] = deque(maxlen=maxlen)

    def push(self, frame: np.ndarray) -> None:
        self._frames.append(frame.copy())

    def latest(self) -> Optional[np.ndarray]:
        if not self._frames:
            return None
        return self._frames[-1].copy()


class ShootingCoachSession:
    REQUIRED_KEYS = {
        "left_shoulder",
        "right_shoulder",
        "left_elbow",
        "right_elbow",
        "left_wrist",
        "right_wrist",
    }

    def __init__(self, standard_ref_url: str = "/school_badge.jpg") -> None:
        self.buffer = FrameRingBuffer(maxlen=24)
        self.machine = TrainingWorkflowMachine()
        self.active_errors: Dict[str, dict] = {}
        self.last_reported_stage: str = ""
        self.standard_ref_url = standard_ref_url
        self.received_weapon = False

    def process_packet(self, packet: dict) -> list[dict]:
        events: list[dict] = []
        frame = self._extract_frame(packet.get("frame"))
        if frame is not None:
            self.buffer.push(frame)

        shooting = packet.get("shooting") or {}
        if not self.received_weapon and shooting:
            res = self.machine.consume(Action.RECEIVE_WEAPON)
            self.received_weapon = True
            if res.advanced:
                events.append({"event": "stage:update", "data": {"stage": res.stage.value, "ts": _now_iso()}})

        keypoints = packet.get("keypoints") or {}
        if self._has_required_keypoints(keypoints):
            keypoints_typed = {k: (float(v[0]), float(v[1])) for k, v in keypoints.items() if isinstance(v, (list, tuple)) and len(v) >= 2}
            pose_metrics = solve_isosceles_posture(keypoints_typed)
            if not bool(pose_metrics["is_isosceles"]):
                card = self._build_pose_card(
                    "P-ISO-001",
                    "双臂等腰三角形不稳定，可能降低控枪稳定性",
                    "双臂自然前伸，双肩保持平齐，肘部微屈吸收后坐力",
                    frame,
                    keypoints_typed,
                    why_wrong=[
                        "双肘角度不对称会让枪口回正变慢",
                        "肩线不平会导致击发瞬间偏移",
                        "后坐力无法沿双臂稳定传导",
                    ],
                    standard_ref_key="fire",
                )
                events.extend(self._upsert_error(card))
            else:
                events.extend(self._remove_error("P-ISO-001", "等腰三角握持已恢复，动作合规"))

        flow_order_ok = shooting.get("flow_order_ok")
        if flow_order_ok is False:
            card = self._build_sequence_card(
                "S-ORDER-001",
                "动作顺序不合法",
                "请按系统提示逐步执行验枪、装弹、射击、再验枪流程",
                frame,
                why_wrong=[
                    "跳步会导致弹膛/保险状态不明",
                    "未确认安全状态就进入下一环节会放大事故风险",
                    "流程错误会使训练评估结果失真",
                ],
                standard_ref_key="check_weapon",
            )
            events.extend(self._upsert_error(card))
        elif flow_order_ok is True:
            events.extend(self._remove_error("S-ORDER-001", "动作顺序已恢复正确"))

        stage = shooting.get("flow_stage")
        if stage and stage != self.last_reported_stage:
            self.last_reported_stage = str(stage)
            events.append({"event": "stage:update", "data": {"stage": stage, "ts": _now_iso()}})

        raw_actions = packet.get("actions") or []
        for name in raw_actions:
            parsed = self._safe_action(name)
            if parsed is None:
                continue
            result = self.machine.consume(parsed)
            if result.violation:
                card = self._build_sequence_card(
                    f"S-{result.violation.code}",
                    result.violation.reason,
                    "请回到当前阶段要求动作并按顺序完成",
                    frame,
                    why_wrong=[
                        "验枪与再验枪是强顺序动作，不能互换",
                        "先查弹膛后卸弹匣会留下供弹不确定性",
                        "顺序错误会触发高风险操作告警",
                    ],
                    standard_ref_key="check_weapon",
                )
                events.extend(self._upsert_error(card))
            elif result.advanced:
                events.append({"event": "stage:update", "data": {"stage": result.stage.value, "ts": _now_iso()}})
                events.extend(self._remove_stage_sequence_errors())

        events.append({"event": "state:snapshot", "data": {"stage": self.machine.stage.value, "active_errors": list(self.active_errors.values())}})
        return events

    def _build_pose_card(
        self,
        error_id: str,
        reason: str,
        suggestion: str,
        frame: Optional[np.ndarray],
        keypoints: Optional[Dict[str, Point]],
        why_wrong: Optional[list[str]] = None,
        standard_ref_key: str = "fire",
    ) -> dict:
        overlay_b64 = self._overlay_pose(frame, keypoints) if frame is not None else ""
        snapshot_b64 = _encode_jpeg_b64(frame) if frame is not None else ""
        return {
            "id": error_id,
            "type": "POSE",
            "stage": self.machine.stage.value,
            "reason": reason,
            "suggestion": suggestion,
            "confidence": 0.92,
            "snapshot_b64": snapshot_b64,
            "overlay_b64": overlay_b64 or snapshot_b64,
            "standard_ref_url": STANDARD_SHOOTING_IMAGES.get(standard_ref_key, self.standard_ref_url),
            "why_wrong": why_wrong or [],
            "ts": _now_iso(),
        }

    def _build_sequence_card(
        self,
        error_id: str,
        reason: str,
        suggestion: str,
        frame: Optional[np.ndarray],
        why_wrong: Optional[list[str]] = None,
        standard_ref_key: str = "check_weapon",
    ) -> dict:
        snapshot_b64 = _encode_jpeg_b64(frame) if frame is not None else ""
        resolved_key = standard_ref_key
        if "insert_mag" in reason:
            resolved_key = "insert_mag"
        elif "check_chamber" in reason or "safe_on" in reason:
            resolved_key = "check_weapon"
        return {
            "id": error_id,
            "type": "SEQUENCE",
            "stage": self.machine.stage.value,
            "reason": reason,
            "suggestion": suggestion,
            "confidence": 0.95,
            "snapshot_b64": snapshot_b64,
            "overlay_b64": snapshot_b64,
            "standard_ref_url": STANDARD_SHOOTING_IMAGES.get(resolved_key, self.standard_ref_url),
            "why_wrong": why_wrong or [],
            "ts": _now_iso(),
        }

    def _overlay_pose(self, frame: np.ndarray, keypoints: Optional[Dict[str, Point]]) -> str:
        if frame is None:
            return ""
        canvas = frame.copy()
        if not keypoints:
            return _encode_jpeg_b64(canvas)

        links = [
            ("left_shoulder", "left_elbow"),
            ("left_elbow", "left_wrist"),
            ("right_shoulder", "right_elbow"),
            ("right_elbow", "right_wrist"),
            ("left_shoulder", "right_shoulder"),
        ]
        red = (0, 0, 255)
        for a, b in links:
            if a not in keypoints or b not in keypoints:
                continue
            ax, ay = keypoints[a]
            bx, by = keypoints[b]
            cv2.line(canvas, (int(ax), int(ay)), (int(bx), int(by)), red, 2)
        for key in keypoints:
            x, y = keypoints[key]
            cv2.circle(canvas, (int(x), int(y)), 4, red, -1)
        return _encode_jpeg_b64(canvas)

    def _upsert_error(self, card: dict) -> list[dict]:
        old = self.active_errors.get(card["id"])
        self.active_errors[card["id"]] = card
        event = "error:add" if old is None else "error:update"
        return [{"event": event, "data": card}]

    def _remove_error(self, error_id: str, success_text: str) -> list[dict]:
        if error_id not in self.active_errors:
            return []
        self.active_errors.pop(error_id, None)
        return [
            {"event": "error:remove", "data": {"id": error_id}},
            {"event": "hint:success", "data": {"text": success_text, "ts": _now_iso()}},
        ]

    def _remove_stage_sequence_errors(self) -> list[dict]:
        events: list[dict] = []
        keys = [key for key, value in self.active_errors.items() if value.get("type") == "SEQUENCE"]
        for key in keys:
            self.active_errors.pop(key, None)
            events.append({"event": "error:remove", "data": {"id": key}})
        if keys:
            events.append({"event": "hint:success", "data": {"text": "顺序错误已消除，可进入下一阶段", "ts": _now_iso()}})
        return events

    @staticmethod
    def _extract_frame(frame_b64: Optional[str]) -> Optional[np.ndarray]:
        if not frame_b64:
            return None
        try:
            raw = _decode_data_url(frame_b64)
            arr = np.frombuffer(raw, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return frame
        except Exception:
            return None

    @classmethod
    def _has_required_keypoints(cls, keypoints: dict) -> bool:
        return cls.REQUIRED_KEYS.issubset(set(keypoints.keys()))

    @staticmethod
    def _safe_action(value: str) -> Optional[Action]:
        legacy_map = {
            "final_rack_slide": Action.FINAL_CHECK_CHAMBER,
        }
        if value in legacy_map:
            return legacy_map[value]
        try:
            return Action(value)
        except Exception:
            return None
