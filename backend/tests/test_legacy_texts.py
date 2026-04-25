import numpy as np
from fastapi.testclient import TestClient

from main import _format_legacy_text, app
from schemas import AnalyzeMode, TacticalMessage, TacticalChatRequest
from services.pipeline import pipeline


def test_legacy_text_formatter_returns_readable_chinese():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    result = pipeline.analyze_frame(frame=frame, mode=AnalyzeMode.combat_full, frame_index=0, fps=0.0)
    text = _format_legacy_text(result)

    assert "综合评估结果" in text
    assert "姿势合规" in text
    assert "体力状态" in text
    assert "缁" not in text


def test_tactical_chat_returns_readable_chinese():
    client = TestClient(app)
    response = client.post(
        "/api/tactical-chat",
        json=TacticalChatRequest(
            scenario="道路盘查",
            messages=[TacticalMessage(role="user", content="我会先做外围警戒")],
        ).model_dump(),
    )

    assert response.status_code == 200
    text = response.json()["result"]
    assert "现场反馈" in text
    assert "处置点评" in text
    assert "下一问题" in text
