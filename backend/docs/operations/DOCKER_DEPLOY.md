# 智警实战综合训练平台 (CAPTP) Docker 部署指南

本指引将教您如何使用 Docker 和 Docker Compose 将系统部署为生产就绪环境。

## 1. 结构说明
我们将通过 **Docker Compose** 编排两个服务：
- **Backend**: FastAPI 服务，运行在 8000 端口。
- **Frontend**: Vue 3 服务，经 Vite 编译后由 Nginx 托管，运行在 80 端口。

---

## 2. 准备 Docker 配置文件

我已经为您创建了以下核心配置文件（见下文）：
1. `backend/Dockerfile`: 后端镜像构建脚本。
2. `frontend/Dockerfile`: 前端镜像构建脚本。
3. `docker-compose.yml`: 整体编排文件。
4. `.dockerignore`: 排除不必要的上传文件。

---

## 3. 部署步骤

### 第一步：安装 Docker
确保您的服务器或本地环境已安装 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。

### 第二步：配置 API 密钥
部署前，请确保您的环境变量或配置文件中包含必要的 NVIDIA API 密钥。可以通过修改 `docker-compose.yml` 中的 `env_vars` 或直接在服务器环境设置。

### 第三步：构建并运行
在项目根目录下执行以下命令：

```bash
# 1. 构建镜像 (首次运行或代码变更后)
docker-compose build

# 2. 后台启动服务
docker-compose up -d

# 3. 查看运行状态
docker-compose ps
```

### 第四步：访问平台
- **前端界面**: 浏览器访问 `http://101.33.210.169:6062`。
- **API 文档**: 访问 `http://101.33.210.169:6063/docs` 查看 Swagger 交互文档。

---

## 4. 常用维护命令

- **停止并移除容器**: `docker-compose down`
- **查看实时日志**: `docker-compose logs -f`
- **重启后端接口**: `docker-compose restart backend`
- **查看资源占用**: `docker stats`

---

*部署建议：生产环境下，建议在前端 Nginx 配置中增加 SSL 证书以保障链路安全。*
