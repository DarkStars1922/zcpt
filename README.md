# 综测平台后端（接口文档对齐版）

本仓库当前实现了两个业务模块：

- 认证与权限（Auth）
- 学生申报（Applications）

技术栈：FastAPI + SQLModel + JWT + bcrypt + SQLite（可切换 MySQL）

---

## 1. 运行方式

### 1.1 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 1.2 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

开发模式（热更新）：

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 1.3 动态文档

- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

## 2. 全局协议约定

- Base URL：`/api/v1`
- 认证方案：`Authorization: Bearer <access_token>`
- 统一响应：`code` / `message` / `data` / `request_id`
- 分页参数：`page`（默认1）/ `size`（默认10，最大100）

主要业务码：

- `0` 成功
- `1000` 通用业务错误（如账号密码错误、状态不允许）
- `1001` 参数校验失败
- `1002` 资源不存在
- `1003` 无权限
- `1004` 未登录或 token 缺失
- `1005` access token 无效或过期
- `1006` refresh token 无效或过期
- `1007` 业务冲突（如并发版本冲突、账号已存在）

---

## 3. 实现范围（对齐接口文档）

### 3.1 认证与权限

| 接口 | 状态 | 说明 |
|---|---|---|
| `POST /api/v1/auth/register` | ✅ 已实现 | 扩展接口，便于联调与测试 |
| `POST /api/v1/auth/login` | ✅ 已实现 | 返回 access/refresh token |
| `POST /api/v1/auth/refresh` | ✅ 已实现 | 使用 refresh token 刷新 access token |
| `POST /api/v1/auth/logout` | ✅ 已实现 | 需 `Authorization` + body中的 `refresh_token` |
| `POST /api/v1/auth/change-password` | ⏳ 未实现 | 文档有定义 |
| `GET /api/v1/users/me` | ⏳ 未实现 | 文档有定义 |
| `PUT /api/v1/users/me` | ⏳ 未实现 | 文档有定义 |

### 3.2 学生申报

| 接口 | 状态 | 说明 |
|---|---|---|
| `POST /api/v1/applications` | ✅ 已实现 | 创建申报 |
| `GET /api/v1/applications/my` | ✅ 已实现 | 我的申报列表 |
| `GET /api/v1/applications/my/category-summary` | ✅ 已实现 | 分类汇总 |
| `GET /api/v1/applications/my/by-category` | ✅ 已实现 | 分类明细 |
| `GET /api/v1/applications/{application_id}` | ✅ 已实现 | 详情 |
| `PUT /api/v1/applications/{application_id}` | ✅ 已实现 | 支持 `version` 并发控制 |
| `POST /api/v1/applications/{application_id}/withdraw` | ✅ 已实现 | 撤回 |
| `DELETE /api/v1/applications/{application_id}` | ✅ 已实现 | 软删 |

---

## 4. 当前业务规则

### 4.1 认证模块

- JWT 双令牌：Access + Refresh
- Refresh Token 落库（可撤销）
- 密码哈希：`bcrypt`
- 已处理密码 72-byte 限制（按 UTF-8 字节长度校验）

### 4.2 学生申报模块

- 学生仅可操作本人申报
- 管理员可执行软删
- 编辑与撤回仅允许状态：`pending_ai` / `ai_abnormal` / `pending_review`
- 并发控制：`version` 不一致返回 `1007`

### 4.3 状态流转

- 已落地：`pending_ai -> withdrawn`
- 已支持编辑区间：`pending_ai` / `ai_abnormal` / `pending_review`
- 后续（文档推荐）：`pending_ai -> (pending_review | ai_abnormal) -> (approved | rejected) -> archived`

---

## 5. 数据模型（当前）

- `user_info`：用户基础信息
- `refresh_token_record`：refresh token 记录与状态
- `comprehensive_apply`：申报信息（含 `version`、`is_deleted`、`attachments_json`）

---

## 6. 项目结构（当前）

```text
platform/
├── app/
│   ├── __init__.py
│   ├── api/v1/endpoints/
│   │   ├── auth.py
│   │   ├── applications.py
│   │   └── files.py
│   ├── api/v1/router.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── responses.py
│   │   └── security.py
│   ├── dependencies/
│   │   └── auth.py
│   ├── models/
│   │   ├── user.py
│   │   ├── refresh_token.py
│   │   └── application.py
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── application.py
│   │   ├── user.py
│   │   └── common.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── application_service.py
│   │   └── file_service.py
│   └── main.py
├── doc/
├── requirements.txt
└── README.md
```

### 6.1 各部分功能与作用

- `app/main.py`
	- 应用入口：创建 FastAPI 实例、注册路由、挂载中间件与全局异常处理。
	- 在生命周期阶段初始化数据库表。

- `app/api/v1/`
	- 对外 API 层（接口层）。
	- `router.py` 负责聚合 v1 所有业务路由。
	- `endpoints/` 负责 HTTP 协议细节：接收请求、参数校验、鉴权依赖注入、统一响应返回。

- `app/services/`
	- 业务层：封装核心业务规则与流程，不关心 HTTP 细节。
	- `auth_service.py` 负责登录、令牌刷新、当前用户解析等认证逻辑。
	- `application_service.py` 负责申报的创建、查询、编辑、撤回、软删除等规则。
	- `file_service.py` 负责文件上传校验（类型/大小）、落盘与读取定位。

- `app/models/`
	- 数据模型层（SQLModel/ORM）：定义数据库表结构与字段约束。
	- 如 `user.py`、`refresh_token.py`、`application.py` 分别对应用户、刷新令牌、申报记录。

- `app/schemas/`
	- 数据契约层（Pydantic）：定义请求/响应的数据结构与校验规则。
	- 例如登录请求、申报创建请求、附件字段校验等。

- `app/dependencies/`
	- 依赖注入层：沉淀可复用的 FastAPI 依赖。
	- 当前主要是认证依赖（从 token 解析当前用户）。

- `app/core/`
	- 基础设施层：全局配置、数据库连接、响应封装、安全工具。
	- 为上层提供统一且稳定的底层能力。

- `doc/`
	- 项目文档目录：存放接口说明与架构说明，用于开发联调与交付。

- `requirements.txt`
	- Python 依赖清单，保证开发与部署环境一致。

---

## 7. 已实现接口明细（请求/权限/返回）

以下仅覆盖当前代码已实现接口（与 `app/api/v1/endpoints` 对齐）。

### 7.1 通用响应格式

成功：

```json
{
	"code": 0,
	"message": "ok",
	"data": {},
	"request_id": "uuid"
}
```

失败：

```json
{
	"code": 1003,
	"message": "无权限",
	"request_id": "uuid"
}
```

---

### 7.2 认证与权限（Auth）

#### 1) 注册

- 接口：`POST /api/v1/auth/register`
- 权限：无需登录

请求 JSON：

```json
{
	"account": "20260001",
	"password": "12345678",
	"name": "张三",
	"role": "student",
	"class_id": 1,
	"is_reviewer": false,
	"email": "zhangsan@example.com",
	"phone": "13800000000"
}
```

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "注册成功",
	"data": {
		"user": {
			"id": 1,
			"name": "张三",
			"role": "student",
			"class_id": 1
		}
	},
	"request_id": "uuid"
}
```

#### 2) 登录

- 接口：`POST /api/v1/auth/login`
- 权限：无需登录

请求 JSON：

```json
{
	"account": "20260001",
	"password": "12345678"
}
```

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "登录成功",
	"data": {
		"user": {
			"id": 1,
			"name": "张三",
			"role": "student",
			"class_id": 1
		},
		"access_token": "<jwt>",
		"refresh_token": "<jwt>",
		"expires_in": 7200
	},
	"request_id": "uuid"
}
```

#### 3) 刷新 Access Token

- 接口：`POST /api/v1/auth/refresh`
- 权限：无需登录（仅需要合法 refresh_token）

请求 JSON：

```json
{
	"refresh_token": "<jwt>"
}
```

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "刷新成功",
	"data": {
		"access_token": "<jwt>",
		"expires_in": 7200
	},
	"request_id": "uuid"
}
```

#### 4) 退出登录

- 接口：`POST /api/v1/auth/logout`
- 权限：已登录用户（`Authorization: Bearer <access_token>`）

请求 JSON：

```json
{
	"refresh_token": "<jwt>"
}
```

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "退出成功",
	"data": {},
	"request_id": "uuid"
}
```

---

### 7.3 学生申报（Applications）

#### 1) 创建申报

- 接口：`POST /api/v1/applications`
- 权限：仅学生（已登录，`role=student`）

请求 JSON：

```json
{
	"award_type": "竞赛",
	"award_level": "国家级一等奖",
	"title": "全国大学生数学建模竞赛",
	"description": "团队获奖",
	"occurred_at": "2026-01-15",
	"attachments": [
		{
			"file_id": "file_abc123"
		}
	],
	"category": "intellectual",
	"sub_type": "discipline_competition"
}
```

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "创建成功",
	"data": {
		"id": 10,
		"status": "pending_ai",
		"item_score": null,
		"total_score": null,
		"score_rule_version": null,
		"created_at": "2026-02-21T10:00:00+00:00"
	},
	"request_id": "uuid"
}
```

#### 2) 我的申报列表

- 接口：`GET /api/v1/applications/my`
- 权限：仅学生（已登录，`role=student`）
- Query：`status`、`award_type`、`category`、`keyword`、`page`、`size`

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "获取成功",
	"data": {
		"page": 1,
		"size": 10,
		"total": 1,
		"list": [
			{
				"id": 10,
				"category": "intellectual",
				"sub_type": "discipline_competition",
				"award_type": "竞赛",
				"award_level": "国家级一等奖",
				"title": "全国大学生数学建模竞赛",
				"status": "pending_ai",
				"item_score": null,
				"total_score": null,
				"created_at": "2026-02-21T10:00:00+00:00"
			}
		]
	},
	"request_id": "uuid"
}
```

#### 3) 分类汇总

- 接口：`GET /api/v1/applications/my/category-summary`
- 权限：仅学生（已登录，`role=student`）
- Query：`term`（可选）

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "获取成功",
	"data": {
		"term": "2025-2026-1",
		"categories": [
			{
				"category": "intellectual",
				"category_name": "学业科研",
				"count": 3,
				"approved": 1,
				"pending": 2,
				"rejected": 0,
				"category_score": 2.0
			}
		],
		"total_score": 2.0
	},
	"request_id": "uuid"
}
```

#### 4) 分类明细

- 接口：`GET /api/v1/applications/my/by-category`
- 权限：仅学生（已登录，`role=student`）
- Query：`category`（必填）、`sub_type`、`status`、`term`、`page`、`size`

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "获取成功",
	"data": {
		"category": "intellectual",
		"term": "2025-2026-1",
		"list": [
			{
				"application_id": 10,
				"title": "全国大学生数学建模竞赛",
				"status": "pending_ai",
				"item_score": null,
				"total_score": null
			}
		]
	},
	"request_id": "uuid"
}
```

#### 5) 申报详情

- 接口：`GET /api/v1/applications/{application_id}`
- 权限：已登录且角色属于 `student/teacher/admin/reviewer`
- 额外限制：学生仅可查看本人申报

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "获取成功",
	"data": {
		"id": 10,
		"category": "intellectual",
		"sub_type": "discipline_competition",
		"award_type": "竞赛",
		"award_level": "国家级一等奖",
		"title": "全国大学生数学建模竞赛",
		"description": "团队获奖",
		"occurred_at": "2026-01-15",
		"attachments": [
			{
				"file_id": "file_abc123"
			}
		],
		"status": "pending_ai",
		"item_score": null,
		"total_score": null,
		"version": 1,
		"created_at": "2026-02-21T10:00:00+00:00"
	},
	"request_id": "uuid"
}
```

#### 6) 更新申报

- 接口：`PUT /api/v1/applications/{application_id}`
- 权限：仅学生（已登录，`role=student`）且仅本人数据
- 状态限制：仅 `pending_ai` / `ai_abnormal` / `pending_review`
- 并发控制：请求 `version` 必须与数据库一致

请求 JSON：

```json
{
	"award_type": "竞赛",
	"award_level": "国家级二等奖",
	"title": "全国大学生数学建模竞赛（修订）",
	"description": "补充说明",
	"occurred_at": "2026-01-15",
	"attachments": [
		{
			"file_id": "file_abc123"
		}
	],
	"category": "intellectual",
	"sub_type": "discipline_competition",
	"version": 1
}
```

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "更新成功",
	"data": {
		"id": 10,
		"status": "pending_ai",
		"version": 2,
		"updated_at": "2026-02-21T10:05:00+00:00"
	},
	"request_id": "uuid"
}
```

#### 7) 撤回申报

- 接口：`POST /api/v1/applications/{application_id}/withdraw`
- 权限：仅学生（已登录，`role=student`）且仅本人数据
- 状态限制：仅 `pending_ai` / `ai_abnormal` / `pending_review`

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "撤回成功",
	"data": {
		"id": 10,
		"status": "withdrawn",
		"version": 3
	},
	"request_id": "uuid"
}
```

#### 8) 删除申报（软删）

- 接口：`DELETE /api/v1/applications/{application_id}`
- 权限：
	- 学生：仅可删除本人申报
	- 管理员：可删除任意申报

返回 JSON（成功）：

```json
{
	"code": 0,
	"message": "删除成功",
	"data": {},
	"request_id": "uuid"
}
```

---

## 8. 后续建议

- 补齐 `users/me` 与 `change-password`
- 对接文件模块：`/files/upload` 与申报附件关联
- 增加 AI 审核结果落库与异步任务
- 迁移 MySQL + Alembic 版本化迁移
