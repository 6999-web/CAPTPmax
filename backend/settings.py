from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: str | None, default: list[str]) -> list[str]:
    if value is None or not value.strip():
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class AppSettings:
    project_name: str = "CAPTP API"
    host: str = os.getenv("CAPTP_HOST", "0.0.0.0")
    port: int = int(os.getenv("CAPTP_PORT", "6063"))

    # Runtime profile
    runtime_profile: str = os.getenv("CAPTP_RUNTIME_PROFILE", "cpu").lower()
    scene_cardinality: str = os.getenv("CAPTP_SCENE_CARDINALITY", "multi_person")

    # Optional model paths
    yolo_pose_model: str = os.getenv("YOLO_POSE_MODEL", "yolov8n-pose.pt")
    yolo_weapon_model: str = os.getenv("YOLO_WEAPON_MODEL", "")
    mmpose_config: str = os.getenv("MMPOSE_CONFIG", "")
    mmpose_checkpoint: str = os.getenv("MMPOSE_CHECKPOINT", "")
    mmaction_config: str = os.getenv("MMACTION_CONFIG", "")
    mmaction_checkpoint: str = os.getenv("MMACTION_CHECKPOINT", "")

    # Optional cloud reasoning (never overrides CV facts)
    reasoning_enabled: bool = _as_bool(os.getenv("REASONING_BRIDGE_ENABLED"), False)
    reasoning_provider: str = os.getenv("REASONING_PROVIDER", "openai")
    reasoning_base_url: str = os.getenv("REASONING_BASE_URL", "")
    reasoning_model: str = os.getenv("REASONING_MODEL", "")
    reasoning_api_key: str = os.getenv("REASONING_API_KEY", "")

    # Backward-compatible tactical chat model fields
    tactical_model: str = os.getenv("TACTICAL_MODEL", "")
    mediapipe_model_complexity: int = int(os.getenv("MEDIAPIPE_MODEL_COMPLEXITY", "1"))
    mediapipe_frame_skip: int = int(os.getenv("MEDIAPIPE_FRAME_SKIP", "0"))

    # Reference image sources (GitHub whitelist with local fallback)
    github_reference_sources: tuple[str, ...] = tuple(
        _as_list(
            os.getenv("GITHUB_REFERENCE_SOURCES"),
            [
                "https://commons.wikimedia.org/wiki/Special:FilePath/Fbiagentsgun.jpg",
                "https://commons.wikimedia.org/wiki/Special:FilePath/Firing-Sig-Sauer-P229s-at-the-range1.jpg",
            ],
        )
    )
    reference_image_fallback: str = os.getenv("REFERENCE_IMAGE_FALLBACK", "/school_badge.jpg")

    @property
    def device(self) -> str:
        if self.runtime_profile == "gpu":
            return "cuda"
        return "cpu"

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parent


settings = AppSettings()

