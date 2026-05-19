from __future__ import annotations

from pathlib import Path


MERMAID = """flowchart LR
    A["A: 领枪/接枪"] --> B["B: 验枪(卸弹匣->查弹膛->关保险)"]
    B --> C["C: 射击中姿态持续监控"]
    C --> D["D: 二次验枪(先卸弹匣->后查弹膛)"]
    D --> E["通过"]
    D -. 先查弹膛后卸弹匣 .-> X["FINAL_ORDER_ERROR"]
"""


def _contains_all(path: Path, patterns: list[str]) -> bool:
    text = path.read_text(encoding="utf-8")
    return all(pattern in text for pattern in patterns)


def run_static_audit(root: Path) -> dict:
    shooting_rules = root / "cv" / "shooting_rules.py"
    shooting_training = root / "services" / "shooting_training.py"
    shooting_vue = root.parent / "frontend" / "src" / "components" / "Shooting.vue"

    checks = {
        "geometry_upper_body_only": _contains_all(
            shooting_rules, ["_check_isosceles_triangle", "_check_arm_extension", "_check_head_alignment"]
        ),
        "fine_hand_logic": _contains_all(
            shooting_rules, ["THUMB_PARALLEL_WEAK", "EJECTION_PORT_HAND_RISK", "HANDS_INCOMPLETE"]
        ),
        "muzzle_critical_alarm": _contains_all(
            shooting_rules, ["MUZZLE_NON_SAFE_ZONE", "high_critical", "_muzzle_vector"]
        ),
        "strict_workflow_state_machine": _contains_all(
            shooting_training, ["A_RECEIVE_WEAPON", "B_INITIAL_CHECK", "C_PREPARE_FIRE", "D_FIRE", "E_FINAL_CHECK", "FINAL_ORDER_ERROR"]
        ),
        "ui_single_upload_image": _contains_all(
            shooting_vue, ['v-if="cameraActive"', 'v-else-if="capturedImage"', 'v-else-if="previewUrl"']
        ),
        "ui_dynamic_remove_logic": _contains_all(shooting_vue, ["removeErrorCard", "msg.event === 'error:remove'"]),
    }
    return checks


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    checks = run_static_audit(backend_root)
    print("=== Acceptance Static Audit ===")
    for key, ok in checks.items():
        print(f"{key}: {'PASS' if ok else 'FAIL'}")
    print("\\n=== Workflow Mermaid ===")
    print(MERMAID)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
