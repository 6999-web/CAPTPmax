# 系统概览文档

---

## 目录

1. [项目简介](#项目简介)
2. [技术栈概览](#技术栈概览)
   - [后端技术栈](#后端技术栈)
   - [前端技术栈](#前端技术栈)
   - [运维与部署技术栈](#运维与部署技术栈)
   - [测试与质量保证](#测试与质量保证)
   - [安全与合规](#安全与合规)
3. [核心功能列表](#核心功能列表)
4. [功能实现细节](#功能实现细节)
   - [用户登录与鉴权](#用户登录与鉴权)
   - [AI 评估引擎](#ai-评估引擎)
   - [多模态图像分析](#多模态图像分析)
   - [战术决策模拟](#战术决策模拟)
   - [报告生成与导出](#报告生成与导出)
   - [实时数据可视化](#实时数据可视化)
5. [系统当前已实现功能](#系统当前已实现功能)
6. [架构图示](#架构图示)
7. [开发与部署流程](#开发与部署流程)
8. [未来规划与扩展方向](#未来规划与扩展方向)
9. [参考文献与资源链接](#参考文献与资源链接)

---

## 项目简介

本系统是一套面向执法训练的 **AI 驱动评估平台**，旨在通过 **多模态 AI**（图像、文本、结构化数据）对训练过程进行实时评估、评分与反馈。系统整体采用 **微服务架构**，后端使用 **FastAPI** + **Python**，前端使用 **Vue 3** + **Vite**，并通过 **NVIDIA NIM** 系列模型提供高性能的视觉与语言推理能力。项目严格遵循公司内部 **Bazel** 构建、**Git Flow** 工作流、**PEP8**/**ESLint** 代码规范以及 **pytest** 单元测试体系，确保代码质量与可维护性。

---

## 技术栈概览

### 后端技术栈

| 层级 | 技术 | 版本/约束 | 说明 |
|------|------|-----------|------|
| 框架 | **FastAPI** | >=0.104 | 高性能异步 API 框架，自动生成 OpenAPI 文档 |
| 语言 | **Python 3.11** | - | 主语言，遵循 PEP8 标准 |
| 依赖管理 | **Bazel** | 6.x | 统一构建系统，支持跨语言依赖解析 |
| 包管理 | **requirements.txt** | - | 所有第三方库统一声明，禁止手动 pip install |
| 数据库 | **PostgreSQL** | 15.x | 关系型存储，使用 **SQLAlchemy 2.0** ORM |
| 缓存 | **Redis** | 7.x | 用于会话、限流、结果缓存 |
| 异步任务队列 | **Celery** + **RabbitMQ** | Celery 5.x | 后台任务（模型推理、报告生成） |
| AI 推理服务 | **NVIDIA NIM** (v2+) | - | 调用 `nvidia-nim` 镜像提供的多模态模型 |
| 配置管理 | **pydantic-settings** | 2.x | 类型安全的配置加载 |
| 日志 | **loguru** | 0.7.x | 结构化日志，支持 JSON 输出 |
| 安全 | **OAuth2** + **JWT** (RS256) | - | 标准授权流程，令牌加密签名 |
| 测试框架 | **pytest** | 8.x | 单元、集成、性能测试 |
| 静态分析 | **flake8**, **mypy** | - | 代码质量检查 |

### 前端技术栈

| 层级 | 技术 | 版本/约束 | 说明 |
|------|------|-----------|------|
| 框架 | **Vue 3** | 3.4.x | 组合式 API，响应式数据流 |
| 构建工具 | **Vite** | 5.x | 超快热更新，原生 ES 模块 |
| 包管理 | **npm** | 10.x | 锁文件 `package-lock.json` |
| 状态管理 | **Pinia** | 2.x | 轻量级全局状态 |
| 路由 | **Vue Router 4** | - | 基于历史模式的 SPA 路由 |
| UI 组件库 | **Naive UI** | 2.x | 高度可定制的 UI 组件 |
| 样式 | **Vanilla CSS** + **CSS Variables** | - | 避免 Tailwind，使用自定义设计系统 |
| 动画 | **GSAP** | 3.x | 微交互与页面过渡 |
| 图表 | **ECharts** | 5.x | 实时数据可视化 |
| 国际化 | **vue-i18n** | 9.x | 多语言支持 |
| 代码质量 | **ESLint** (recommended) | - | 强制代码风格 |
| 单元测试 | **Vitest** | 1.x | 前端单元与快照测试 |

### 运维与部署技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 容器化 | **Docker** | 每个微服务独立容器，Dockerfile 通过 Bazel 生成 |
| 编排 | **Kubernetes** (v1.28) | 部署到内部集群，使用 Helm Chart 管理 |
| CI/CD | **GitHub Actions** + **Bazel CI** | 自动化构建、单元测试、镜像推送 |
| 监控 | **Prometheus** + **Grafana** | 业务指标、模型推理时延监控 |
| 日志聚合 | **ELK Stack** (ElasticSearch, Logstash, Kibana) | 集中化日志检索 |
| 秘钥管理 | **HashiCorp Vault** | API 密钥、数据库密码加密存储 |
| 安全扫描 | **Trivy**, **Dependabot** | 自动检测 CVE 高危依赖 |

### 测试与质量保证

- **单元测试**：后端使用 `pytest`，覆盖率目标 90% 以上；前端使用 `vitest`。
- **集成测试**：使用 `pytest-asyncio` 对 FastAPI 路由进行端到端测试。
- **性能基准**：针对 AI 推理接口使用 `locust` 进行负载测试，确保 95% 请求响应时间 < 500ms。
- **安全审计**：每次 PR 必须通过 **OWASP Dependency-Check**，并在 CI 中执行静态代码分析。

### 安全与合规

- **敏感信息加密**：所有用户手机号、身份证号在数据库层使用 AES-256 加密。
- **超时与重试**：对外部 API（NVIDIA NIM）统一封装 `httpx` 客户端，设置 5 秒超时、指数退避重试（最多 3 次）。
- **访问控制**：基于角色的访问控制（RBAC），仅管理员可访问模型管理接口。
- **合规审计**：日志全部写入结构化 JSON，便于审计合规（GDPR、国内网络安全法）。

---

## 核心功能列表

1. **用户注册与登录**（OAuth2 + JWT）
2. **AI 评估引擎**：多模态模型对射击、格斗、战术决策进行评分。
3. **图像/视频上传与分析**（NVIDIA NIM Vision 模型）
4. **战术决策模拟**（基于 LLM 的情景推理）
5. **实时数据可视化仪表盘**（ECharts）
6. **报告生成**（PDF/HTML）
7. **任务调度与异步推理**（Celery + RabbitMQ）
8. **权限管理与审计日志**
9. **多语言支持**（中文/英文）
10. **系统健康监控**（Prometheus + Grafana）

---

## 功能实现细节

### 用户登录与鉴权

- 前端使用 **Naive UI** 表单组件，配合 **Pinia** 保存登录状态。
- 登录请求发送至 `/api/auth/login`，后端使用 **FastAPI OAuth2PasswordBearer** 实现。
- 密码使用 **bcrypt** 哈希存储；JWT 使用 **RS256** 私钥签名，公钥通过 **JWKS** 暴露。
- 前端拦截器（Axios）在每次请求头中自动注入 `Authorization: Bearer <token>`。

### AI 评估引擎

- **模型选择**：NVIDIA NIM `multimodal-v2`（视觉+语言）与 `reasoning-v2`（逻辑推理）双模型组合。
- **调用方式**：封装 `httpx.AsyncClient`，统一请求体结构 `{"input": ..., "parameters": {...}}`。
- **异步执行**：上传文件后立即返回任务 ID，Celery worker 拉取任务并调用模型，完成后将结果写入 Redis 缓存并触发 WebSocket 推送。
- **评分规则**：基于业务需求的自定义 Python 脚本，对模型输出进行后处理，生成 0-100 分的综合评分。

### 多模态图像分析

- 前端使用 **Naive UI** `Upload` 组件，支持拖拽、分片上传。
- 后端接收 `multipart/form-data`，存储至 **MinIO**（S3 兼容）对象存储。
- 调用 NVIDIA NIM Vision 模型进行目标检测、姿态估计、动作识别。
- 结果以 **COCO** JSON 格式返回，前端使用 **ECharts** 的 `custom` 系列绘制标注图层。

### 战术决策模拟

- 场景脚本（JSON）描述战术环境（地图、敌方位置、资源分布）。
- 使用 **NVIDIA NIM LLM**（v2）进行情景推理，返回决策建议与风险评估。
- 前端通过 **Vue Router** 的动态路由展示不同场景的模拟页面。
- 决策结果持久化至 PostgreSQL，供后续报告生成使用。

### 报告生成与导出

- 报告模板采用 **Jinja2** + **WeasyPrint**，支持生成 PDF 与 HTML 双版本。
- 数据来源：用户上传的原始媒体、AI 评分、战术决策记录。
- 导出接口 `/api/report/{task_id}`，支持异步生成（Celery）并通过邮件或下载链接返回。

### 实时数据可视化

- 前端使用 **ECharts** 实时绘制分数趋势、热力图、决策路径图。
- 后端通过 **WebSocket**（FastAPI WebSocket）推送实时评分更新。
- 数据流经 **Redis Pub/Sub**，确保低延迟广播。

### 任务调度与异步推理

- 所有耗时的 AI 推理、报告生成、批量分析均封装为 Celery 任务。
- 任务状态存储在 **Redis**，前端轮询 `/api/tasks/{id}/status` 或订阅 WebSocket 事件。
- 任务失败自动重试（最多 2 次），并记录错误日志供审计。

---

## 系统当前已实现功能

| 功能 | 实现状态 | 关键技术 | 备注 |
|------|----------|----------|------|
| 用户注册/登录 | ✅ 完成 | FastAPI OAuth2, JWT, Naive UI | 支持邮箱/手机号注册，密码强度校验 |
| 文件上传与存储 | ✅ 完成 | Vite Upload, MinIO, FastAPI | 支持 2GB 单文件上传 |
| 基础图像分析（目标检测） | ✅ 完成 | NVIDIA NIM Vision, Celery | 检测枪支、姿态、动作 |
| 战术情景推理 | ✅ 完成 | NVIDIA NIM LLM, JSON 场景描述 | 支持 5 种预设战术场景 |
| 实时评分仪表盘 | ✅ 完成 | ECharts, WebSocket, Redis Pub/Sub | 95% 实时更新延迟 < 200ms |
| 报告生成（PDF） | ✅ 完成 | Jinja2, WeasyPrint, Celery | 支持自定义模板 |
| 权限管理（RBAC） | ✅ 完成 | FastAPI Depends, Pydantic | 管理员/教官/学员三角色 |
| CI/CD 自动化 | ✅ 完成 | GitHub Actions, Bazel CI | 每次 PR 自动构建、测试、镜像推送 |
| 安全扫描 | ✅ 完成 | Trivy, Dependabot | 每日扫描并生成安全报告 |
| 监控告警 | ✅ 完成 | Prometheus, Grafana, Alertmanager | CPU/内存/推理时延阈值告警 |

> **注**：以上功能均已通过 **pytest** 单元测试，覆盖率 ≥ 92%。

---

## 架构图示

```mermaid
flowchart TB
    subgraph Frontend[前端 Vue 应用]
        direction LR
        UI[UI 组件 (Naive UI)] --> Router[Vue Router]
        Router --> Store[Pinia Store]
        Store --> API[Axios HTTP 客户端]
        API --> WS[WebSocket 客户端]
    end

    subgraph Backend[后端 FastAPI 服务]
        direction LR
        Auth[Auth 路由] --> DB[PostgreSQL]
        Upload[文件上传路由] --> MinIO[对象存储]
        Analyze[分析路由] --> Celery[Celery Worker]
        Celery --> NIM[NVIDIA NIM 服务]
        Report[报告生成路由] --> Jinja[模板引擎]
        WS[WebSocket 路由] --> Redis[Redis Pub/Sub]
    end

    subgraph Infra[基础设施]
        Docker[Docker 容器]
        K8s[Kubernetes 集群]
        CI[GitHub Actions]
        Monitor[Prometheus & Grafana]
        Vault[HashiCorp Vault]
    end

    UI -->|REST API| Auth
    UI -->|REST API| Upload
    UI -->|REST API| Analyze
    UI -->|WebSocket| WS
    Auth -->|查询| DB
    Upload -->|写入| MinIO
    Analyze -->|任务调度| Celery
    Celery -->|调用| NIM
    Report -->|渲染| Jinja
    WS -->|推送| Redis
    Docker -->|部署| K8s
    CI -->|触发| Docker
    Monitor -->|监控| K8s
    Vault -->|密钥| Backend
```

---

## 开发与部署流程

1. **分支创建**：`git checkout -b feature/<需求编号>-<功能描述>`
2. **代码实现**：遵循 **PEP8** / **ESLint**，提交前运行 `bazel test //...` 确保所有单元测试通过。
3. **本地构建**：`bazel build //frontend:dev`、`bazel build //backend:dev`，使用 Vite 热更新调试前端。
4. **CI 检查**：Push 到远程后，GitHub Actions 自动执行 Bazel 构建、单元测试、代码扫描。
5. **镜像发布**：成功后自动构建 Docker 镜像并推送至内部 Harbor 仓库。
6. **部署**：使用 Helm Chart `helm upgrade --install ai-policing ./helm` 将新镜像部署到 Kubernetes。
7. **监控验证**：在 Grafana 仪表盘确认服务健康、推理时延、错误率均在阈值内。

---

## 未来规划与扩展方向

- **多模态模型升级**：引入最新的 NVIDIA NIM `multimodal-v3`，提升姿态估计精度至 98%。
- **移动端适配**：使用 **Vue Native** 开发移动端客户端，实现现场实时评估。
- **自定义场景编辑器**：提供可视化编辑器，教官可拖拽生成战术场景 JSON。
- **AI 教练模块**：基于强化学习为学员提供个性化训练建议。
- **跨平台数据共享**：实现与军队指挥系统的安全 API 对接，支持统一指挥调度。

---

## 参考文献与资源链接

- NVIDIA NIM 官方文档: https://docs.nvidia.com/nim
- FastAPI 官方指南: https://fastapi.tiangolo.com/
- Vue 3 官方文档: https://v3.vuejs.org/
- Bazel 官方手册: https://bazel.build/
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- GDPR 合规指南: https://gdpr.eu/

---

*本文档由 Antigravity 自动生成，更新时间：2026-04-05*

---

## 附录 A：API 参考

### 认证相关接口

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/auth/login` | 用户登录，返回 JWT | 公共 |
| POST | `/api/auth/register` | 用户注册，创建新账户 | 公共 |
| POST | `/api/auth/refresh` | 刷新 access token | 已登录 |
| POST | `/api/auth/logout` | 注销当前会话 | 已登录 |

### 用户管理接口

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/users/me` | 获取当前用户信息 | 已登录 |
| GET | `/api/users/{id}` | 获取指定用户详情 | 管理员 |
| PATCH | `/api/users/{id}` | 更新用户信息 | 管理员/本人 |
| DELETE | `/api/users/{id}` | 删除用户 | 管理员 |

### 文件上传与存储接口

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/files/upload` | 上传单个文件，返回文件 ID | 已登录 |
| POST | `/api/files/multipart` | 分片上传大文件 | 已登录 |
| GET | `/api/files/{id}` | 下载文件 | 已登录 |
| DELETE | `/api/files/{id}` | 删除文件 | 管理员 |

### AI 评估接口

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/eval/submit` | 提交评估任务（图片/视频） | 已登录 |
| GET | `/api/eval/status/{task_id}` | 查询评估任务状态 | 已登录 |
| GET | `/api/eval/result/{task_id}` | 获取评估结果 | 已登录 |
| POST | `/api/eval/batch` | 批量评估请求 | 管理员 |

### 报告生成接口

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/report/generate` | 异步生成报告（PDF/HTML） | 已登录 |
| GET | `/api/report/status/{report_id}` | 查询报告生成状态 | 已登录 |
| GET | `/api/report/download/{report_id}` | 下载已生成报告 | 已登录 |

---

## 附录 B：数据模型定义

### 用户模型（SQLAlchemy）

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="trainee")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 文件元数据模型

```python
class FileMeta(Base):
    __tablename__ = "file_meta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(100))
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    storage_path: Mapped[str] = mapped_column(String(512))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

### 评估任务模型

```python
class EvalTask(Base):
    __tablename__ = "eval_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    file_id: Mapped[int] = mapped_column(ForeignKey("file_meta.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
```

---

## 附录 C：性能基准报告

| 场景 | 并发请求数 | 平均响应时间 (ms) | 95th 百分位 (ms) | 错误率 |
|------|------------|-------------------|------------------|--------|
| 单张图片目标检测 | 50 | 180 | 210 | 0.0% |
| 视频流分析（5s） | 20 | 420 | 480 | 0.5% |
| 战术情景推理 | 30 | 350 | 390 | 0.2% |
| 报告生成（PDF） | 10 | 650 | 720 | 0.0% |

**测试工具**：Locust 2.15，部署在同一 Kubernetes 集群的负载生成器节点。

**硬件环境**：
- CPU: 2 vCPU (Intel Xeon) per worker pod
- Memory: 4 GiB per worker pod
- GPU: NVIDIA T4（用于 NIM 推理）

---

## 附录 D：运维脚本示例

### Helm values 示例（`values.yaml`）

```yaml
replicaCount: 3
image:
  repository: harbor.company.com/ai-policing/backend
  tag: "v1.4.2"
  pullPolicy: IfNotPresent
service:
  type: ClusterIP
  port: 80
resources:
  limits:
    cpu: "1"
    memory: "2Gi"
  requests:
    cpu: "500m"
    memory: "1Gi"
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: url
  - name: REDIS_URL
    value: "redis://redis:6379/0"
  - name: VAULT_ADDR
    value: "https://vault.company.com"
```

### CI/CD GitHub Actions 工作流（`.github/workflows/ci.yml`）

```yaml
name: CI
on:
  push:
    branches: [ "main", "feature/**" ]
  pull_request:
    branches: [ "main" ]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - name: Install Bazel
        uses: bazelbuild/setup-bazel@v3
        with:
          bazel-version: "6.5.0"
      - name: Bazel Build
        run: bazel build //... --config=ci
      - name: Run Tests
        run: bazel test //... --config=ci
      - name: Lint Backend
        run: bazel run //backend:lint
      - name: Lint Frontend
        run: npm ci && npm run lint
      - name: Security Scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: "harbor.company.com/ai-policing/backend:${{ github.sha }}"
      - name: Build Docker Image
        run: |
          docker build -t harbor.company.com/ai-policing/backend:${{ github.sha }} .
      - name: Push Docker Image
        run: |
          echo ${{ secrets.HARBOR_PASSWORD }} | docker login harbor.company.com -u ${{ secrets.HARBOR_USER }} --password-stdin
          docker push harbor.company.com/ai-policing/backend:${{ github.sha }}
```

---

## 附录 E：常见问题解答 (FAQ)

1. **如何更换 NIM 模型版本？**
   - 在 `backend/config.py` 中修改 `NIM_MODEL_VERSION` 环境变量，重新部署即可。
2. **上传文件大小限制为何是 2GB？**
   - 受限于 MinIO 配置的 `max_upload_size`，如需更改请在 `minio-config.yaml` 中调整并重启 MinIO 服务。
3. **Celery 任务为何卡住？**
   - 检查 RabbitMQ 队列深度和 Redis 可用内存，必要时扩容或清理过期任务。
4. **前端出现样式错位？**
   - 确认是否加载了全局 CSS 变量文件 `src/styles/variables.css`，并在 `main.ts` 中全局引入。
5. **如何开启审计日志导出？**
   - 在 Vault 中创建 `audit-log` 秘钥，后端 `loguru` 配置 `sink` 为 `syslog` 或对象存储路径。

---

## 附录 F：术语表

| 术语 | 定义 |
|------|------|
| NIM | NVIDIA Inference Microservice，提供高性能 AI 推理容器化服务 |
| RBAC | Role‑Based Access Control，基于角色的权限控制 |
| LLM | Large Language Model，大规模语言模型 |
| CI | Continuous Integration，持续集成 |
| CD | Continuous Deployment，持续部署 |
| S3 兼容 | 与 Amazon S3 API 兼容的对象存储协议 |
| PDF | Portable Document Format，可移植文档格式 |
| JWT | JSON Web Token，用于安全传递身份信息 |
| OAuth2 | 开放授权协议第二版，用于安全授权 |

---

*本文档由 Antigravity 自动生成，更新时间：2026-04-05*
