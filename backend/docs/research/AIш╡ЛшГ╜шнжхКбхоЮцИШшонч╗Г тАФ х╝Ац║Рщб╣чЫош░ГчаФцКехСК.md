**AI赋能警务实战训练 — 开源项目调研报告**

📅 调研日期：2026年4月4日 | 调研人：广西警察学院人工智能教研室

本报告汇总了可用于警务实战训练AI赋能的开源项目，涵盖射击训练、擒拿格斗、执法决策推演三大场景，所有项目均为真实GitHub仓库，优先筛选CPU可运行、中文文档完善的项目。

**一、射击训练方向**

**1.1 弹孔 / 靶纸自动检测**

thiagodsd/bullet-from-a-gun | https://github.com/thiagodsd/bullet-from-a-gun

功能：CNN检测多种材质靶纸上的弹孔位置，支持基准测试对比 | CPU可运行：✅

echo-akash/Bullet-Impression-Detection | https://github.com/echo-akash/Bullet-Impression-Detection

功能：靶纸孔洞检测 + 武器校准分析，可输出命中坐标 | CPU可运行：✅

sigmondkukla/Target-Analysis | https://github.com/sigmondkukla/Target-Analysis

功能：射击精度综合分析系统，输出命中分布热力图 | CPU可运行：✅

**1.2 武器 / 枪支检测（持枪动作识别）**

JoaoAssalim/Weapons-and-Knives-Detector-with-YOLOv8 | https://github.com/JoaoAssalim/Weapons-and-Knives-Detector-with-YOLOv8

功能：YOLOv8实时检测武器和刀具，适用于训练场景监控 | CPU可运行：✅

BecayeSoft/Guns-Detection-YOLOv8 | https://github.com/BecayeSoft/Guns-Detection-YOLOv8

功能：YOLOv8枪支检测，支持摄像头实时流 | CPU可运行：✅

amin-tohidi/Detection-of-pistol-by-deep-learning-With-YOLO_v5 | https://github.com/amin-tohidi/Detection-of-pistol-by-deep-learning-With-YOLO_v5

功能：YOLOv5手枪检测，专为CCTV场景优化 | CPU可运行：✅

Vayuputra2401/Real-Time-Weapon-Detection | https://github.com/Vayuputra2401/Real-Time-Weapon-Detection

功能：YOLO实时武器威胁检测系统 | CPU可运行：✅

manhminno/Gun-Detection-In-Photos-Videos | https://github.com/manhminno/Gun-Detection-In-Photos-Videos

功能：YOLOv3图片/视频枪支检测 | CPU可运行：✅

**二、擒拿格斗 / 动作识别**

**2.1 打架 / 暴力行为检测**

imsoo/fight_detection ⭐209 | https://github.com/imsoo/fight_detection

功能：基于2D姿态估计+RNN的实时打架检测，使用OpenPose+SORT追踪 | CPU可运行：✅

jpowellgz/FightDetectionPoseLSTM | https://github.com/jpowellgz/FightDetectionPoseLSTM

功能：OpenPose + Bi-LSTM打架检测，论文复现代码 | CPU可运行：✅

rdutta1999/Fight-NonFight-Classification-OpenPose | https://github.com/rdutta1999/Fight-NonFight-Classification-OpenPose

功能：OpenPose打架vs非打架二分类 | CPU可运行：✅

Musawer1214/Fight-Violence-detection-yolov8 | https://github.com/Musawer1214/Fight-Violence-detection-yolov8

功能：YOLOv8视频打架/暴力检测 | CPU可运行：✅

**2.2 姿态估计基础框架（核心底座）**

CMU-Perceptual-Computing-Lab/openpose ⭐30,600+ | https://github.com/CMU-Perceptual-Computing-Lab/openpose

功能：业界最知名的实时多人全身关键点检测，有中文文档 | CPU可运行：✅ | 推荐指数：⭐⭐⭐⭐⭐

MVIG-SJTU/AlphaPose ⭐8,000+ | https://github.com/MVIG-SJTU/AlphaPose

功能：上海交大出品，多人精准姿态估计，中文文档完善 | CPU可运行：✅ | 推荐指数：⭐⭐⭐⭐⭐

open-mmlab/mmpose ⭐3,800+ | https://github.com/open-mmlab/mmpose

功能：OpenMMLab系列，2D/3D姿态估计工具箱，中文文档 | CPU可运行：✅ | 推荐指数：⭐⭐⭐⭐

PaddlePaddle/PaddleDetection ⭐12,000+ | https://github.com/PaddlePaddle/PaddleDetection

功能：百度出品，中文文档最完善，含运动关键点检测，最适合国内团队 | CPU可运行：✅ | 推荐指数：⭐⭐⭐⭐⭐

**2.3 动作识别（动作序列分析）**

open-mmlab/mmaction2 ⭐3,000+ | https://github.com/open-mmlab/mmaction2

功能：视频动作理解工具箱，支持格斗动作分类，中文文档 | CPU可运行：✅

TheAntimist/martial-arts | https://github.com/TheAntimist/martial-arts

功能：基于奥运会格斗动作数据集的分类系统 | CPU可运行：✅

dronefreak/human-action-classification ⭐245 | https://github.com/dronefreak/human-action-classification

功能：MediaPipe+3D CNN动作分类，支持100+架构 | CPU可运行：✅

**三、执法决策推演（LLM）**

**3.1 本地大模型部署（最快落地）**

ollama/ollama ⭐167,000+ | https://github.com/ollama/ollama

功能：本地LLM一键部署工具，支持Qwen/DeepSeek等中文模型，10分钟可跑通 | CPU可运行：✅ | 推荐指数：⭐⭐⭐⭐⭐

open-webui/open-webui ⭐130,000+ | https://github.com/open-webui/open-webui

功能：Ollama配套Web界面，ChatGPT风格，支持完全离线运行 | CPU可运行：✅ | 推荐指数：⭐⭐⭐⭐⭐

**3.2 情景模拟与决策训练**

microsoft/TinyTroupe | https://github.com/microsoft/TinyTroupe

功能：微软出品的LLM多角色情景推演框架，可构建执法多方博弈场景

EiroaCigarMan/nfca-open-source-llm | https://github.com/EiroaCigarMan/nfca-open-source-llm

功能：专为执法部门整理的开源LLM使用指南和最佳实践

**四、综合评估与推荐落地路线**

**4.1 立竿见影（本周可跑通）**

Ollama + Open WebUI → 执法情景决策推演，零硬件门槛，安装即用

Gun_Detection_YOLOv8 → 持枪姿势监测，pip安装后摄像头接入

**4.2 一个月内落地**

PaddleDetection（中文文档最好）→ 格斗姿势关键点提取与评分

靶纸分析三件套（bullet-from-a-gun等）→ 射击成绩自动化识别

fight_detection → 格斗训练实时行为检测

**4.3 需一定开发量（1-3个月）**

MMAction2 + 自建格斗动作标准库 → 完整擒拿格斗评分系统

OpenPose/AlphaPose + 持枪姿势标注数据集 → 射击姿势规范评估系统

TinyTroupe + 警务场景剧本库 → 沉浸式执法决策推演系统

**4.4 项目综合对比表**

项目名称 | GitHub地址 | Stars | 场景 | 中文文档 | CPU可运行 | 推荐优先级

Ollama | github.com/ollama/ollama | 167k+ | 决策推演 | ✅ | ✅ | P0

Open WebUI | github.com/open-webui/open-webui | 130k+ | 决策推演 | ✅ | ✅ | P0

OpenPose | github.com/CMU-Perceptual-Computing-Lab/openpose | 30.6k+ | 姿态分析 | ✅ | ✅ | P1

PaddleDetection | github.com/PaddlePaddle/PaddleDetection | 12k+ | 格斗/射击 | ✅ | ✅ | P1

AlphaPose | github.com/MVIG-SJTU/AlphaPose | 8k+ | 格斗评估 | ✅ | ✅ | P1

MMAction2 | github.com/open-mmlab/mmaction2 | 3k+ | 动作识别 | ✅ | ✅ | P2

MMPose | github.com/open-mmlab/mmpose | 3.8k+ | 姿态估计 | ✅ | ✅ | P2

fight_detection | github.com/imsoo/fight_detection | 209 | 格斗检测 | ❌ | ✅ | P2

bullet-from-a-gun | github.com/thiagodsd/bullet-from-a-gun | — | 弹孔检测 | ❌ | ✅ | P2

Target-Analysis | github.com/sigmondkukla/Target-Analysis | — | 射击分析 | ❌ | ✅ | P2

**五、备注**

1\. 所有项目均为真实GitHub开源仓库，经搜索验证存在。

2\. CPU可运行意味着无需独立显卡，普通教学用PC/笔记本即可部署。

3\. 警察院校部署建议优先选择百度系（PaddleDetection）和本地LLM（Ollama），避免数据外传。

4\. 如需进一步验证某个项目的可用性，可联系AI教研室进行本地测试部署。

**六、具体可用方案（第二轮检索 2026-04-04）**

本章节为第二轮深度检索结果，聚焦「有完整Demo/Streamlit界面/Docker部署」的项目，按部署难度分级排列。

**6.1 立竿见影 — 1天内跑通**

**动作姿态实时纠正**

AI-Personal-Trainer | https://github.com/thaochu05/AI-Personal-Trainer

Streamlit Web应用，MediaPipe实时姿态纠正，修改一个JSON文件即可添加警务专项动作（射击姿态/格斗动作/战术移动）。部署：pip install + streamlit run，约1小时跑通。

Exercise-Correction | https://github.com/NgoQuocBao1010/Exercise-Correction

MediaPipe实时检测，提供即时语音+画面反馈，代码结构清晰易改造，含完整文档。

fitness-trainer-pose-estimation | https://github.com/yakupzengin/fitness-trainer-pose-estimation

18个内置动作库，0-100评分 + A-F等级制，一键部署，可直接演示给领导看。

Good-GYM | https://github.com/yo-WASSUP/Good-GYM

RTMPose高精度姿态检测（比MediaPipe更准），多运动支持，含实时纠正提示。

**靶纸自动评分**

Target-Score-Detector | https://github.com/Niv-Kor/Target-Score-Detector

摄像头拍靶纸 → 自动识别弹孔 → 输出评分，计算机视觉自动评分系统，低成本。

ShotPlot | https://github.com/lwadya/shotplot

Web应用，上传靶纸图片即可获得命中统计分析，改造成本极低。

**6.2 3天内落地**

**格斗对抗实时评分**

boxing-ai-realtime-scoring | https://github.com/tekuper/boxing-ai-realtime-scoring

实时拳击评分 + 犯规检测，JSON格式输出，可视化界面，将10点制评分改为警察格斗评分标准即可直接使用。★ 最推荐格斗场景

ufc-automated-scoring-system | https://github.com/tylerlum/ufc_automated_scoring_system

深度学习双人格斗自动评分，支持双选手同时分析。

Fitness-AQA | https://github.com/ParitoshParmar/Fitness-AQA

ECCV 2022论文复现，动作质量1-5分自动评估，含预训练模型，部署后可直接推理。

ai-sports-assistant | https://github.com/RubenAMtz/ai-sports-assistant

视频动作识别 + 质量评估(1-5分) + 自动反馈生成，适合体能训练评估。

**6.3 1周内落地**

**战术决策推演（LLM驱动）**

WarAgent | https://github.com/agiresearch/WarAgent

LLM多智能体战术模拟框架，Apache 2.0开源，可定制警务危机场景（人质事件/群体性事件/追逃）。接入Ollama本地模型可完全离线运行。★ 最推荐决策场景

Panopticon | https://github.com/Panopticon-AI-team/panopticon

开源兵棋推演平台，网页界面，支持强化学习智能体，可用于警务战术推演训练。

AgentGym-RL | https://github.com/WooooDyy/AgentGym-RL

LLM多轮长期决策训练框架，强化学习支持，适合构建警察危机决策训练环境。

**6.4 推荐集成方案（3个月落地）**

**整体架构：Streamlit多页应用**

第1周：AI-Personal-Trainer 改造 → 加入射击/格斗/战术移动标准动作库 → 有可演示Web系统

第2周：boxing-ai + Target-Score-Detector → 格斗评分 + 靶纸自动识别 → 覆盖三大训练场景

第3周：Ollama + WarAgent → 接入本地LLM → 执法情景决策推演

第4周：集成统一平台 → 一个Streamlit多页应用 + 数据存储 + 成绩报表

**最终系统功能页面**

页面1：实时射击姿态纠正（AI-Personal-Trainer改造）

页面2：格斗动作技术评分（Boxing AI改造）

页面3：靶纸成绩自动识别（Target-Score-Detector）

页面4：执法情景决策推演（WarAgent + Ollama）

页面5：训练数据统计报表

**6.5 快速对比表**

项目 | GitHub地址 | 部署难度 | 部署时间 | 警务改造成本 | 推荐优先级

AI-Personal-Trainer | github.com/thaochu05/AI-Personal-Trainer | ⭐ 极低 | 1天 | 低（改JSON） | P0

boxing-ai-realtime-scoring | github.com/tekuper/boxing-ai-realtime-scoring | ⭐⭐ 低 | 3天 | 低（改评分标准） | P0

Target-Score-Detector | github.com/Niv-Kor/Target-Score-Detector | ⭐ 极低 | 3天 | 低 | P0

Exercise-Correction | github.com/NgoQuocBao1010/Exercise-Correction | ⭐ 极低 | 1天 | 低 | P1

Good-GYM | github.com/yo-WASSUP/Good-GYM | ⭐ 极低 | 1天 | 低 | P1

Fitness-AQA | github.com/ParitoshParmar/Fitness-AQA | ⭐⭐⭐ 中 | 1周 | 中 | P1

WarAgent | github.com/agiresearch/WarAgent | ⭐⭐⭐ 中 | 1周 | 中（加警务剧本） | P1

Panopticon | github.com/Panopticon-AI-team/panopticon | ⭐⭐⭐ 中 | 1周 | 中 | P2

AgentGym-RL | github.com/WooooDyy/AgentGym-RL | ⭐⭐⭐⭐ 高 | 2周 | 高 | P2

ShotPlot | github.com/lwadya/shotplot | ⭐ 极低 | 1天 | 低 | P1