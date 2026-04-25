# --- 第一阶段: 编译阶段 ---
FROM node:20-alpine AS build-stage

# --- 设置工作目录 ---
WORKDIR /app
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# --- 复制构建依赖文件并安装 ---
COPY ./frontend/package*.json ./
RUN npm install --frozen-lockfile

# --- 复制前端完整代码并构建 ---
COPY ./frontend ./
RUN npm run build

# --- 第二阶段: 运行阶段 ---
FROM nginx:stable-alpine AS production-stage

# --- 复制生成的静态文件到 Nginx ---
COPY --from=build-stage /app/dist /usr/share/nginx/html

# --- 复制自定义 Nginx 配置 (若需自定义代理等) ---
# COPY ./nginx.conf /etc/nginx/conf.d/default.conf

# --- 暴露端口并运行 ---
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
