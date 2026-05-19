import base64
import logging
import math
from typing import Iterable

import cv2
import numpy as np
from openai import OpenAI
from config import KEYS, MODELS, NVIDIA_BASE_URL

logger = logging.getLogger(__name__)

class CAPTPEngine:
    """智警 AI 实战引擎 - 升级为多密钥专项控制系统"""
    DEFAULT_VISION_MODE = "SHOOTING_POSTURE"
    MAX_TACTICAL_HISTORY = 8
    VISION_TIMEOUT_SECONDS = 25.0
    TEXT_TIMEOUT_SECONDS = 18.0

    def __init__(self):
        # 初始化针对不同负载的专项客户端
        self.client_vision = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=KEYS["VISION_PRIMARY"],
            timeout=self.VISION_TIMEOUT_SECONDS,
            max_retries=0,
        )
        self.client_parser = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=KEYS["PARSER_NODE"],
            timeout=20.0,
            max_retries=0,
        )
        self.client_reward = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=KEYS["REWARD_SCORING"],
            timeout=self.VISION_TIMEOUT_SECONDS,
            max_retries=0,
        )
        self.vision_models = [MODELS["VISION"], MODELS.get("VISION_FALLBACK")]
        self.tactical_models = [MODELS["TACTICAL"], MODELS.get("TACTICAL_FALLBACK")]
        self.tactical_follow_ups = {
            "人质劫持危机处理": [
                "嫌疑人要求 5 分钟内看到车辆并威胁伤害人质，你准备如何回应，既不刺激对方又不作超范围承诺？",
                "一名家属情绪失控要冲上楼，你如何隔离家属并安排谁负责沟通安抚？",
                "人质短暂喊出“我头晕”，你下一步优先核实哪两项生命安全信息？",
                "如果嫌疑人要求指定一名民警单独靠近送水，你如何评估风险并处置？",
            ],
            "群体性突发事件疏导": [
                "仍有 6 人坐在主车道中央拒不移动，救护车已被堵在 50 米外，你准备如何分层处置并保持全程录像取证？",
                "一名自称工头的人持续煽动围堵民警，你如何区分诉求人、带头煽动者和普通围观者？",
                "现场直播评论开始误传“警方驱赶讨薪群众”，你准备怎样现场回应并安排谁对接项目方或劳动监察？",
                "如果有人突然带头冲击工地闸门，你先保护什么、先控制谁、先喊什么？",
            ],
            "入室搜巡战术接战": [
                "屋内女性突然喊“刀在厨房”，你是否立即进屋？进屋前你先确认哪两项风险信息？",
                "一名邻居不断靠近门口拍摄，影响你观察门内情况，你如何保持楼道净空并固定现场证据？",
                "如果屋内男性拒不露手、反复退向厨房方向，你如何调整门口站位和协同分工？",
                "若发现屋内还有未成年人，你准备先完成哪一步保护动作？",
            ],
            "常规道路拦截盘查": [
                "副驾迟迟不举手且反复低头伸手到座椅侧面，你是继续口头控制还是立即升级控制？依据是什么？",
                "后排乘客称自己只是顺路搭车并试图下车解释，你如何在确保安全前提下分离检查？",
                "驾驶员拒绝熄火并试图挂挡，你下一步的口令、站位和协同动作分别是什么？",
                "若车内闻到明显酒精味且驾驶员情绪激动，你先查人、查车还是先稳控？为什么？",
            ],
        }
        
        self.prompts = {
            "SHOOTING_POSTURE": (
                "你是一名资深警务射击教官。请根据上传画面判断持枪姿态是否规范，"
                "重点检查站姿、重心、双手握持、手臂状态和枪口控制。"
                "请按“综合判断 / 主要问题 / 纠偏建议”输出，语言简洁明确。"
            ),
            "SHOOTING_TARGET": (
                "你是一套警务阅靶评估系统。请先判断靶纸是否清晰可读；如果能识别，"
                "必须明确写出弹孔数量、各圈层分布、偏移趋势和整体成绩水平。"
                "如果图像角度或清晰度不足，请明确指出原因并给出重拍建议。"
                "禁止输出代码，只输出评估结论。"
            ),
            "SHOOTING_WEAPON": (
                "你是一套警务武器安全检查系统。请识别画面中武器的大致类型，"
                "重点检查食指位置、枪口指向、保险状态和持枪安全风险。"
                "请按“识别结果 / 风险点 / 规范建议”输出。"
            ),
            "COMBAT_FIGHT": (
                "你正在分析警务格斗训练画面。输入可能是一张静态图，也可能是同一段视频抽取的多帧拼图，"
                "顺序默认为从左上到右下。忽略水印、边框、字幕和任何帧编号，不要照抄画面文字。"
                "必须只用中文输出，并按“双方动作 / 可能伤害 / 控制态势 / 风险提醒”四段给出结论。"
            ),
            "COMBAT_SCORING": (
                "你是一名警务格斗动作质量裁判。输入可能是一张静态图，也可能是同一段视频抽取的多帧拼图，"
                "顺序默认为从左上到右下。忽略水印、边框、字幕和任何帧编号，不要复述 F1、F2、时间码等画面文字。"
                "请只用中文，并严格按以下格式输出："
                "双方动作：A方做了什么，B方做了什么。"
                "可能伤害：分别说明双方可能受到的击打、扭伤、摔击或关节伤害；无法确认时写“无法从画面确认”。"
                "控制态势：谁占主动、谁处于被动。"
                "技术评分：10 分制，并说明评分理由。"
                "改进建议：给出训练纠偏建议。"
            ),
            "TACTICAL_AGENT": (
                "你是警务实战推演教官，也是虚拟数字人点评引擎。"
                "当前场景：{scenario}。"
                "场景背景：{scenario_context}。"
                "你必须严格锁定当前案情，不得改写成其他类型警情，不得混淆处警性质。"
                "你的任务不是泛泛聊天，而是针对使用者刚刚那一轮回答做精细点评：先判断是否贴合当前警情，再拆出正确点、遗漏点、风险点和下一步处置。"
                "如果用户回答过于笼统、跳步骤、缺少口令、站位、分工、法律程序或安全控制中的关键项，要直接指出，不要模糊带过。"
                "每轮都必须只用中文，并严格按以下格式输出："
                "回答判断：先用一句话判断该回答是‘基本正确 / 部分正确 / 偏离场景 / 风险较高’，并说明最核心原因。"
                "做对了什么：结合用户原话，提炼 2-4 个有效处置点；如果不足 2 个，就如实写明‘有效点较少’。"
                "还缺什么：明确列出 2-4 个缺失环节，优先检查警戒隔离、口头控制、站位分工、升级处置、证据固定、群众管理、医疗救助、法律程序。"
                "风险提醒：指出如果按当前回答直接执行，最可能出现的 1-3 个现场风险或执法风险。"
                "下一问题：必须提出 1 个非常具体、可执行、贴着当前案情往下走的问题，优先追问‘你下一句口令说什么、谁负责什么、你站在哪里、先控制谁、先固定什么证据、何时升级警力或措施’。"
                "输出要像教官逐条讲评，避免空话，避免只说‘不错’‘还行’‘继续完善’这类模糊评价。"
            ),
        }

    @property
    def supported_vision_modes(self) -> list[str]:
        return [mode for mode in self.prompts if mode != "TACTICAL_AGENT"]

    def is_supported_vision_mode(self, mode: str) -> bool:
        return mode in self.supported_vision_modes

    def _build_image_messages(self, prompt: str, image_data: bytes) -> list[dict]:
        base64_image = base64.b64encode(image_data).decode('utf-8')
        return [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
            ],
        }]

    def _first_available_result(self, attempts):
        last_error = None

        for model_name, runner in attempts:
            if not model_name:
                continue

            try:
                result = runner(model_name)
                if result:
                    return result
            except Exception as exc:
                last_error = exc
                logger.warning("Model call failed for %s: %s", model_name, exc)

        if last_error:
            raise last_error

        raise RuntimeError("没有可用的模型可供调用。")

    def _run_vision_completion(
        self,
        prompt: str,
        image_data: bytes,
        *,
        max_tokens: int = 640,
        temperature: float = 0.2,
    ):
        messages = self._build_image_messages(prompt, image_data)
        return self._first_available_result(
            [
                (
                    model_name,
                    lambda current_model, msgs=messages: (
                        self.client_vision.chat.completions.create(
                            model=current_model,
                            messages=msgs,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        ).choices[0].message.content
                        or "未获得模型返回结果。"
                    ),
                )
                for model_name in self.vision_models
            ]
        )

    def _run_text_completion(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
    ):
        return self._first_available_result(
            [
                (
                    model_name,
                    lambda current_model, msgs=messages: (
                        self.client_vision.chat.completions.create(
                            model=current_model,
                            messages=msgs,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            timeout=self.TEXT_TIMEOUT_SECONDS,
                            stream=False,
                        ).choices[0].message.content
                        or "现场暂无新的态势变化。"
                    ),
                )
                for model_name in self.tactical_models
            ]
        )

    def _compact_tactical_messages(
        self,
        messages: Iterable[dict],
        scenario: str | None,
        scenario_context: str | None,
    ) -> list[dict]:
        scenario_name = (scenario or "").strip() or "常规道路拦截盘查"
        scenario_details = (scenario_context or "").strip() or "请结合真实警务问题进行模拟，持续追问具体处置。"
        compact_messages = []

        for message in messages:
            role = str(message.get("role", "")).strip()
            content = message.get("content", "")
            if role not in {"user", "assistant"}:
                continue

            normalized_content = str(content).strip()
            if not normalized_content:
                continue

            compact_messages.append({"role": role, "content": normalized_content})

        compact_messages = compact_messages[-self.MAX_TACTICAL_HISTORY :]
        system_prompt = self.prompts["TACTICAL_AGENT"].format(
            scenario=scenario_name,
            scenario_context=scenario_details,
        )
        anchor_messages = [
            {
                "role": "user",
                "content": f"固定案情如下，请你后续只能围绕这起警情推演，不得改写：{scenario_details}",
            },
            {
                "role": "assistant",
                "content": f"已锁定案情【{scenario_name}】。后续我只围绕这起警情进行现场反馈、点评和下一问题追问。",
            },
        ]
        return [{"role": "system", "content": system_prompt}, *anchor_messages, *compact_messages]

    def _select_tactical_question(self, scenario: str | None, messages: list[dict]) -> str | None:
        scenario_name = (scenario or "").strip()
        follow_ups = self.tactical_follow_ups.get(scenario_name)
        if not follow_ups:
            return None

        user_turn_count = sum(1 for message in messages if message.get("role") == "user")
        if user_turn_count <= 0:
            return follow_ups[0]

        index = min(user_turn_count - 1, len(follow_ups) - 1)
        return follow_ups[index]

    def _inject_tactical_question(self, response_text: str, forced_question: str | None) -> str:
        if not forced_question:
            return response_text

        cleaned_text = (response_text or "").strip()
        if "下一问题：" in cleaned_text:
            prefix = cleaned_text.split("下一问题：", 1)[0].rstrip()
            return f"{prefix}\n\n下一问题：{forced_question}"

        return f"{cleaned_text}\n\n下一问题：{forced_question}".strip()

    def analyze_vision(self, image_data: bytes, mode: str):
        """核心视觉分析 - 使用视觉专属 API 密钥"""
        resolved_mode = mode if self.is_supported_vision_mode(mode) else self.DEFAULT_VISION_MODE
        prompt = self.prompts.get(resolved_mode, "分析画面内容")
        
        try:
            token_budget = 768 if resolved_mode == "SHOOTING_TARGET" else 512
            result = self._run_vision_completion(
                prompt,
                image_data,
                max_tokens=token_budget,
                temperature=0.15,
            )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": f"视觉处理节点 [VISION] 异常: {str(e)}"}

    def _decode_image(self, image_data: bytes):
        image_array = np.frombuffer(image_data, dtype=np.uint8)
        return cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    def _clock_direction(self, angle_degrees: float) -> str:
        clock = int(((90 - angle_degrees) % 360) / 30) + 1
        if clock == 13:
            clock = 1
        return f"{clock}点方向"

    def analyze_shooting_target(self, image_data: bytes):
        """靶纸评估优先使用 OpenCV 计分，失败后回退到视觉模型。"""
        image = self._decode_image(image_data)
        if image is None:
            return self.analyze_vision(image_data, "SHOOTING_TARGET")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, dark_mask = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return self.analyze_vision(image_data, "SHOOTING_TARGET")

        target_contour = max(contours, key=cv2.contourArea)
        target_area = cv2.contourArea(target_contour)
        if target_area < 30000:
            return self.analyze_vision(image_data, "SHOOTING_TARGET")

        (center_x, center_y), outer_radius = cv2.minEnclosingCircle(target_contour)
        target_mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.drawContours(target_mask, [target_contour], -1, 255, thickness=-1)

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        candidate_mask = (
            (hsv[:, :, 1] <= 70)
            & (hsv[:, :, 2] >= 175)
            & (target_mask > 0)
        ).astype(np.uint8) * 255

        num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(candidate_mask)
        center = np.array([center_x, center_y], dtype=float)
        hit_candidates = []

        for index in range(1, num_labels):
            area = int(stats[index, cv2.CC_STAT_AREA])
            x, y, width, height, _ = stats[index]
            if area < 150 or area > 1400:
                continue

            aspect_ratio = max(width / max(height, 1), height / max(width, 1))
            if aspect_ratio > 1.6:
                continue

            centroid = centroids[index]
            distance = float(np.linalg.norm(centroid - center))
            if distance > outer_radius * 1.02:
                continue

            # 过滤靶纸底部中心的印刷数字，保留两侧真实命中点
            if centroid[1] > center_y + outer_radius * 0.55 and abs(centroid[0] - center_x) < outer_radius * 0.35:
                continue

            patch = gray[
                max(0, int(centroid[1]) - 6): int(centroid[1]) + 7,
                max(0, int(centroid[0]) - 6): int(centroid[0]) + 7,
            ]
            bright_ratio = float((patch > 180).mean()) if patch.size else 0.0
            if bright_ratio < 0.25:
                continue

            duplicate = False
            for existing in hit_candidates:
                if np.linalg.norm(existing["centroid"] - centroid) < 18:
                    if area > existing["area"]:
                        existing.update({"centroid": centroid, "area": area, "distance": distance})
                    duplicate = True
                    break

            if not duplicate:
                hit_candidates.append({
                    "centroid": centroid,
                    "area": area,
                    "distance": distance,
                })

        if not hit_candidates:
            return self.analyze_vision(image_data, "SHOOTING_TARGET")

        inner_ring_radius = outer_radius * 0.25
        ring_step = max((outer_radius - inner_ring_radius) / 4.0, 1.0)
        ring_counts = {ring: 0 for ring in range(1, 6)}
        hit_details = []

        for hit in sorted(hit_candidates, key=lambda item: item["distance"]):
            distance = hit["distance"]
            if distance <= inner_ring_radius:
                ring = 1
            else:
                ring = min(5, 2 + int((distance - inner_ring_radius) / ring_step))

            ring_counts[ring] += 1

            angle = (math.degrees(math.atan2(center_y - hit["centroid"][1], hit["centroid"][0] - center_x)) + 360) % 360
            hit_details.append({
                "ring": ring,
                "direction": self._clock_direction(angle),
                "distance_ratio": distance / outer_radius,
            })

        mean_offset = np.mean([hit["centroid"] - center for hit in hit_candidates], axis=0)
        horizontal_bias = "偏右" if mean_offset[0] > outer_radius * 0.08 else "偏左" if mean_offset[0] < -outer_radius * 0.08 else "左右基本居中"
        vertical_bias = "偏下" if mean_offset[1] > outer_radius * 0.08 else "偏上" if mean_offset[1] < -outer_radius * 0.08 else "高低基本居中"

        mean_distance_ratio = float(np.mean([hit["distance"] / outer_radius for hit in hit_candidates]))
        distance_std_ratio = float(np.std([hit["distance"] / outer_radius for hit in hit_candidates]))

        if mean_distance_ratio <= 0.32 and distance_std_ratio <= 0.12:
            level = "优秀"
        elif mean_distance_ratio <= 0.46 and distance_std_ratio <= 0.16:
            level = "良好"
        elif mean_distance_ratio <= 0.62:
            level = "中等"
        else:
            level = "待提升"

        spread = "集中度较好" if distance_std_ratio <= 0.12 else "集中度一般" if distance_std_ratio <= 0.18 else "散布偏大"

        ring_summary = "，".join(
            f"{ring}环 {count} 发"
            for ring, count in ring_counts.items()
            if count > 0
        )
        detail_summary = "；".join(
            f"第{index + 1}发约 {item['ring']} 环（{item['direction']}）"
            for index, item in enumerate(hit_details[:8])
        )
        if len(hit_details) > 8:
            detail_summary += f"；其余 {len(hit_details) - 8} 发分布在相近圈层"

        report = (
            "靶纸评估结果\n"
            f"- 有效弹孔：约 {len(hit_candidates)} 发\n"
            f"- 圈层分布：{ring_summary}\n"
            f"- 单发判断：{detail_summary}\n"
            f"- 偏移趋势：整体{horizontal_bias}、{vertical_bias}\n"
            f"- 散布情况：{spread}\n"
            f"- 水平判断：整体为{level}水平，平均落点约在 3 环附近。"
        )
        return {"success": True, "data": report}

    def tactical_chat(self, messages: list, scenario: str | None = None, scenario_context: str | None = None):
        """决策推演聊天 - 升级为 1 秒内极致响应模式"""
        try:
            compact_messages = self._compact_tactical_messages(messages, scenario, scenario_context)
            result = self._run_text_completion(
                compact_messages,
                max_tokens=420,
                temperature=0.25,
            )
            forced_question = self._select_tactical_question(scenario, messages)
            return {"success": True, "data": self._inject_tactical_question(result, forced_question)}
        except Exception as e:
            return {"success": False, "error": f"推演引擎瞬发模式异常: {str(e)}"}

    def combat_quality_scoring(self, image_data: bytes):
        """专业格斗高质量评分 - 走专用评分提示词链路"""
        try:
            result = self._run_vision_completion(
                self.prompts["COMBAT_SCORING"],
                image_data,
                max_tokens=640,
                temperature=0.05,
            )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": f"奖励评分节点 [REWARD] 异常: {str(e)}"}
            
    def legal_document_parsing(self, text_content: str):
        """法律/警务文档结构化解析 - 使用专用的 PARSER 密钥与模型"""
        try:
            response = self.client_parser.chat.completions.create(
                model=MODELS["PARSER"],
                messages=[{"role": "user", "content": f"请深度解析这份警务战术文书，进行结构化抽取：{text_content}"}]
            )
            return {"success": True, "data": response.choices[0].message.content}
        except Exception as e:
            return {"success": False, "error": f"解析处理节点 [PARSER] 异常: {str(e)}"}

engine = CAPTPEngine()
