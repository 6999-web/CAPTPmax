from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from schemas import ShootingFlowStage, Violation
from cv.types import FramePoseResult, FrameWeaponResult, PosePerson, WeaponDetection


# COCO-17 indices
NOSE = 0
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12


@dataclass
class PostureEvaluation:
    compliance: bool
    score: float
    dimension_scores: dict[str, float] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)


DIMENSION_LABELS = {
    "shoulder_balance": "肩线稳定",
    "isosceles_triangle": "等腰三角",
    "arm_extension": "手臂前伸",
    "head_alignment": "头部对齐",
    "grip_stability": "双手握持",
    "muzzle_safety": "枪口安全",
}


class EventType(str, Enum):
    pass_gun_method_1 = "pass_gun_method_1"
    pass_gun_method_2 = "pass_gun_method_2"
    check_weapon = "check_weapon"
    insert_magazine = "insert_magazine"
    prepare_and_fire = "prepare_and_fire"
    post_fire_check = "post_fire_check"


class ShootingFlowStateMachine:
    def __init__(self) -> None:
        self._path: list[EventType] = []
        self._order_ok: bool = True

    @property
    def order_ok(self) -> bool:
        return self._order_ok

    def ingest(self, event: EventType | None) -> ShootingFlowStage:
        if event is None:
            return self.current_stage()

        if not self._path:
            if event in {EventType.pass_gun_method_1, EventType.pass_gun_method_2, EventType.check_weapon}:
                self._path.append(event)
            else:
                self._order_ok = False
                self._path.append(event)
            return self.current_stage()

        expected_next = self._expected_next_events()
        if event not in expected_next and event != self._path[-1]:
            self._order_ok = False

        if event != self._path[-1]:
            self._path.append(event)

        return self.current_stage()

    def current_stage(self) -> ShootingFlowStage:
        if not self._path:
            return ShootingFlowStage.check_weapon
        return ShootingFlowStage(self._path[-1].value)

    def _expected_next_events(self) -> set[EventType]:
        last = self._path[-1]
        if last in {EventType.pass_gun_method_1, EventType.pass_gun_method_2}:
            return {EventType.check_weapon}
        if last == EventType.check_weapon:
            return {EventType.insert_magazine}
        if last == EventType.insert_magazine:
            return {EventType.prepare_and_fire}
        if last == EventType.prepare_and_fire:
            return {EventType.post_fire_check}
        return {EventType.post_fire_check}


class ShootingRulesAnalyzer:
    def evaluate_posture(
        self,
        pose_result: FramePoseResult,
        weapon_result: FrameWeaponResult,
        frame_index: int,
    ) -> PostureEvaluation:
        if not pose_result.persons:
            violations = [
                Violation(
                    code="NO_PERSON",
                    severity="high",
                    description="No person detected for shooting posture check.",
                    rule_ref="basic.body.front_target",
                    evidence_frame_idx=frame_index,
                )
            ]
            return PostureEvaluation(
                compliance=False,
                score=0.0,
                dimension_scores={key: 0.0 for key in DIMENSION_LABELS},
                violations=violations,
            )

        subject = max(pose_result.persons, key=lambda p: p.score)
        violations: list[Violation] = []
        score_items: list[float] = []
        dimension_scores: dict[str, float] = {}

        self._check_shoulder_balance(subject, frame_index, violations, score_items, dimension_scores)
        self._check_isosceles_triangle(subject, frame_index, violations, score_items, dimension_scores)
        self._check_arm_extension(subject, frame_index, violations, score_items, dimension_scores)
        self._check_head_alignment(subject, frame_index, violations, score_items, dimension_scores)
        self._check_two_hand_grip(pose_result, weapon_result, frame_index, violations, score_items, dimension_scores)
        self._check_muzzle_safety(pose_result, weapon_result, frame_index, violations, score_items, dimension_scores)

        score = float(np.mean(score_items)) if score_items else 0.0
        has_critical = any(v.severity == "high_critical" for v in violations)
        has_high = any(v.severity == "high" for v in violations)
        return PostureEvaluation(
            compliance=score >= 0.7 and not has_high and not has_critical,
            score=score,
            dimension_scores=dimension_scores,
            violations=violations,
        )

    def infer_flow_event(
        self,
        pose_result: FramePoseResult,
        weapon_result: FrameWeaponResult,
        posture: PostureEvaluation,
    ) -> EventType | None:
        has_weapon = len(weapon_result.weapons) > 0
        subject = max(pose_result.persons, key=lambda p: p.score) if pose_result.persons else None

        if has_weapon and subject and self._arms_extended(subject):
            return EventType.prepare_and_fire
        if self._is_ready_pre_fire_stage(weapon_result, posture):
            return EventType.insert_magazine
        return None

    def _is_ready_pre_fire_stage(
        self,
        weapon_result: FrameWeaponResult,
        posture: PostureEvaluation,
    ) -> bool:
        # 面向上半身取景场景，射前准备放宽为只要枪械可见且姿态基本成立即可。
        has_pistol = self._find_detection(weapon_result, "pistol", fallback_any=False) is not None
        return has_pistol and posture.score > 0.4

    def _arms_extended(self, person: PosePerson) -> bool:
        k = person.keypoints_xy
        le = np.linalg.norm(k[LEFT_WRIST] - k[LEFT_SHOULDER])
        re = np.linalg.norm(k[RIGHT_WRIST] - k[RIGHT_SHOULDER])
        torso = np.linalg.norm(k[LEFT_SHOULDER] - k[LEFT_HIP]) + 1e-6
        return (le / torso > 0.9) and (re / torso > 0.9)

    @staticmethod
    def _joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        ba = a - b
        bc = c - b
        n1 = float(np.linalg.norm(ba))
        n2 = float(np.linalg.norm(bc))
        if n1 < 1e-6 or n2 < 1e-6:
            return 0.0
        cosv = float(np.dot(ba, bc) / (n1 * n2))
        cosv = float(np.clip(cosv, -1.0, 1.0))
        return float(np.degrees(np.arccos(cosv)))

    def _check_shoulder_balance(self, person: PosePerson, frame_idx: int, violations: list[Violation], score_items: list[float], dimension_scores: dict[str, float]) -> None:
        k = person.keypoints_xy
        dy = abs(float(k[LEFT_SHOULDER][1] - k[RIGHT_SHOULDER][1]))
        shoulder_span = np.linalg.norm(k[LEFT_SHOULDER] - k[RIGHT_SHOULDER]) + 1e-6
        norm = dy / shoulder_span
        score = max(0.0, 1.0 - norm * 2.5)
        score_items.append(score)
        dimension_scores["shoulder_balance"] = float(score)
        if norm > 0.15:
            violations.append(Violation(code="SHOULDER_UNLEVEL", severity="medium", description="Shoulders are not level for stable two-arm posture.", rule_ref="basic.arms.shoulder_level", evidence_frame_idx=frame_idx))

    def _check_isosceles_triangle(self, person: PosePerson, frame_idx: int, violations: list[Violation], score_items: list[float], dimension_scores: dict[str, float]) -> None:
        k = person.keypoints_xy
        left_arm = float(np.linalg.norm(k[LEFT_WRIST] - k[LEFT_SHOULDER]))
        right_arm = float(np.linalg.norm(k[RIGHT_WRIST] - k[RIGHT_SHOULDER]))
        max_arm = max(left_arm, right_arm, 1e-6)
        arm_ratio = min(left_arm, right_arm) / max_arm
        left_elbow = self._joint_angle(k[LEFT_SHOULDER], k[LEFT_ELBOW], k[LEFT_WRIST])
        right_elbow = self._joint_angle(k[RIGHT_SHOULDER], k[RIGHT_ELBOW], k[RIGHT_WRIST])

        elbow_score = max(0.0, 1.0 - abs(left_elbow - right_elbow) / 30.0)
        score = float(np.clip((arm_ratio + elbow_score) / 2.0, 0.0, 1.0))
        score_items.append(score)
        dimension_scores["isosceles_triangle"] = score

        if arm_ratio < 0.9 or not (145.0 <= left_elbow <= 178.0 and 145.0 <= right_elbow <= 178.0):
            violations.append(
                Violation(
                    code="ISO_TRIANGLE_WEAK",
                    severity="medium",
                    description="Arms and shoulders do not form a stable isosceles triangle.",
                    rule_ref="posture.isosceles.triangle",
                    evidence_frame_idx=frame_idx,
                )
            )

    def _check_arm_extension(self, person: PosePerson, frame_idx: int, violations: list[Violation], score_items: list[float], dimension_scores: dict[str, float]) -> None:
        k = person.keypoints_xy
        arm_l = np.linalg.norm(k[LEFT_WRIST] - k[LEFT_SHOULDER])
        arm_r = np.linalg.norm(k[RIGHT_WRIST] - k[RIGHT_SHOULDER])
        torso = np.linalg.norm(k[LEFT_SHOULDER] - k[LEFT_HIP]) + 1e-6
        ratio = (arm_l + arm_r) / (2 * torso)
        score = float(np.clip((ratio - 0.6) / 0.6, 0.0, 1.0))
        score_items.append(score)
        dimension_scores["arm_extension"] = score
        if ratio < 0.9:
            violations.append(Violation(code="ARM_NOT_EXTENDED", severity="medium", description="Arms are not naturally extended toward target.", rule_ref="basic.arms.extension", evidence_frame_idx=frame_idx))

    def _check_head_alignment(self, person: PosePerson, frame_idx: int, violations: list[Violation], score_items: list[float], dimension_scores: dict[str, float]) -> None:
        k = person.keypoints_xy
        shoulder_mid = (k[LEFT_SHOULDER] + k[RIGHT_SHOULDER]) / 2
        head_offset = abs(float(k[NOSE][0] - shoulder_mid[0]))
        shoulder_span = np.linalg.norm(k[LEFT_SHOULDER] - k[RIGHT_SHOULDER]) + 1e-6
        norm = head_offset / shoulder_span
        score = max(0.0, 1.0 - norm * 2.0)
        score_items.append(score)
        dimension_scores["head_alignment"] = float(score)
        if norm > 0.25:
            violations.append(Violation(code="HEAD_NOT_ALIGNED", severity="low", description="Head is not upright and centered toward target.", rule_ref="basic.head.upright", evidence_frame_idx=frame_idx))

    def _check_two_hand_grip(self, pose_result: FramePoseResult, weapon_result: FrameWeaponResult, frame_idx: int, violations: list[Violation], score_items: list[float], dimension_scores: dict[str, float]) -> None:
        if len(pose_result.hands) < 2:
            score_items.append(0.4)
            dimension_scores["grip_stability"] = 0.4
            violations.append(Violation(code="HANDS_INCOMPLETE", severity="medium", description="Both hands should wrap the grip with no visible gap.", rule_ref="grip.two_hands.wrap", evidence_frame_idx=frame_idx))
            return

        right = next((h for h in pose_result.hands if h.hand_label == "right"), pose_result.hands[0])
        left = next((h for h in pose_result.hands if h.hand_label == "left"), pose_result.hands[-1])

        # Right-hand primary grip / left-hand support check
        right_palm = right.points_xy[0]
        left_palm = left.points_xy[0]
        grip_distance = float(np.linalg.norm(right_palm - left_palm))
        palm_score = float(np.clip(1.0 - grip_distance / 220.0, 0.0, 1.0))
        score_items.append(palm_score)

        right_thumb_tip = right.points_xy[4]
        left_thumb_tip = left.points_xy[4]
        thumb_gap = np.linalg.norm(right_thumb_tip - left_thumb_tip)
        wrist_gap = np.linalg.norm(right.points_xy[0] - left.points_xy[0]) + 1e-6
        thumb_parallel_score = float(np.clip(1.0 - (thumb_gap / (wrist_gap * 2.0)), 0.0, 1.0))
        score_items.append(thumb_parallel_score)
        dimension_scores["grip_stability"] = float(np.clip((palm_score + thumb_parallel_score) / 2.0, 0.0, 1.0))
        if thumb_parallel_score < 0.5:
            violations.append(Violation(code="THUMB_PARALLEL_WEAK", severity="medium", description="Thumb alignment suggests unstable supporting-hand wrap.", rule_ref="grip.thumb.parallel", evidence_frame_idx=frame_idx))

        ejection = self._find_detection(weapon_result, "ejection_port", fallback_any=False)
        if ejection is not None:
            x1, y1, x2, y2 = ejection.bbox
            ejection_center = np.asarray([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=float)
            finger_tip = np.vstack([left.points_xy[8], right.points_xy[8], left.points_xy[4], right.points_xy[4]]).mean(axis=0)
            risk_radius = max(20.0, (x2 - x1) * 0.9)
            if np.linalg.norm(finger_tip - ejection_center) < risk_radius:
                violations.append(
                    Violation(
                        code="EJECTION_PORT_HAND_RISK",
                        severity="high",
                        description="Thumb or finger is too close to the ejection port area.",
                        rule_ref="grip.ejection_port.safe_distance",
                        evidence_frame_idx=frame_idx,
                    )
                )

    def _check_muzzle_safety(self, pose_result: FramePoseResult, weapon_result: FrameWeaponResult, frame_idx: int, violations: list[Violation], score_items: list[float], dimension_scores: dict[str, float]) -> None:
        pistol = self._find_detection(weapon_result, "pistol", fallback_any=True)
        if pistol is None:
            score_items.append(0.5)
            dimension_scores["muzzle_safety"] = 0.5
            return

        muzzle_vec = self._muzzle_vector(pistol)
        start = np.asarray([(pistol.bbox[0] + pistol.bbox[2]) / 2.0, (pistol.bbox[1] + pistol.bbox[3]) / 2.0], dtype=float)
        critical_hits = 0
        for person in pose_result.persons:
            x1, y1, x2, y2 = person.bbox
            target = np.asarray([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=float)
            vec_to_target = target - start
            dist = float(np.linalg.norm(vec_to_target))
            if dist < 1e-6:
                continue
            cosv = float(np.dot(muzzle_vec, vec_to_target / dist))
            if cosv > 0.92 and dist < 500.0:
                critical_hits += 1

        if critical_hits > 0:
            score_items.append(0.0)
            dimension_scores["muzzle_safety"] = 0.0
            violations.append(
                Violation(
                    code="MUZZLE_NON_SAFE_ZONE",
                    severity="high_critical",
                    description="Muzzle vector points toward non-safe zone (person/protected area).",
                    rule_ref="weapon.muzzle.safe_zone",
                    evidence_frame_idx=frame_idx,
                )
            )
            return

        direction = pistol.muzzle_direction
        if direction == "vertical":
            score_items.append(0.4)
            dimension_scores["muzzle_safety"] = 0.4
            violations.append(Violation(code="MUZZLE_DIRECTION_RISK", severity="high", description="Muzzle direction does not look like a safe downrange orientation.", rule_ref="weapon.muzzle.safe_direction", evidence_frame_idx=frame_idx))
        else:
            score_items.append(0.9)
            dimension_scores["muzzle_safety"] = 0.9

    @staticmethod
    def _find_detection(weapon_result: FrameWeaponResult, cls_name: str, fallback_any: bool) -> WeaponDetection | None:
        cls_name = cls_name.lower()
        for item in weapon_result.weapons:
            if item.cls_name.lower() == cls_name:
                return item
        for item in weapon_result.weapons:
            if cls_name in item.cls_name.lower():
                return item
        return weapon_result.weapons[0] if fallback_any and weapon_result.weapons else None

    @staticmethod
    def _muzzle_vector(weapon: WeaponDetection) -> np.ndarray:
        x1, y1, x2, y2 = weapon.bbox
        if weapon.muzzle_direction == "vertical":
            vec = np.asarray([0.0, 1.0], dtype=float)
        elif weapon.muzzle_direction == "diagonal":
            vec = np.asarray([1.0, -0.6], dtype=float)
        else:
            vec = np.asarray([1.0, 0.0], dtype=float)
        n = float(np.linalg.norm(vec))
        return vec / max(n, 1e-6)
