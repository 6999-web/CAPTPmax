from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalyzeMode(str, Enum):
    shooting_posture = "shooting_posture"
    shooting_flow = "shooting_flow"
    combat_action = "combat_action"
    combat_full = "combat_full"


class AnalyzeSource(str, Enum):
    image = "image"
    video = "video"
    stream = "stream"


class VideoAnalysisStrategy(str, Enum):
    adaptive = "adaptive"
    five_way = "five_way"
    single_pass = "single_pass"


class ShootingFlowStage(str, Enum):
    pass_gun_method_1 = "pass_gun_method_1"
    pass_gun_method_2 = "pass_gun_method_2"
    check_weapon = "check_weapon"
    insert_magazine = "insert_magazine"
    prepare_and_fire = "prepare_and_fire"
    post_fire_check = "post_fire_check"


class Violation(BaseModel):
    code: str
    severity: Literal["low", "medium", "high", "high_critical"]
    description: str
    rule_ref: str
    evidence_frame_idx: int = 0


class ShootingEvidence(BaseModel):
    frame_index: int
    label: str
    confidence: float = 0.0


class ShootingIssueEvidence(BaseModel):
    frame_index: int = 0
    timestamp: str | None = None
    label: str = ""
    confidence: float = 0.0
    detail: str | None = None


class ShootingPrimaryIssue(BaseModel):
    issue_key: str
    title: str
    step_key: str
    step_label_zh: str
    trigger_reason: str
    why_flagged: list[str] = Field(default_factory=list)
    risk: str
    improvement_suggestion: str
    evidence: list[ShootingIssueEvidence] = Field(default_factory=list)


class ShootingStepReport(BaseModel):
    step_key: str
    step_label_zh: str
    status: Literal["pending", "current", "completed", "issue"]
    detected_actions: list[str] = Field(default_factory=list)
    missing_actions: list[str] = Field(default_factory=list)
    issues: list[ShootingPrimaryIssue] = Field(default_factory=list)
    evidence: list[ShootingEvidence] = Field(default_factory=list)
    why_flagged: list[str] = Field(default_factory=list)


class ShootingResult(BaseModel):
    posture_compliance: bool = False
    posture_score: float = 0.0
    flow_stage: ShootingFlowStage = ShootingFlowStage.check_weapon
    flow_order_ok: bool = True
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[ShootingEvidence] = Field(default_factory=list)
    ui_stage_label: str = "初次验枪"
    step_reports: list[ShootingStepReport] = Field(default_factory=list)
    primary_issues: list[ShootingPrimaryIssue] = Field(default_factory=list)


class CombatActionItem(BaseModel):
    action: str
    confidence: float
    actor_id: int | None = None
    frame_index: int = 0


class CombatQuartet(BaseModel):
    action: str
    effect: str
    reason: str
    suggestion: str
    confidence: float
    timestamp_range: tuple[float, float]


class HitEvent(BaseModel):
    attacker_id: int
    defender_id: int
    target: str
    confidence: float
    frame_index: int


class FatigueResult(BaseModel):
    level: Literal["low", "medium", "high"]
    score: float
    reason: str


class CombatReviewMetrics(BaseModel):
    distance_score: float = 0.0
    impact_score: float = 0.0
    guard_open_score: float = 0.0
    balance_break_score: float = 0.0
    stability_score: float = 0.0
    explosiveness_score: float = 0.0
    reaction_lag_score: float = 0.0


class CombatReviewCard(BaseModel):
    card_id: str
    frame_index: int = 0
    timestamp: str = "00:00.00"
    image_b64: str | None = None
    action_code: str
    action_zh: str
    damage_zh: str
    evade_failure_reason_zh: str
    summary_zh: str
    confidence: float = 0.0
    attacker_id: int | None = None
    defender_id: int | None = None
    target_zh: str = "未判定"
    metrics: CombatReviewMetrics = Field(default_factory=CombatReviewMetrics)


class SupportedCombatAction(BaseModel):
    action_code: str
    action_zh: str
    description_zh: str
    typical_damage_zh: str
    common_evade_failure_reasons_zh: list[str] = Field(default_factory=list)


class CombatResult(BaseModel):
    actions: list[CombatActionItem] = Field(default_factory=list)
    quartets: list[CombatQuartet] = Field(default_factory=list)
    fatigue: FatigueResult = Field(default_factory=lambda: FatigueResult(level="low", score=0.0, reason="insufficient_motion_history"))
    hit_events: list[HitEvent] = Field(default_factory=list)
    stability: float = 0.0
    review_cards: list[CombatReviewCard] = Field(default_factory=list)
    supported_actions: list[SupportedCombatAction] = Field(default_factory=list)


class MetaResult(BaseModel):
    fps: float = 0.0
    latency_ms: float = 0.0
    persons: int = 0
    device: str = "cpu"
    fallback_used: bool = False
    analysis_phase: Literal["single", "preview", "final"] = "single"
    is_final: bool = True
    performance: dict[str, float] = Field(default_factory=dict)


class AttributionEvidence(BaseModel):
    timestamp: str
    details: str
    step_key: str | None = None


class EventSpot(BaseModel):
    event_type: str
    timestamp_seconds: float
    timestamp: str
    confidence: float = 0.0
    details: str


class WindowComparison(BaseModel):
    minute_1: dict[str, float] = Field(default_factory=dict)
    minute_3: dict[str, float] = Field(default_factory=dict)
    changes: dict[str, float] = Field(default_factory=dict)


class AttributionResult(BaseModel):
    result: str = "Undetermined"
    primary_reason: str = ""
    evidence: AttributionEvidence | None = None
    technical_feedback: str = ""
    event_spots: list[EventSpot] = Field(default_factory=list)
    window_comparison: WindowComparison = Field(default_factory=WindowComparison)
    diagnoses: dict[str, Any] = Field(default_factory=dict)


class AnalyzeResult(BaseModel):
    shooting: ShootingResult
    combat: CombatResult
    meta: MetaResult
    reasoning: str | None = None
    attribution: AttributionResult | None = None


class LongVideoJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class LongVideoJobResponse(BaseModel):
    job_id: str
    status: LongVideoJobStatus
    progress: int = 0
    result: AnalyzeResult | None = None
    error: str | None = None


class CombatSegmentManifestItem(BaseModel):
    segment_id: int
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    frame_times_seconds: list[float] = Field(default_factory=list)
    filenames: list[str] = Field(default_factory=list)


class CombatVideoFastRequestMeta(BaseModel):
    mode: AnalyzeMode = AnalyzeMode.combat_full
    strategy: VideoAnalysisStrategy = VideoAnalysisStrategy.adaptive
    duration_seconds: float = 0.0
    client_extract_ms: float = 0.0
    manifest: list[CombatSegmentManifestItem] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    mode: AnalyzeMode = AnalyzeMode.combat_full
    source: AnalyzeSource = AnalyzeSource.image
    scene_cardinality: str = "multi_person"


class RtspAnalyzeRequest(BaseModel):
    url: str
    mode: AnalyzeMode = AnalyzeMode.combat_full
    frame_index: int = 0
    fps: float = 12.0


class TacticalMessage(BaseModel):
    role: str
    content: str


class TacticalChatRequest(BaseModel):
    messages: list[TacticalMessage]
    scenario: str | None = None
    scenarioContext: str | None = None


class ModelHealth(BaseModel):
    ready: bool
    runtime_profile: str
    device: str
    loaded_models: dict[str, bool]
    versions: dict[str, Any]

