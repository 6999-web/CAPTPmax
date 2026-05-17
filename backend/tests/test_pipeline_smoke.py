from __future__ import annotations

import numpy as np

from schemas import AnalyzeMode
from services.pipeline import VisionPipeline


def test_pipeline_frame_smoke():
    p = VisionPipeline()
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    out = p.analyze_frame(frame, mode=AnalyzeMode.combat_full, frame_index=0, fps=0.0)
    assert out.meta.device in {"cpu", "cuda"}
    assert out.shooting.flow_stage is not None
    assert out.shooting.ui_stage_label
    assert isinstance(out.shooting.step_reports, list)
    assert out.combat.supported_actions
    assert isinstance(out.combat.review_cards, list)

