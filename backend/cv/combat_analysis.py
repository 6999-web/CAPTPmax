from __future__ import annotations

import base64

import cv2
import numpy as np

from cv.types import FramePoseResult, PosePerson
from schemas import CombatActionItem, CombatQuartet, CombatReviewCard, CombatReviewMetrics, HitEvent, SupportedCombatAction


EVADE_REASONS = [
    "距离来不及拉开",
    "护架被打开，头部或躯干暴露",
    "重心被带偏后，无法及时撤步",
    "连续对抗后反应下降",
    "被假动作或上一步动作牵制",
    "画面证据不足，无法稳定判断",
]
DEFAULT_EVADE_REASON = "画面证据不足，无法稳定判断"

DAMAGE_RESULTS = [
    "未形成有效击中",
    "击中头部",
    "击中躯干",
    "形成压制，迫使对手后撤",
    "击中同时自身失衡风险上升",
]

ACTION_CATALOG = {
    "straight_punch": {
        "action_zh": "直拳",
        "description_zh": "沿直线快速出拳，强调手臂伸展与中轴压迫。",
        "typical_damage_zh": "常见为击中头部或躯干，形成直接打击。",
        "common_evade_failure_reasons_zh": [EVADE_REASONS[0], EVADE_REASONS[1], EVADE_REASONS[4]],
        "suggestion_zh": "命中后快速回收护架，避免反击空当。",
    },
    "hook_punch": {
        "action_zh": "勾拳",
        "description_zh": "利用躯干旋转与肩部联动，完成弧线打击。",
        "typical_damage_zh": "更容易形成头部侧向命中或压制护架。",
        "common_evade_failure_reasons_zh": [EVADE_REASONS[1], EVADE_REASONS[2], EVADE_REASONS[4]],
        "suggestion_zh": "先稳住支撑脚，再发力转髋，减少失衡。",
    },
    "kick": {
        "action_zh": "踢击",
        "description_zh": "抬膝与转髋发力的中远距离打击动作。",
        "typical_damage_zh": "常见为击中躯干，或形成明显压制。",
        "common_evade_failure_reasons_zh": [EVADE_REASONS[0], EVADE_REASONS[2], EVADE_REASONS[3]],
        "suggestion_zh": "出腿后及时回收，并恢复护架与重心。",
    },
    "block": {
        "action_zh": "格挡",
        "description_zh": "用前臂和护架吸收来袭力量，降低受击概率。",
        "typical_damage_zh": "通常不形成有效击中，但可打断对抗节奏。",
        "common_evade_failure_reasons_zh": [EVADE_REASONS[4], EVADE_REASONS[3], EVADE_REASONS[5]],
        "suggestion_zh": "缩短防守弧线，避免护架被持续拉开。",
    },
    "dodge": {
        "action_zh": "闪躲",
        "description_zh": "通过头部与躯干位移降低被击中概率。",
        "typical_damage_zh": "通常不形成有效击中，更多用于化解威胁。",
        "common_evade_failure_reasons_zh": [EVADE_REASONS[2], EVADE_REASONS[3], EVADE_REASONS[5]],
        "suggestion_zh": "位移要配合脚步与重心转移，避免二次受击。",
    },
}

TARGET_ZH_MAP = {"head": "头部", "body": "躯干"}


class CombatAnalyzer:
    def supported_actions(self) -> list[SupportedCombatAction]:
        return [
            SupportedCombatAction(
                action_code=code,
                action_zh=meta["action_zh"],
                description_zh=meta["description_zh"],
                typical_damage_zh=meta["typical_damage_zh"],
                common_evade_failure_reasons_zh=list(meta["common_evade_failure_reasons_zh"]),
            )
            for code, meta in ACTION_CATALOG.items()
        ]

    def build_actions(self, action_label: str, confidence: float, frame_index: int) -> list[CombatActionItem]:
        if action_label in {"idle", "unknown", "weapon_present", "prepare_and_fire", "check_weapon"}:
            return []
        return [CombatActionItem(action=action_label, confidence=confidence, actor_id=0, frame_index=frame_index)]

    def estimate_hits(self, pose: FramePoseResult, frame_index: int) -> list[HitEvent]:
        if len(pose.persons) < 2:
            return []

        attacker, defender = sorted(pose.persons, key=lambda item: item.score, reverse=True)[:2]
        attacker_wrist = (attacker.keypoints_xy[9] + attacker.keypoints_xy[10]) / 2
        defender_head = defender.keypoints_xy[0]
        defender_torso = (defender.keypoints_xy[5] + defender.keypoints_xy[6] + defender.keypoints_xy[11] + defender.keypoints_xy[12]) / 4

        head_dist = np.linalg.norm(attacker_wrist - defender_head)
        torso_dist = np.linalg.norm(attacker_wrist - defender_torso)
        torso_scale = np.linalg.norm(defender.keypoints_xy[5] - defender.keypoints_xy[11]) + 1e-6

        events: list[HitEvent] = []
        if head_dist < torso_scale * 0.6:
            events.append(
                HitEvent(
                    attacker_id=attacker.person_id,
                    defender_id=defender.person_id,
                    target="head",
                    confidence=float(np.clip(1.0 - head_dist / (torso_scale * 0.6), 0.0, 1.0)),
                    frame_index=frame_index,
                )
            )
        elif torso_dist < torso_scale * 0.7:
            events.append(
                HitEvent(
                    attacker_id=attacker.person_id,
                    defender_id=defender.person_id,
                    target="body",
                    confidence=float(np.clip(1.0 - torso_dist / (torso_scale * 0.7), 0.0, 1.0)),
                    frame_index=frame_index,
                )
            )
        return events

    def build_quartets(self, actions: list[CombatActionItem], hits: list[HitEvent], fatigue: dict, fps: float) -> list[CombatQuartet]:
        quartets: list[CombatQuartet] = []
        for action in actions:
            hit = next((item for item in hits if item.frame_index == action.frame_index), None)
            ts = action.frame_index / max(1.0, fps)
            metrics = CombatReviewMetrics(
                impact_score=float(action.confidence) + (0.2 if hit is not None else 0.0),
                reaction_lag_score=0.75 if fatigue.get("level") == "high" else 0.45 if fatigue.get("level") == "medium" else 0.2,
            )
            reason = self._evade_failure_reason(metrics, action.action, hit, fatigue)
            quartets.append(
                CombatQuartet(
                    action=self._action_zh(action.action),
                    effect=self._damage_zh(hit, fatigue.get("level") == "high", action.confidence),
                    reason=reason,
                    suggestion=self._suggestion_zh(action.action),
                    confidence=action.confidence,
                    timestamp_range=(max(0.0, ts - 0.2), ts + 0.2),
                )
            )
        return quartets

    def build_review_cards(
        self,
        frames: list[np.ndarray],
        poses: list[FramePoseResult],
        actions: list[CombatActionItem],
        hits: list[HitEvent],
        fatigue: dict,
        fps: float,
        limit: int | None = None,
    ) -> list[CombatReviewCard]:
        if not frames or not poses:
            return []

        pose_by_frame = {idx: pose for idx, pose in enumerate(poses)}
        frame_by_index = {idx: frame for idx, frame in enumerate(frames)}
        hit_by_frame = {hit.frame_index: hit for hit in hits}
        candidates: list[tuple[float, int, CombatActionItem, PosePerson | None, PosePerson | None, HitEvent | None, CombatReviewMetrics]] = []

        for seq_idx, action in enumerate(actions):
            pose = pose_by_frame.get(action.frame_index)
            frame = frame_by_index.get(action.frame_index)
            if pose is None or frame is None:
                continue

            previous_pose = pose_by_frame.get(max(0, action.frame_index - 1), pose)
            hit = hit_by_frame.get(action.frame_index)
            attacker, defender = self._resolve_pair(pose, hit)
            metrics = self._review_metrics(pose, previous_pose, attacker, defender, action, hit, fatigue)
            priority = (
                float(action.confidence) * 0.45
                + float(metrics.impact_score) * 0.25
                + float(metrics.balance_break_score) * 0.2
                + float(metrics.reaction_lag_score) * 0.1
            )
            candidates.append((priority, seq_idx, action, attacker, defender, hit, metrics))

        cards: list[CombatReviewCard] = []
        selected = sorted(candidates, key=lambda item: item[0], reverse=True)
        if limit is not None:
            selected = selected[:limit]
        selected = sorted(selected, key=lambda item: (item[2].frame_index, item[1]))

        for _, seq_idx, action, attacker, defender, hit, metrics in selected:
            frame = frame_by_index[action.frame_index]
            action_zh = self._action_zh(action.action)
            damage_zh = self._damage_zh(hit, metrics.balance_break_score > 0.7, action.confidence)
            evade_failure_reason_zh = self._evade_failure_reason(metrics, action.action, hit, fatigue)
            timestamp = self._format_timestamp(action.frame_index, fps)
            target_zh = TARGET_ZH_MAP.get(hit.target, "未判定") if hit is not None else "未判定"

            cards.append(
                CombatReviewCard(
                    card_id=f"combat-card-{action.frame_index}-{seq_idx}",
                    frame_index=action.frame_index,
                    timestamp=timestamp,
                    image_b64=self._encode_crop(frame, attacker, defender),
                    action_code=action.action,
                    action_zh=action_zh,
                    damage_zh=damage_zh,
                    evade_failure_reason_zh=evade_failure_reason_zh,
                    summary_zh=f"{timestamp}，{action_zh}，{damage_zh}；未闪避原因：{evade_failure_reason_zh}",
                    confidence=float(action.confidence),
                    attacker_id=attacker.person_id if attacker is not None else action.actor_id,
                    defender_id=defender.person_id if defender is not None else (hit.defender_id if hit is not None else None),
                    target_zh=target_zh,
                    metrics=metrics,
                )
            )
        return cards

    def estimate_stability(self, pose: FramePoseResult) -> float:
        if not pose.persons:
            return 0.0
        person = max(pose.persons, key=lambda item: item.score)
        return self._stability_for_person(person)

    def _review_metrics(
        self,
        pose: FramePoseResult,
        previous_pose: FramePoseResult,
        attacker: PosePerson | None,
        defender: PosePerson | None,
        action: CombatActionItem,
        hit: HitEvent | None,
        fatigue: dict,
    ) -> CombatReviewMetrics:
        if attacker is None:
            return CombatReviewMetrics()

        attacker_wrist = self._mean_points(attacker.keypoints_xy[[9, 10]])
        attacker_shoulder = self._mean_points(attacker.keypoints_xy[[5, 6]])
        torso_scale = np.linalg.norm(attacker.keypoints_xy[5] - attacker.keypoints_xy[11]) + 1e-6
        explosiveness_score = self._clip(np.linalg.norm(attacker_wrist - attacker_shoulder) / (torso_scale * 1.3))
        stability_score = self._stability_for_person(attacker)
        impact_score = self._clip(action.confidence + (0.2 if hit is not None else 0.0))

        if defender is None:
            return CombatReviewMetrics(
                impact_score=impact_score,
                balance_break_score=1.0 - stability_score,
                stability_score=stability_score,
                explosiveness_score=explosiveness_score,
                reaction_lag_score=0.35 if fatigue.get("level") == "high" else 0.0,
            )

        defender_head = defender.keypoints_xy[0]
        defender_torso = self._mean_points(defender.keypoints_xy[[5, 6, 11, 12]])
        target_point = defender_head if hit is not None and hit.target == "head" else defender_torso
        distance_score = self._clip(1.0 - np.linalg.norm(attacker_wrist - target_point) / (torso_scale * 1.4))
        guard_open_score = self._guard_open_score(defender)
        defender_stability = self._stability_for_person(defender)
        previous_defender = self._resolve_person_by_id(previous_pose, defender.person_id) or defender
        previous_guard_open = self._guard_open_score(previous_defender)
        reaction_lag_base = 0.75 if fatigue.get("level") == "high" else 0.45 if fatigue.get("level") == "medium" else 0.2
        reaction_lag_score = self._clip(reaction_lag_base + max(0.0, guard_open_score - previous_guard_open))
        balance_break_score = self._clip((1.0 - defender_stability) * 0.8 + max(0.0, distance_score - 0.35) * 0.4)

        return CombatReviewMetrics(
            distance_score=distance_score,
            impact_score=impact_score,
            guard_open_score=guard_open_score,
            balance_break_score=balance_break_score,
            stability_score=stability_score,
            explosiveness_score=explosiveness_score,
            reaction_lag_score=reaction_lag_score,
        )

    def _resolve_pair(self, pose: FramePoseResult, hit: HitEvent | None) -> tuple[PosePerson | None, PosePerson | None]:
        if not pose.persons:
            return None, None
        ordered = sorted(pose.persons, key=lambda item: item.score, reverse=True)
        attacker = ordered[0]
        defender = ordered[1] if len(ordered) > 1 else None
        if hit is None:
            return attacker, defender
        return self._resolve_person_by_id(pose, hit.attacker_id) or attacker, self._resolve_person_by_id(pose, hit.defender_id) or defender

    def _resolve_person_by_id(self, pose: FramePoseResult, person_id: int) -> PosePerson | None:
        for person in pose.persons:
            if person.person_id == person_id:
                return person
        return None

    def _guard_open_score(self, person: PosePerson) -> float:
        head = person.keypoints_xy[0]
        left_wrist = person.keypoints_xy[9]
        right_wrist = person.keypoints_xy[10]
        torso = np.linalg.norm(person.keypoints_xy[5] - person.keypoints_xy[11]) + 1e-6
        mean_dist = (np.linalg.norm(left_wrist - head) + np.linalg.norm(right_wrist - head)) / 2
        return self._clip(mean_dist / (torso * 1.2))

    def _stability_for_person(self, person: PosePerson) -> float:
        k = person.keypoints_xy
        shoulder_center = self._mean_points(k[[5, 6]])
        foot_center = self._mean_points(k[[15, 16]])
        torso = np.linalg.norm(k[5] - k[11]) + 1e-6
        x_dev = abs(shoulder_center[0] - foot_center[0]) / torso
        hip_center_y = (k[11][1] + k[12][1]) / 2
        support_depth = abs(hip_center_y - foot_center[1]) / torso
        return self._clip((1.0 - x_dev) * 0.7 + support_depth * 0.3)

    def _damage_zh(self, hit: HitEvent | None, unstable: bool, confidence: float) -> str:
        if hit is not None and unstable:
            return DAMAGE_RESULTS[4]
        if hit is not None and hit.target == "head":
            return DAMAGE_RESULTS[1]
        if hit is not None and hit.target == "body":
            return DAMAGE_RESULTS[2]
        if confidence >= 0.66:
            return DAMAGE_RESULTS[3]
        return DAMAGE_RESULTS[0]

    def _evade_failure_reason(
        self,
        metrics: CombatReviewMetrics,
        action_code: str,
        hit: HitEvent | None,
        fatigue: dict,
    ) -> str:
        if hit is None and metrics.impact_score < 0.55:
            return DEFAULT_EVADE_REASON
        if metrics.guard_open_score >= 0.62:
            return EVADE_REASONS[1]
        if metrics.balance_break_score >= 0.58:
            return EVADE_REASONS[2]
        if fatigue.get("level") == "high" or metrics.reaction_lag_score >= 0.72:
            return EVADE_REASONS[3]
        if metrics.distance_score >= 0.68:
            return EVADE_REASONS[0]
        if action_code in {"hook_punch", "kick", "block"} and metrics.impact_score >= 0.58:
            return EVADE_REASONS[4]
        return DEFAULT_EVADE_REASON

    def _suggestion_zh(self, action_code: str) -> str:
        meta = ACTION_CATALOG.get(action_code)
        if meta is None:
            return "保持基础站姿稳定，持续补充有效证据。"
        return meta["suggestion_zh"]

    def _action_zh(self, action_code: str) -> str:
        return ACTION_CATALOG.get(action_code, {}).get("action_zh", action_code)

    def _encode_crop(self, frame: np.ndarray, attacker: PosePerson | None, defender: PosePerson | None) -> str | None:
        crop = frame
        boxes = []
        if attacker is not None:
            boxes.append(attacker.bbox)
        if defender is not None:
            boxes.append(defender.bbox)
        if boxes:
            x1 = min(box[0] for box in boxes)
            y1 = min(box[1] for box in boxes)
            x2 = max(box[2] for box in boxes)
            y2 = max(box[3] for box in boxes)
            height, width = frame.shape[:2]
            margin_x = max(16, int((x2 - x1) * 0.18))
            margin_y = max(16, int((y2 - y1) * 0.18))
            x1 = max(0, x1 - margin_x)
            y1 = max(0, y1 - margin_y)
            x2 = min(width, x2 + margin_x)
            y2 = min(height, y2 + margin_y)
            crop = frame[y1:y2, x1:x2]
        ok, encoded = cv2.imencode(".jpg", crop)
        if not ok:
            return None
        return base64.b64encode(encoded.tobytes()).decode("ascii")

    def _format_timestamp(self, frame_index: int, fps: float) -> str:
        seconds = frame_index / max(1.0, fps)
        minutes = int(seconds // 60)
        remain = seconds - (minutes * 60)
        return f"{minutes:02d}:{remain:05.2f}"

    def _mean_points(self, points: np.ndarray) -> np.ndarray:
        return np.mean(points, axis=0)

    def _clip(self, value: float) -> float:
        return float(np.clip(value, 0.0, 1.0))
