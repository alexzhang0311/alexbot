# AI Web Tool

企业内部 AI Web 工具平台，支持对话、Skill 插件、定时任务、长期记忆。

## 快速启动

```bash
cd /root/ai-web-tool

# 启动所有服务
docker compose up -d

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f backend
```

## 服务地址

- **前端**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

## 初始化

首次启动后，注册一个用户：

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123","email":"admin@company.com","full_name":"管理员"}'
```

然后登录获取 Token，开始使用。

## 项目结构

```
ai-web-tool/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/          # API 路由
│   │   ├── core/          # 核心配置
│   │   ├── models/        # SQLAlchemy 模型
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/      # 业务逻辑
│   │   └── skills/        # 内置 Skills
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/              # 前端（React 单页应用）
│   ├── public/
│   └── nginx.conf
└── docker-compose.yml
```

## 核心功能

- ✅ 用户认证 (JWT)
- ✅ 多会话对话
- ✅ WebSocket 流式响应
- ✅ Skill 插件系统
- ✅ 定时任务 (APScheduler)
- ✅ 长期记忆
- ✅ 流式 LLM 调用
- ❌ 前端流式响应（待实现）

## 下一步

1. 接入真实 LLM（OpenAI / Claude / 本地模型）
2. 实现 WebSocket 前端流式输出
3. 添加更多 Skill
4. 完善前端界面（响应式、移动端）
5. 添加审计日志
6. 部署到生产环境
