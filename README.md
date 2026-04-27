# 综测平台后端

本项目是一个基于 FastAPI 的综测平台后端，实现了认证、学生申报、AI 审核、审核员审核、教师复核、导出归档、公示申诉、系统配置等完整业务链路。

核心目标：

- 支持学生在线申报各类综测加分项目；
- 接入 AI 审核结果，辅助班委/教师进行审核；
- 为教师提供统计、导出、归档、公示、申诉处理等管理能力；
- 为管理员提供系统配置与日志查看能力。

前端仓库地址： <https://github.com/MincerGitHub/sdu-ai-evaluation-platform-frontend>

## 文档

- 架构说明：[docs/综测平台基本架构.md](docs/%E7%BB%BC%E6%B5%8B%E5%B9%B3%E5%8F%B0%E5%9F%BA%E6%9C%AC%E6%9E%B6%E6%9E%84.md)
- 接口文档：[docs/综测平台接口文档.md](docs/%E7%BB%BC%E6%B5%8B%E5%B9%B3%E5%8F%B0%E6%8E%A5%E5%8F%A3%E6%96%87%E6%A1%A3.md)


## 技术栈

- Web: FastAPI
- ORM: SQLModel / SQLAlchemy
- 鉴权: JWT
- 密码: bcrypt
- 数据库: SQLite / MySQL
- 缓存与队列: Redis / Celery
- 导出: openpyxl
- OCR: PaddleOCR / PaddlePaddle
- 迁移: Alembic

## 已实现能力

- 认证与用户资料
  - 注册、登录、刷新、登出、修改密码
  - `/users/me` 查询与更新
- 学生申报
  - 创建、更新、撤回、删除、分类汇总、详情查询
  - 附件上传与文件下载
- AI 审核
  - 异步审核任务
  - AI 报告查询与日志查询
- 审核员 / 教师审核
  - 待审列表、分类汇总、审核历史
  - 审核员通过后流转教师终审
  - 教师复核、归档、统计
- 导出 / 归档 / 公示 / 申诉
  - 异步导出 Excel
  - 归档记录、归档下载
  - 公示发布、关闭、删除
  - 学生申诉与教师处理
- 系统管理
  - 奖项字典
  - 系统配置
  - 系统日志
- Redis 能力
  - access token 黑名单
  - `Idempotency-Key` 去重
  - 导出状态缓存
  - 本地无 Redis 时自动回退到进程内缓存，便于 SQLite 调试
- 异步能力
  - 文件上传后的 OCR 分析、申报 AI 审核、邮件通知、Excel 导出均走 Celery worker
  - API 进程只处理轻量请求与任务入队，避免 OCR/导出阻塞学生访问

## 目录结构

```text
.
├─ app
│  ├─ api                 # 路由层
│  ├─ core                # 配置、数据库、缓存、Celery、启动初始化
│  ├─ data                # 后端自带字典/分值数据
│  ├─ dependencies        # 鉴权依赖
│  ├─ models              # SQLModel 数据模型
│  ├─ schemas             # 请求/响应 DTO
│  ├─ services            # 业务逻辑
│  └─ tasks               # Celery 异步任务
├─ alembic
│  └─ versions            # 迁移脚本
├─ doc                    # 架构与接口文档
├─ tests                  # 自动化测试
├─ docker-compose.yml
├─ Dockerfile
├─ alembic.ini
└─ requirements.txt
```

## 运行方式

### 1. 本地 SQLite 模式

适合单机开发、自测、接口联调。

1. 安装依赖

```bash
py -3 -m pip install -r requirements.txt
```

2. 准备环境变量

```bash
copy .env.example .env
```

建议保留如下配置：

```env
DATABASE_URL=sqlite:///./platform.db
REDIS_ENABLED=false
CELERY_TASK_ALWAYS_EAGER=true
AUTO_CREATE_TABLES=true
```

3. 启动 API

```bash
py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

说明：

- 首次触发文件 OCR 时，PaddleOCR 会自动下载模型到 `models/paddleocr/`
- 如需自定义模型路径，可在 `.env` 中配置 `PADDLE_MODEL_DIR` 或各个 `PADDLEOCR_*_MODEL_DIR`

4. 访问文档

- Swagger: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 2. MySQL + Redis + Celery 模式

适合正式部署和完整异步链路。

1. 配置 `.env`

```env
DATABASE_URL=mysql+pymysql://root:root@127.0.0.1:3306/zcpt?charset=utf8mb4
REDIS_ENABLED=true
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_TASK_ALWAYS_EAGER=false
AUTO_CREATE_TABLES=false
DB_POOL_SIZE=8
DB_MAX_OVERFLOW=8
CELERY_WORKER_PREFETCH_MULTIPLIER=1
```

2. 执行迁移

```bash
py -3 -m alembic upgrade head
```

3. 启动 API

```bash
py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

4. 启动 Worker

```bash
py -3 -m celery -A app.core.celery_app:celery_app worker --loglevel=INFO --concurrency=2
```

几千学生集中访问时，建议至少拆成：

- `api`：2-4 个 Uvicorn worker 起步，根据 CPU 与响应时间扩容。
- `worker-ocr`：单独跑 OCR/AI 审核 worker，PaddleOCR 很吃 CPU/内存，通常从 `--concurrency=1-2` 起步。
- `worker-export`：导出任务可单独 worker，避免大 Excel 抢 OCR 资源。
- `redis`：用于 Celery broker/result、token 黑名单、幂等键和导出状态缓存。
- `mysql`：开启连接池配置，按 `WEB_CONCURRENCY * (DB_POOL_SIZE + DB_MAX_OVERFLOW) + worker 并发 * (DB_POOL_SIZE + DB_MAX_OVERFLOW)` 估算 `max_connections`；本地 MySQL 默认常见为 151，建议先用 `DB_POOL_SIZE=8`、`DB_MAX_OVERFLOW=8`，需要更高吞吐时同步提高 MySQL `max_connections`。

本机压测口径可以使用仓库脚本：

```bash
PYTHONPATH=.runtime-deps:. python3 scripts/load_test.py \
  --base-url http://127.0.0.1:8000 \
  --mode read \
  --generated-users 1000 \
  --clients 250 \
  --concurrency 250 \
  --iterations 5
```

在 MySQL 默认 `max_connections=151` 的机器上，250 并发建议 API 使用 `DB_POOL_SIZE=20`、`DB_MAX_OVERFLOW=15`，Celery worker 使用较小池如 `4+4`；如果继续增加 Uvicorn worker、Celery 并发或部署多台 API，需要同步提高 MySQL `max_connections`。`/api/v1/applications/categories` 是静态评分规则树，接口只做 access token 与黑名单校验，不占用数据库连接。

### 3. Docker Compose

仓库已经提供 `mysql + redis + api + worker` 的编排文件。

```bash
copy .env.example .env
py -3 -m alembic upgrade head
docker compose up --build
```

如果宿主机没有 Docker，可以直接使用上面的本地模式。

## 数据库迁移

- 初始化迁移：`0001_initial_schema`
- 迁移入口：`alembic.ini` + `alembic/env.py`
- 执行升级：

```bash
py -3 -m alembic upgrade head
```

- 回滚：

```bash
py -3 -m alembic downgrade base
```

## 测试

```bash
py -3 -m pytest -q
```

当前测试覆盖：

- 认证与资料流转
- 学生申报、AI 审核、审核员审核、教师复核
- 导出、归档、公示、申诉、系统配置
- 真实 Redis 集成测试
  - token 黑名单写入 Redis
  - `Idempotency-Key` 去重

说明：

- 若本机没有运行 Redis，Redis 集成测试会自动跳过
- 在我当前这次实现中，已经在本机实际安装并验证了 Redis 连通

## 接口约定

- Base URL: `/api/v1`
- 统一响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "uuid"
}
```

- 鉴权头：

```http
Authorization: Bearer <access_token>
```

- 幂等请求头：

```http
Idempotency-Key: <client-generated-key>
```

## 重要说明

- 奖项分值与分类树已迁移到后端本地数据目录 `app/data`
- 邮件通知当前为异步模拟发送，不接真实 SMTP，但数据库记录、任务链路、日志查询都已实现
- AI 审核已接入 PaddleOCR，会在上传时缓存文件 OCR 结果，并在申报审核时结合标题、级别、姓名、文件名、印章、落款等信息生成审核报告
- 默认模型目录为 `models/paddleocr/`，已加入 `.gitignore`
