from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import cv2
import numpy as np

from schemas import (
    AnalyzeMode,
    AnalyzeResult,
    CombatSegmentManifestItem,
    CombatResult,
    FatigueResult,
    MetaResult,
    ShootingEvidence,
    ShootingFlowStage,
    ShootingResult,
    VideoAnalysisStrategy,
)
from settings import settings
from cv.action_temporal import ActionTemporalAnalyzer
from cv.combat_analysis import CombatAnalyzer
from cv.fatigue_engine import FatigueEngine
from cv.pose_engine import PoseEngine
from cv.reasoning_bridge import ReasoningBridge
from cv.shooting_rules import ShootingFlowStateMachine, ShootingRulesAnalyzer
from cv.types import FramePoseResult, FrameWeaponResult
from cv.video_input import VideoInputService
from cv.weapon_engine import WeaponEngine
from services.combat_deep_analyst import CombatDeepAnalyst
from services.shooting_reporting import build_step_reports


@dataclass
class CombatSegmentArtifacts:
    segment_id: int
    frames: list[np.ndarray]
    frame_times_seconds: list[float]
    pose_seq: list[FramePoseResult]
    weapon_seq: list[FrameWeaponResult]
    actions: list
    hits: list
    fallback_used: bool
    performance: dict[str, float]


class VisionPipeline:
    def __init__(self) -> None:
        self.video_input = VideoInputService()
        self.pose_engine = PoseEngine()
        self.weapon_engine = WeaponEngine()
        self.shooting_rules = ShootingRulesAnalyzer()
        self.temporal = ActionTemporalAnalyzer()
        self.combat = CombatAnalyzer()
        self.fatigue = FatigueEngine()
        self.reasoning = ReasoningBridge()
        self.deep_analyst = CombatDeepAnalyst()
        self.stream_pose_window: deque = deque(maxlen=12)
        self.flow_state = ShootingFlowStateMachine()

    def model_health(self) -> dict:
        return {
            "ready": True,
            "runtime_profile": settings.runtime_profile,
            "device": settings.device,
            "loaded_models": {
                "yolo_pose": self.pose_engine.status.yolo_ready,
                "mediapipe": self.pose_engine.status.mediapipe_ready,
                "mmpose": self.pose_engine.status.mmpose_ready,
                "yolo_weapon": self.weapon_engine.status.yolo_ready,
                "mmaction2": self.temporal.status.mmaction_ready,
                "st_gcn": self.temporal.status.stgcn_ready,
                "agcn": self.temporal.status.agcn_ready,
            },
            "versions": {
                "opencv": cv2.__version__,
                "numpy": np.__version__,
            },
        }

    def analyze_file(self, content: bytes, filename: str, content_type: str, mode: AnalyzeMode) -> AnalyzeResult:
        t0 = time.perf_counter()
        source = self.video_input.infer_source_type(filename, content_type)

        if source == "image":
            frame = self.video_input.decode_image(content)
            result = self._analyze_frame_internal(frame, mode=mode, frame_index=0, fps=0.0)
        else:
            bundle = self.video_input.sample_video_bundle(content, max_frames=48, profile="uniform")
            result = self._analyze_sequence_internal(
                frames=bundle["frames"],
                mode=mode,
                fps=bundle["fps"],
                duration_seconds=bundle["duration_seconds"],
                attach_attribution=bundle["duration_seconds"] >= 90.0 and mode == AnalyzeMode.combat_full,
                review_card_limit=8,
                analysis_phase="single",
                is_final=True,
            )

        result.meta.latency_ms = (time.perf_counter() - t0) * 1000.0
        result.meta.analysis_phase = "single"
        result.meta.is_final = True
        result.meta.performance = {
            "client_extract_ms": 0.0,
            "backend_parse_ms": 0.0,
            "backend_infer_ms": max(0.0, result.meta.latency_ms),
            "backend_post_ms": 0.0,
            "total_pipeline_ms": result.meta.latency_ms,
        }
        return result

    def analyze_combat_preview(self, frames: list[np.ndarray], mode: AnalyzeMode, duration_seconds: float = 0.0) -> AnalyzeResult:
        t0 = time.perf_counter()
        result = self._analyze_sequence_internal(
            frames=frames,
            mode=mode,
            fps=max(1.0, len(frames) / max(duration_seconds, 1.0)) if duration_seconds else 12.0,
            duration_seconds=duration_seconds,
            attach_attribution=False,
            review_card_limit=4,
            analysis_phase="preview",
            is_final=False,
        )
        result.meta.latency_ms = (time.perf_counter() - t0) * 1000.0
        result.meta.performance = {
            "client_extract_ms": 0.0,
            "backend_parse_ms": 0.0,
            "backend_infer_ms": max(0.0, result.meta.latency_ms),
            "backend_post_ms": 0.0,
            "total_pipeline_ms": result.meta.latency_ms,
        }
        return result

    def analyze_combat_video_fast(
        self,
        segment_frames: list[list[np.ndarray]],
        manifest: list[CombatSegmentManifestItem],
        mode: AnalyzeMode,
        strategy: VideoAnalysisStrategy,
        duration_seconds: float,
        client_extract_ms: float = 0.0,
    ) -> AnalyzeResult:
        t0 = time.perf_counter()
        parse_done = time.perf_counter()
        if not segment_frames or not manifest:
            raise ValueError("Fast combat endpoint requires segment frames and manifest")

        if len(segment_frames) != len(manifest):
            raise ValueError("Segment frame groups do not match manifest items")

        for item, frames in zip(manifest, segment_frames, strict=False):
            if len(item.frame_times_seconds) != len(frames):
                raise ValueError(f"Manifest frame count mismatch for segment {item.segment_id}")

        infer_start = time.perf_counter()
        max_workers = max(1, min(5, len(segment_frames)))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="captp-combat-fast") as executor:
            futures = [
                executor.submit(self._extract_combat_segment, item, frames)
                for item, frames in zip(manifest, segment_frames, strict=False)
            ]
            segments = [future.result() for future in futures]
        infer_done = time.perf_counter()

        result = self._finalize_combat_segments(
            segments=segments,
            mode=mode,
            strategy=strategy,
            duration_seconds=duration_seconds,
            analysis_phase="final",
            is_final=True,
            review_card_limit=8,
        )
        done = time.perf_counter()
        result.meta.latency_ms = (done - t0) * 1000.0
        result.meta.performance = {
            "client_extract_ms": float(client_extract_ms),
            "backend_parse_ms": (parse_done - t0) * 1000.0,
            "backend_infer_ms": (infer_done - infer_start) * 1000.0,
            "backend_post_ms": (done - infer_done) * 1000.0,
            "total_pipeline_ms": float(client_extract_ms) + ((done - t0) * 1000.0),
        }
        return result

    def analyze_long_video(self, content: bytes, filename: str, content_type: str, mode: AnalyzeMode) -> AnalyzeResult:
        t0 = time.perf_counter()
        source = self.video_input.infer_source_type(filename, content_type)
        if source != "video":
            raise ValueError("Long video endpoint requires video input")

        parse_start = time.perf_counter()
        video_meta = self.video_input.inspect_video(content)
        frame_budget = self.video_input.long_video_frame_budget(video_meta["duration_seconds"])
        bundle = self.video_input.sample_video_bundle(
            content,
            max_frames=frame_budget,
            profile="budgeted",
            sequential=True,
        )
        parse_done = time.perf_counter()
        result = self._analyze_sequence_internal(
            frames=bundle["frames"],
            mode=mode,
            fps=bundle["fps"],
            duration_seconds=bundle["duration_seconds"],
            attach_attribution=mode == AnalyzeMode.combat_full,
            review_card_limit=8,
            analysis_phase="final",
            is_final=True,
        )
        done = time.perf_counter()
        result.meta.latency_ms = (done - t0) * 1000.0
        result.meta.performance = {
            "client_extract_ms": 0.0,
            "backend_parse_ms": (parse_done - parse_start) * 1000.0,
            "backend_infer_ms": max(0.0, result.meta.latency_ms - ((parse_done - parse_start) * 1000.0)),
            "backend_post_ms": 0.0,
            "total_pipeline_ms": result.meta.latency_ms,
        }
        return result

    def analyze_long_video_async_final(
        self,
        content: bytes,
        filename: str,
        content_type: str,
        mode: AnalyzeMode,
        progress_callback: Callable[[int], None] | None = None,
    ) -> AnalyzeResult:
        t0 = time.perf_counter()
        if progress_callback is not None:
            progress_callback(5)

        source = self.video_input.infer_source_type(filename, content_type)
        if source != "video":
            raise ValueError("Long video endpoint requires video input")

        parse_start = time.perf_counter()
        video_meta = self.video_input.inspect_video(content)
        frame_budget = self.video_input.long_video_frame_budget(video_meta["duration_seconds"])
        if progress_callback is not None:
            progress_callback(15)

        bundle = self.video_input.sample_video_bundle(
            content,
            max_frames=frame_budget,
            profile="budgeted",
            sequential=True,
        )
        parse_done = time.perf_counter()
        if progress_callback is not None:
            progress_callback(40)

        result = self._analyze_sequence_internal(
            frames=bundle["frames"],
            mode=mode,
            fps=bundle["fps"],
            duration_seconds=bundle["duration_seconds"],
            attach_attribution=mode == AnalyzeMode.combat_full,
            review_card_limit=8,
            analysis_phase="final",
            is_final=True,
            progress_callback=progress_callback,
        )
        result.meta.latency_ms = (time.perf_counter() - t0) * 1000.0
        result.meta.performance = {
            "client_extract_ms": 0.0,
            "backend_parse_ms": (parse_done - parse_start) * 1000.0,
            "backend_infer_ms": max(0.0, result.meta.latency_ms - ((parse_done - parse_start) * 1000.0)),
            "backend_post_ms": 0.0,
            "total_pipeline_ms": result.meta.latency_ms,
        }
        if progress_callback is not None:
            progress_callback(100)
        return result

    def analyze_frame(self, frame: np.ndarray, mode: AnalyzeMode, frame_index: int = 0, fps: float = 0.0) -> AnalyzeResult:
        t0 = time.perf_counter()
        result = self._analyze_frame_internal(frame, mode=mode, frame_index=frame_index, fps=fps)
        result.meta.latency_ms = (time.perf_counter() - t0) * 1000.0
        result.meta.performance = {
            "client_extract_ms": 0.0,
            "backend_parse_ms": 0.0,
            "backend_infer_ms": max(0.0, result.meta.latency_ms),
            "backend_post_ms": 0.0,
            "total_pipeline_ms": result.meta.latency_ms,
        }
        return result

    def _analyze_sequence_internal(
        self,
        frames: list[np.ndarray],
        mode: AnalyzeMode,
        fps: float,
        duration_seconds: float = 0.0,
        attach_attribution: bool = False,
        review_card_limit: int = 8,
        analysis_phase: str = "single",
        is_final: bool = True,
        progress_callback: Callable[[int], None] | None = None,
    ) -> AnalyzeResult:
        if not frames:
            return AnalyzeResult(
                shooting=self._build_placeholder_shooting(),
                combat=CombatResult(supported_actions=self.combat.supported_actions()),
                meta=MetaResult(fps=fps, persons=0, device=settings.device, fallback_used=True, analysis_phase=analysis_phase, is_final=is_final),
                reasoning=None,
                attribution=None,
            )

        if self._is_combat_mode(mode):
            return self._analyze_combat_sequence(
                frames=frames,
                mode=mode,
                fps=fps,
                duration_seconds=duration_seconds,
                attach_attribution=attach_attribution,
                review_card_limit=review_card_limit,
                analysis_phase=analysis_phase,
                is_final=is_final,
                progress_callback=progress_callback,
            )

        return self._analyze_full_sequence(
            frames=frames,
            mode=mode,
            fps=fps,
            duration_seconds=duration_seconds,
            attach_attribution=attach_attribution,
            analysis_phase=analysis_phase,
            is_final=is_final,
        )

    def _analyze_combat_sequence(
        self,
        frames: list[np.ndarray],
        mode: AnalyzeMode,
        fps: float,
        duration_seconds: float,
        attach_attribution: bool,
        review_card_limit: int,
        analysis_phase: str,
        is_final: bool,
        progress_callback: Callable[[int], None] | None = None,
    ) -> AnalyzeResult:
        if progress_callback is not None:
            progress_callback(55)
        segment = self._extract_combat_segment(
            CombatSegmentManifestItem(
                segment_id=0,
                start_seconds=0.0,
                end_seconds=duration_seconds,
                frame_times_seconds=self._uniform_frame_times(len(frames), duration_seconds),
                filenames=[],
            ),
            frames,
        )
        if progress_callback is not None:
            progress_callback(75)
        result = self._finalize_combat_segments(
            segments=[segment],
            mode=mode,
            strategy=VideoAnalysisStrategy.single_pass,
            duration_seconds=duration_seconds,
            analysis_phase=analysis_phase,
            is_final=is_final,
            review_card_limit=review_card_limit,
            attach_attribution=attach_attribution,
        )
        if progress_callback is not None:
            progress_callback(95 if attach_attribution else 90)
        result.meta.fps = fps
        return result

    def _extract_combat_segment(
        self,
        manifest_item: CombatSegmentManifestItem,
        frames: list[np.ndarray],
    ) -> CombatSegmentArtifacts:
        t0 = time.perf_counter()
        pose_seq = self.pose_engine.infer_batch(frames)
        infer_done = time.perf_counter()
        weapon_seq = [FrameWeaponResult(fallback_used=True) for _ in frames]
        actions = []
        hits = []
        fallback_used = False

        for idx, pose in enumerate(pose_seq):
            temporal_one = self.temporal.analyze_frame(pose, weapon_seq[idx])
            actions.extend(self.combat.build_actions(temporal_one.dominant_action, temporal_one.confidence, idx))
            hits.extend(self.combat.estimate_hits(pose, idx))
            fallback_used = fallback_used or pose.fallback_used

        return CombatSegmentArtifacts(
            segment_id=manifest_item.segment_id,
            frames=list(frames),
            frame_times_seconds=list(manifest_item.frame_times_seconds),
            pose_seq=pose_seq,
            weapon_seq=weapon_seq,
            actions=actions,
            hits=hits,
            fallback_used=fallback_used,
            performance={
                "backend_infer_ms": (infer_done - t0) * 1000.0,
                "backend_post_ms": (time.perf_counter() - infer_done) * 1000.0,
            },
        )

    def _finalize_combat_segments(
        self,
        segments: list[CombatSegmentArtifacts],
        mode: AnalyzeMode,
        strategy: VideoAnalysisStrategy,
        duration_seconds: float,
        analysis_phase: str,
        is_final: bool,
        review_card_limit: int,
        attach_attribution: bool | None = None,
    ) -> AnalyzeResult:
        merged = self._merge_combat_segments(segments, duration_seconds=duration_seconds)
        global_frames = merged["frames"]
        pose_seq = merged["pose_seq"]
        weapon_seq = merged["weapon_seq"]
        all_actions = merged["actions"]
        all_hits = merged["hits"]
        fps = merged["fps"]
        if attach_attribution is None:
            attach_attribution = mode == AnalyzeMode.combat_full

        fatigue = self.fatigue.update(pose_seq)
        quartets = self.combat.build_quartets(all_actions, all_hits, fatigue, fps or 12.0)
        review_actions = self._select_review_actions(all_actions, all_hits, review_card_limit)
        review_hits = [hit for hit in all_hits if any(hit.frame_index == action.frame_index for action in review_actions)]
        review_cards = self.combat.build_review_cards(
            frames=global_frames,
            poses=pose_seq,
            actions=review_actions,
            hits=review_hits,
            fatigue=fatigue,
            fps=fps or 12.0,
        )

        attribution = None
        if attach_attribution:
            attribution = self.deep_analyst.analyze(
                pose_sequence=pose_seq,
                weapon_sequence=weapon_seq,
                shooting_issues=[],
                fps=fps or 1.0,
                duration_seconds=duration_seconds or float(len(global_frames)),
            )

        return AnalyzeResult(
            shooting=self._build_placeholder_shooting(),
            combat=CombatResult(
                actions=all_actions,
                quartets=quartets,
                fatigue=FatigueResult(**fatigue),
                hit_events=all_hits,
                stability=float(np.mean([self.combat.estimate_stability(p) for p in pose_seq])) if pose_seq else 0.0,
                review_cards=review_cards,
                supported_actions=self.combat.supported_actions(),
            ),
            meta=MetaResult(
                fps=fps,
                persons=len(pose_seq[-1].persons) if pose_seq else 0,
                device=settings.device,
                fallback_used=any(segment.fallback_used for segment in segments),
                analysis_phase=analysis_phase,
                is_final=is_final,
            ),
            reasoning=None,
            attribution=attribution,
        )

    def _merge_combat_segments(self, segments: list[CombatSegmentArtifacts], duration_seconds: float) -> dict:
        merged_frames: list[np.ndarray] = []
        merged_pose_seq: list[FramePoseResult] = []
        merged_weapon_seq: list[FrameWeaponResult] = []
        time_rows: list[tuple[float, int, int, np.ndarray, FramePoseResult, FrameWeaponResult]] = []

        for segment in segments:
            for local_idx, (frame, pose, weapon) in enumerate(zip(segment.frames, segment.pose_seq, segment.weapon_seq, strict=False)):
                if local_idx >= len(segment.frame_times_seconds):
                    continue
                time_rows.append((segment.frame_times_seconds[local_idx], segment.segment_id, local_idx, frame, pose, weapon))

        time_rows.sort(key=lambda item: (item[0], item[1], item[2]))
        frame_index_map: dict[tuple[int, int], int] = {}
        time_by_index: dict[int, float] = {}

        for global_idx, (ts, segment_id, local_idx, frame, pose, weapon) in enumerate(time_rows):
            frame_index_map[(segment_id, local_idx)] = global_idx
            time_by_index[global_idx] = ts
            merged_frames.append(frame)
            merged_pose_seq.append(pose)
            merged_weapon_seq.append(weapon)

        merged_actions = []
        for segment in segments:
            for action in segment.actions:
                mapped_index = frame_index_map.get((segment.segment_id, action.frame_index))
                if mapped_index is None:
                    continue
                merged_actions.append(action.model_copy(update={"frame_index": mapped_index}))

        merged_hits = []
        for segment in segments:
            for hit in segment.hits:
                mapped_index = frame_index_map.get((segment.segment_id, hit.frame_index))
                if mapped_index is None:
                    continue
                merged_hits.append(hit.model_copy(update={"frame_index": mapped_index}))

        merged_actions = self._dedupe_actions(merged_actions, time_by_index)
        merged_hits = self._dedupe_hits(merged_hits, time_by_index)
        merged_duration = duration_seconds or (max(time_by_index.values()) if time_by_index else 0.0)
        fps = max(1.0, len(merged_frames) / max(merged_duration, 1.0))
        return {
            "frames": merged_frames,
            "pose_seq": merged_pose_seq,
            "weapon_seq": merged_weapon_seq,
            "actions": merged_actions,
            "hits": merged_hits,
            "fps": fps,
        }

    def _dedupe_actions(self, actions: list, time_by_index: dict[int, float], tolerance_seconds: float = 0.75) -> list:
        deduped: list = []
        for action in sorted(actions, key=lambda item: time_by_index.get(item.frame_index, 0.0)):
            current_time = time_by_index.get(action.frame_index, 0.0)
            replaced = False
            for idx, kept in enumerate(deduped):
                kept_time = time_by_index.get(kept.frame_index, 0.0)
                if kept.action == action.action and abs(current_time - kept_time) < tolerance_seconds:
                    if action.confidence > kept.confidence:
                        deduped[idx] = action
                    replaced = True
                    break
            if not replaced:
                deduped.append(action)
        return deduped

    def _dedupe_hits(self, hits: list, time_by_index: dict[int, float], tolerance_seconds: float = 0.75) -> list:
        deduped: list = []
        for hit in sorted(hits, key=lambda item: time_by_index.get(item.frame_index, 0.0)):
            current_time = time_by_index.get(hit.frame_index, 0.0)
            replaced = False
            for idx, kept in enumerate(deduped):
                kept_time = time_by_index.get(kept.frame_index, 0.0)
                same_pair = kept.attacker_id == hit.attacker_id and kept.defender_id == hit.defender_id and kept.target == hit.target
                if same_pair and abs(current_time - kept_time) < tolerance_seconds:
                    if hit.confidence > kept.confidence:
                        deduped[idx] = hit
                    replaced = True
                    break
            if not replaced:
                deduped.append(hit)
        return deduped

    def _select_review_actions(self, actions: list, hits: list, limit: int) -> list:
        hit_frames = {hit.frame_index for hit in hits}
        ranked = sorted(
            actions,
            key=lambda item: (item.frame_index in hit_frames, item.confidence),
            reverse=True,
        )
        return sorted(ranked[: max(0, limit)], key=lambda item: item.frame_index)

    def _uniform_frame_times(self, frame_count: int, duration_seconds: float) -> list[float]:
        if frame_count <= 0:
            return []
        if duration_seconds <= 0:
            return [float(idx) for idx in range(frame_count)]
        if frame_count == 1:
            return [max(0.0, duration_seconds * 0.5)]
        return [
            min(duration_seconds, max(0.0, duration_seconds * (idx / max(1, frame_count - 1))))
            for idx in range(frame_count)
        ]

    def _analyze_full_sequence(
        self,
        frames: list[np.ndarray],
        mode: AnalyzeMode,
        fps: float,
        duration_seconds: float,
        attach_attribution: bool,
        analysis_phase: str,
        is_final: bool,
    ) -> AnalyzeResult:
        pose_seq = []
        weapon_seq = []
        all_hits = []
        all_combat_actions = []
        all_quartets = []
        all_violations = []
        all_evidence = []
        last_shooting = None
        fallback_used = False

        local_flow = ShootingFlowStateMachine()

        for idx, frame in enumerate(frames):
            pose = self.pose_engine.infer(frame, frame_index=idx)
            weapon = self.weapon_engine.infer(frame)
            posture_eval = self.shooting_rules.evaluate_posture(pose, weapon, frame_index=idx)
            event = self.shooting_rules.infer_flow_event(pose, weapon, posture_eval)
            stage = local_flow.ingest(event)

            temporal_one = self.temporal.analyze_frame(pose, weapon)
            combat_actions = self.combat.build_actions(temporal_one.dominant_action, temporal_one.confidence, idx)
            hits = self.combat.estimate_hits(pose, idx)
            evidence_item = ShootingEvidence(
                frame_index=idx,
                label=str(event.value if event else stage.value),
                confidence=temporal_one.confidence,
            )

            pose_seq.append(pose)
            weapon_seq.append(weapon)
            all_combat_actions.extend(combat_actions)
            all_hits.extend(hits)
            all_violations.extend(posture_eval.violations)
            all_evidence.append(evidence_item)
            fallback_used = fallback_used or pose.fallback_used or weapon.fallback_used

            last_shooting = ShootingResult(
                posture_compliance=posture_eval.compliance,
                posture_score=posture_eval.score,
                flow_stage=stage,
                flow_order_ok=local_flow.order_ok,
                violations=list(all_violations),
                evidence=list(all_evidence),
            )

        seq_temporal = self.temporal.analyze_sequence(pose_seq, weapon_seq)
        fatigue = self.fatigue.update(pose_seq)
        quartets = self.combat.build_quartets(all_combat_actions, all_hits, fatigue, fps or 12.0)
        review_cards = self.combat.build_review_cards(
            frames=frames,
            poses=pose_seq,
            actions=all_combat_actions,
            hits=all_hits,
            fatigue=fatigue,
            fps=fps or 12.0,
        )
        all_quartets.extend(quartets)

        combat_result = CombatResult(
            actions=all_combat_actions,
            quartets=all_quartets,
            fatigue=FatigueResult(**fatigue),
            hit_events=all_hits,
            stability=float(np.mean([self.combat.estimate_stability(p) for p in pose_seq])) if pose_seq else 0.0,
            review_cards=review_cards,
            supported_actions=self.combat.supported_actions(),
        )

        if last_shooting is None:
            last_shooting = self._build_placeholder_shooting()

        ui_stage_label, step_reports, primary_issues = build_step_reports(
            flow_stage=last_shooting.flow_stage.value,
            flow_order_ok=last_shooting.flow_order_ok,
            violations=last_shooting.violations,
            evidence=last_shooting.evidence,
            fps=fps or 0.0,
        )
        last_shooting.ui_stage_label = ui_stage_label
        last_shooting.step_reports = step_reports
        last_shooting.primary_issues = primary_issues

        payload = AnalyzeResult(
            shooting=last_shooting,
            combat=combat_result,
            meta=MetaResult(
                fps=fps,
                persons=len(pose_seq[-1].persons) if pose_seq else 0,
                device=settings.device,
                fallback_used=fallback_used,
                analysis_phase=analysis_phase,
                is_final=is_final,
            ),
            reasoning=None,
            attribution=None,
        )
        if attach_attribution:
            payload.attribution = self.deep_analyst.analyze(
                pose_sequence=pose_seq,
                weapon_sequence=weapon_seq,
                shooting_issues=primary_issues,
                fps=fps or 1.0,
                duration_seconds=duration_seconds or float(len(frames)),
            )

        low_conf = (seq_temporal.confidence < 0.58) or (not last_shooting.flow_order_ok)
        payload.reasoning = self.reasoning.enrich(payload.model_dump(), low_conf)
        return payload

    def _analyze_frame_internal(self, frame: np.ndarray, mode: AnalyzeMode, frame_index: int, fps: float) -> AnalyzeResult:
        if self._is_combat_mode(mode):
            pose = self.pose_engine.infer(frame, frame_index=frame_index)
            weapon = FrameWeaponResult(fallback_used=True)
            temporal = self.temporal.analyze_frame(pose, weapon)
            actions = self.combat.build_actions(temporal.dominant_action, temporal.confidence, frame_index)
            hits = self.combat.estimate_hits(pose, frame_index)

            self.stream_pose_window.append(pose)
            fatigue_raw = self.fatigue.update(list(self.stream_pose_window))
            quartets = self.combat.build_quartets(actions, hits, fatigue_raw, fps or 12.0)
            stability = self.combat.estimate_stability(pose)
            review_cards = self.combat.build_review_cards(
                frames=[frame],
                poses=[pose],
                actions=actions,
                hits=hits,
                fatigue=fatigue_raw,
                fps=fps or 12.0,
            )[:4]
            combat = CombatResult(
                actions=actions,
                quartets=quartets,
                fatigue=FatigueResult(**fatigue_raw),
                hit_events=hits,
                stability=stability,
                review_cards=review_cards,
                supported_actions=self.combat.supported_actions(),
            )
            meta = MetaResult(
                fps=fps,
                persons=len(pose.persons),
                device=settings.device,
                fallback_used=pose.fallback_used,
                analysis_phase="single",
                is_final=True,
            )
            return AnalyzeResult(
                shooting=self._build_placeholder_shooting(),
                combat=combat,
                meta=meta,
                reasoning=None,
                attribution=None,
            )

        pose = self.pose_engine.infer(frame, frame_index=frame_index)
        weapon = self.weapon_engine.infer(frame)

        posture = self.shooting_rules.evaluate_posture(pose, weapon, frame_index=frame_index)
        event = self.shooting_rules.infer_flow_event(pose, weapon, posture)
        stage = self.flow_state.ingest(event)

        temporal = self.temporal.analyze_frame(pose, weapon)
        actions = self.combat.build_actions(temporal.dominant_action, temporal.confidence, frame_index)
        hits = self.combat.estimate_hits(pose, frame_index)

        self.stream_pose_window.append(pose)
        fatigue_raw = self.fatigue.update(list(self.stream_pose_window))

        quartets = self.combat.build_quartets(actions, hits, fatigue_raw, fps or 12.0)
        stability = self.combat.estimate_stability(pose)
        review_cards = self.combat.build_review_cards(
            frames=[frame],
            poses=[pose],
            actions=actions,
            hits=hits,
            fatigue=fatigue_raw,
            fps=fps or 12.0,
        )
        evidence = [ShootingEvidence(frame_index=frame_index, label=str(event.value if event else stage.value), confidence=temporal.confidence)]
        ui_stage_label, step_reports, primary_issues = build_step_reports(
            flow_stage=stage.value,
            flow_order_ok=self.flow_state.order_ok,
            violations=posture.violations,
            evidence=evidence,
            fps=fps or 0.0,
        )

        shooting = ShootingResult(
            posture_compliance=posture.compliance,
            posture_score=posture.score,
            flow_stage=stage,
            flow_order_ok=self.flow_state.order_ok,
            violations=posture.violations,
            evidence=evidence,
            ui_stage_label=ui_stage_label,
            step_reports=step_reports,
            primary_issues=primary_issues,
        )
        combat = CombatResult(
            actions=actions,
            quartets=quartets,
            fatigue=FatigueResult(**fatigue_raw),
            hit_events=hits,
            stability=stability,
            review_cards=review_cards,
            supported_actions=self.combat.supported_actions(),
        )
        meta = MetaResult(
            fps=fps,
            persons=len(pose.persons),
            device=settings.device,
            fallback_used=pose.fallback_used or weapon.fallback_used,
            analysis_phase="single",
            is_final=True,
        )
        output = AnalyzeResult(shooting=shooting, combat=combat, meta=meta, reasoning=None, attribution=None)

        low_conf = temporal.confidence < 0.58
        output.reasoning = self.reasoning.enrich(output.model_dump(), low_conf)
        return output

    def _build_placeholder_shooting(self) -> ShootingResult:
        return ShootingResult(
            posture_compliance=False,
            posture_score=0.0,
            flow_stage=ShootingFlowStage.check_weapon,
            flow_order_ok=True,
            violations=[],
            evidence=[],
            ui_stage_label="格斗模式未启用射击流程",
            step_reports=[],
            primary_issues=[],
        )

    def _is_combat_mode(self, mode: AnalyzeMode) -> bool:
        return mode in {AnalyzeMode.combat_action, AnalyzeMode.combat_full}


pipeline = VisionPipeline()
