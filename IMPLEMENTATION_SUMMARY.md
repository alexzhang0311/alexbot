# Claude Agent SDK 用户交互功能实现总结

## 完成时间
2026-05-19

## 实现内容

### 1. 后端实现

#### 1.1 Claude Agent SDK 交互回调 (`llm_service.py`)
- **位置**: `backend/app/services/llm_service.py`
- **核心功能**:
  - 实现 `can_use_tool` 回调，支持工具审批和 AskUserQuestion
  - 自动将 `AskUserQuestion` 加入工具列表（当有用户交互处理器时）
  - 添加 `PreToolUse` hook（Python SDK 要求，保持流式会话）
  - 支持流式输入模式（`prompt_stream`）
  - 从 `bypassPermissions` 切换到 `default` 权限模式（启用交互时）

#### 1.2 聊天服务链路透传 (`chat_service.py`)
- **位置**: `backend/app/services/chat_service.py`
- **修改**:
  - `chat()` 方法增加 `_user_input_handler` 参数
  - 传递到 LLM 服务调用链

#### 1.3 WebSocket 协议桥接 (`websocket.py`)
- **位置**: `backend/app/api/websocket.py`
- **核心功能**:
  - 实现 `handle_user_input()` 回调函数
  - 检测 Claude SDK 触发的工具审批/追问事件
  - 向前端发送 `user_input_required` 消息
  - 等待前端回复 `user_input_response`
  - 返回 `allow`/`deny` 决策给 SDK

#### 1.4 清理冗余接口 (`chat.py`)
- **位置**: `backend/app/api/chat.py`
- **修改**:
  - 删除了 `/chat` 和 `/stream` HTTP SSE 接口
  - 统一使用 WebSocket (`/api/chat/ws/{token}`)

### 2. 前端实现

#### 2.1 WebSocket 连接管理 (`index.html`)
- **核心功能**:
  - 替换原有的 HTTP SSE (`fetch`) 为 WebSocket
  - 自动连接和重连逻辑
  - 处理多种消息类型: `start`, `chunk`, `end`, `error`, `user_input_required`

#### 2.2 用户交互 UI 组件
##### ApprovalDialog - 工具授权弹窗
- 显示工具名称和参数
- 提供"允许"/"拒绝"按钮
- 发送 `user_input_response` 消息

##### QuestionDialog - 追问弹窗
- 解析 `AskUserQuestion` 的 questions 数组
- 支持单选/多选选项
- 支持 preview 预览（HTML/Markdown）
- 构建 `answers` 对象返回给 SDK

#### 2.3 状态管理
- 新增 `pendingApproval` 和 `pendingQuestion` 状态
- 新增 `wsRef` WebSocket 引用
- 集成到主 App 组件

## 协议规范

### 前端 → 后端 (WebSocket)

#### 聊天消息
```json
{
  "type": "chat",
  "payload": {
    "session_id": "xxx",
    "message": "用户消息",
    "model": "...",
    "provider_id": "...",
    "tools_enabled": true
  }
}
```

#### 用户输入响应 - 允许
```json
{
  "type": "user_input_response",
  "request_id": "xxx",
  "behavior": "allow",
  "updated_input": { /* 原始 input 或 questions+answers */ }
}
```

#### 用户输入响应 - 拒绝
```json
{
  "type": "user_input_response",
  "request_id": "xxx",
  "behavior": "deny",
  "message": "用户拒绝了此操作"
}
```

### 后端 → 前端 (WebSocket)

#### 流式响应
```json
{"type": "start", "session_id": "xxx"}
{"type": "chunk", "content": "..."}
{"type": "end", "tool_calls": ["Bash", "Write", ...]}
{"type": "error", "message": "..."}
```

#### 请求用户输入 - 工具审批
```json
{
  "type": "user_input_required",
  "request_id": "xxx",
  "kind": "approval",
  "tool_name": "Write",
  "input": {
    "file_path": "/path/to/file",
    "content": "..."
  }
}
```

#### 请求用户输入 - 追问
```json
{
  "type": "user_input_required",
  "request_id": "xxx",
  "kind": "question",
  "tool_name": "AskUserQuestion",
  "input": {
    "questions": [
      {
        "question": "如何格式化输出?",
        "header": "格式",
        "options": [
          {"label": "摘要", "description": "简要概述"},
          {"label": "详细", "description": "完整说明"}
        ],
        "multiSelect": false
      }
    ]
  }
}
```

## 使用流程

1. **用户发送消息** → WebSocket 发送 `chat` 消息
2. **Claude 调用工具** → 触发 `can_use_tool` 回调
3. **后端发送审批请求** → WebSocket 推送 `user_input_required`
4. **前端弹出对话框** → ApprovalDialog 或 QuestionDialog
5. **用户做出决策** → 点击"允许"/"拒绝"或提交答案
6. **前端发送响应** → WebSocket 发送 `user_input_response`
7. **Claude 继续执行** → 根据用户决策执行或跳过工具
8. **返回最终结果** → WebSocket 推送 `end` 消息

## 技术细节

### 权限模式切换
- 默认: `bypassPermissions` (工具直接执行)
- 启用交互: `default` (所有工具需审批，除非 permission rules 配置)
- 可配置: `provider.config.interactive_permission_mode`

### Python SDK 特殊要求
- 必须使用流式输入 (`prompt_stream`)
- 必须添加 `PreToolUse` hook 返回 `{"continue_": True}`
- 否则流会提前关闭，无法触发 `can_use_tool`

### Windows 兼容性
- 使用独立线程运行 SDK (`WindowsProactorEventLoopPolicy`)
- 通过 `queue.Queue` 跨线程传递消息
- 避免事件循环冲突

## 文件清单

### 修改的文件
- `backend/app/services/llm_service.py` - SDK 交互回调
- `backend/app/services/chat_service.py` - 透传用户交互处理器
- `backend/app/api/websocket.py` - WebSocket 协议桥接
- `backend/app/api/chat.py` - 删除冗余 HTTP SSE
- `frontend/public/index.html` - WebSocket 客户端 + 交互 UI

### 未修改但相关的文件
- `backend/app/schemas/schemas.py` - ChatRequest 已有 tools_enabled
- `backend/app/models/models.py` - ChatSession 已有 tools_enabled, provider_id
- `backend/app/core/config.py` - 配置文件

## 下一步优化建议

1. **前端体验**
   - 添加加载动画（等待审批时）
   - 支持自定义输入（"Other" 选项）
   - 显示历史审批记录

2. **权限规则**
   - 支持 PermissionUpdate（记住审批决策）
   - 配置白名单工具（自动放行）
   - 敏感操作二次确认

3. **错误处理**
   - WebSocket 断线重连
   - 超时处理（审批请求过期）
   - 回滚机制（拒绝后的后续处理）

4. **监控和审计**
   - 记录所有审批决策
   - 工具调用统计
   - 异常行为告警

## 参考文档
- Claude Agent SDK 文档: https://code.claude.com/docs/en/agent-sdk/user-input
- WebSocket 协议: RFC 6455
- React Hooks 最佳实践
