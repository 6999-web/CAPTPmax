from __future__ import annotations

from services.shooting_training import Action, TrainingWorkflowMachine


def test_workflow_happy_path_reaches_done():
    sm = TrainingWorkflowMachine()
    steps = [
        Action.RECEIVE_WEAPON,
        Action.REMOVE_MAG,
        Action.CHECK_CHAMBER,
        Action.SAFE_ON,
        Action.INSERT_MAG,
        Action.HOLSTER_OR_READY,
        Action.ISO_GRIP,
        Action.RACK_SLIDE,
        Action.FIRE,
        Action.FINAL_REMOVE_MAG,
        Action.FINAL_CHECK_CHAMBER,
    ]
    for step in steps:
        sm.consume(step)
    assert sm.stage.value == "DONE"


def test_final_check_wrong_order_triggers_error():
    sm = TrainingWorkflowMachine()
    steps = [
        Action.RECEIVE_WEAPON,
        Action.REMOVE_MAG,
        Action.CHECK_CHAMBER,
        Action.SAFE_ON,
        Action.INSERT_MAG,
        Action.HOLSTER_OR_READY,
        Action.ISO_GRIP,
        Action.RACK_SLIDE,
        Action.FIRE,
    ]
    for step in steps:
        sm.consume(step)
    bad = sm.consume(Action.FINAL_CHECK_CHAMBER)
    assert bad.violation is not None
    assert bad.violation.code == "FINAL_ORDER_ERROR"
