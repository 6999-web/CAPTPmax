from __future__ import annotations

import numpy as np

from cv.shooting_rules import EventType, PostureEvaluation, ShootingFlowStateMachine, ShootingRulesAnalyzer
from cv.types import FramePoseResult, FrameWeaponResult, PosePerson, WeaponDetection
from services.shooting_reporting import build_step_reports


def _person() -> PosePerson:
    k = np.array([
        [100, 40],
        [0, 0], [0, 0], [0, 0], [0, 0],
        [80, 80], [120, 80],
        [70, 95], [130, 95],
        [60, 100], [140, 100],
        [85, 130], [115, 130],
        [85, 165], [115, 165],
        [85, 200], [115, 200],
    ], dtype=float)
    c = np.ones((17,), dtype=float)
    return PosePerson(person_id=0, bbox=(50, 20, 150, 220), score=0.9, keypoints_xy=k, keypoints_conf=c)


def test_posture_evaluation_runs():
    rules = ShootingRulesAnalyzer()
    pose = FramePoseResult(persons=[_person()], hands=[])
    weapon = FrameWeaponResult(weapons=[WeaponDetection(cls_name='pistol', bbox=(130, 90, 170, 110), score=0.8, muzzle_direction='horizontal')])

    res = rules.evaluate_posture(pose, weapon, frame_index=0)
    assert 0.0 <= res.score <= 1.0
    assert isinstance(res.compliance, bool)
    assert any(v.code in {"ISO_TRIANGLE_WEAK", "HANDS_INCOMPLETE", "ARM_NOT_EXTENDED"} for v in res.violations)


def test_flow_state_machine_order_check():
    sm = ShootingFlowStateMachine()
    sm.ingest(EventType.check_weapon)
    sm.ingest(EventType.insert_magazine)
    sm.ingest(EventType.prepare_and_fire)
    sm.ingest(EventType.post_fire_check)
    assert sm.order_ok is True

    sm2 = ShootingFlowStateMachine()
    sm2.ingest(EventType.prepare_and_fire)
    sm2.ingest(EventType.check_weapon)
    assert sm2.order_ok is False


def test_muzzle_critical_alarm_branch_exists():
    rules = ShootingRulesAnalyzer()
    p1 = _person()
    p2 = PosePerson(person_id=1, bbox=(300, 20, 390, 220), score=0.8, keypoints_xy=p1.keypoints_xy.copy(), keypoints_conf=p1.keypoints_conf.copy())
    pose = FramePoseResult(persons=[p1, p2], hands=[])
    weapon = FrameWeaponResult(weapons=[WeaponDetection(cls_name='pistol', bbox=(40, 90, 180, 120), score=0.95, muzzle_direction='horizontal')])
    out = rules.evaluate_posture(pose, weapon, frame_index=1)
    severities = {v.severity for v in out.violations}
    assert severities.intersection({"high", "high_critical"})


def test_pre_fire_stage_requires_visible_pistol_and_basic_posture_score():
    rules = ShootingRulesAnalyzer()
    pose = FramePoseResult(persons=[_person()], hands=[])
    posture = rules.evaluate_posture(
        pose,
        FrameWeaponResult(
            weapons=[
                WeaponDetection(cls_name='pistol', bbox=(130, 90, 170, 110), score=0.8, muzzle_direction='horizontal'),
            ]
        ),
        frame_index=2,
    )

    event = rules.infer_flow_event(
        pose,
        FrameWeaponResult(
            weapons=[
                WeaponDetection(cls_name='pistol', bbox=(130, 90, 170, 110), score=0.8, muzzle_direction='horizontal'),
            ]
        ),
        posture,
    )

    assert event == EventType.insert_magazine


def test_pre_fire_stage_not_triggered_by_missing_weapon_detection():
    rules = ShootingRulesAnalyzer()
    pose = FramePoseResult(persons=[_person()], hands=[])
    posture = PostureEvaluation(compliance=True, score=0.9, violations=[])

    event = rules.infer_flow_event(pose, FrameWeaponResult(weapons=[]), posture)

    assert event is None


def test_pre_fire_stage_not_triggered_by_low_posture_score():
    rules = ShootingRulesAnalyzer()
    pose = FramePoseResult(persons=[_person()], hands=[])
    posture = PostureEvaluation(compliance=False, score=0.25, violations=[])

    event = rules.infer_flow_event(
        pose,
        FrameWeaponResult(
            weapons=[WeaponDetection(cls_name='pistol', bbox=(130, 90, 170, 110), score=0.8, muzzle_direction='horizontal')]
        ),
        posture,
    )

    assert event is None


def test_violation_translation_returns_chinese_issue_cards():
    rules = ShootingRulesAnalyzer()
    pose = FramePoseResult(persons=[_person()], hands=[])
    weapon = FrameWeaponResult(weapons=[WeaponDetection(cls_name='pistol', bbox=(130, 90, 170, 110), score=0.8, muzzle_direction='horizontal')])
    out = rules.evaluate_posture(pose, weapon, frame_index=3)
    _, reports, issues = build_step_reports(
        flow_stage=EventType.prepare_and_fire.value,
        flow_order_ok=True,
        violations=out.violations,
        evidence=[],
        fps=12.0,
    )

    assert any("双臂" in item.title or "手臂" in item.title for item in issues)
    assert len(reports) == 5

