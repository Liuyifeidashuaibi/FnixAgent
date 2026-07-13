# FnixAgent - 智能办公助手

> 面向学习/教育/办公场景的智能 Agent,核心能力包括论文文献检索、Word编辑、格式转换、图表生成、PDF生成、文档解析、学习辅助问答。

## 项目结构

```
FNIXAGENT/
├── config/                  # 配置文件
│   ├── settings.yaml        # 全局配置
│   ├── prompts/             # Prompt模板
│   └── security/            # 安全配置
├── src/fnixagent/
│   ├── main.py              # FastAPI入口
│   ├── core/                # 核心算法引擎
│   ├── api/                 # API接口层
│   ├── models/              # 数据模型
│   ├── adapters/            # 适配器层
│   └── business/            # 业务能力层
├── tests/                   # 测试代码
├── scripts/                 # 运维脚本
├── deploy/                  # 部署配置
├── docker-compose.yml       # Docker编排
├── Makefile                 # 构建脚本
└── requirements.txt         # 依赖清单
```

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/your-org/fnixagent.git
cd fnixagent

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件,填入API密钥等配置
```

### 2. 启动服务

```bash
# 方式1: 本地启动(开发模式)
make dev

# 方式2: Docker启动(完整环境)
make docker-up
make migrate  # 初始化数据库
make seed     # 导入种子数据
```

### 3. 访问服务

- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health
- API基础路径: http://localhost:8000/api/v1

## 核心功能

### API接口

| 接口 | 功能 | 路径 |
|------|------|------|
| 用户鉴权 | 注册/登录/JWT认证 | `/api/v1/auth/*` |
| Agent对话 | 智能对话/流式输出 | `/api/v1/chat/*` |
| 文档管理 | 上传/处理/下载 | `/api/v1/documents/*` |
| 任务管理 | 创建/查询/取消 | `/api/v1/tasks/*` |
| 工具管理 | 注册/执行/统计 | `/api/v1/tools/*` |

### 业务工具

- **论文检索**: arXiv / Semantic Scholar / 知网万方
- **Word编辑**: 创建/修改/格式化
- **格式转换**: docx ↔ pdf ↔ markdown ↔ html
- **图表生成**: 柱状图/折线图/饼图/散点图
- **PDF生成**: 报告/简历/学术论文
- **文档解析**: PDF/Word/图片 表格抽取、OCR
- **学习辅助**: 摘要/问答/笔记/抽认卡

## 开发指南

### 运行测试

```bash
# 运行所有测试
make test

# 代码检查
make lint
```

### 数据库操作

```bash
# 初始化数据库
make migrate

# 导入种子数据
make seed
```

### Docker操作

```bash
# 启动所有服务
make docker-up

# 查看日志
make logs

# 停止服务
make docker-down

# 清理数据
make docker-clean
```

## 技术架构

- **后端**: Python 3.11 + FastAPI
- **数据库**: PostgreSQL 16 + Milvus + Redis
- **LLM**: GLM / OpenAI / Qwen2.5
- **向量库**: Milvus
- **文件存储**: MinIO
- **搜索引擎**: Elasticsearch
- **监控**: Prometheus + Grafana + Jaeger

详细架构设计见 [ARCHITECTURE.md](ARCHITECTURE.md)

## 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| POSTGRES_PASSWORD | PostgreSQL密码 | ✅ |
| REDIS_PASSWORD | Redis密码 | ✅ |
| MINIO_ACCESS_KEY | MinIO访问密钥 | ✅ |
| MINIO_SECRET_KEY | MinIO密钥 | ✅ |
| GLM_API_KEY | GLM API密钥 | ✅ |
| JWT_SECRET_KEY | JWT密钥 | ✅ |

## 许可证

MIT License

## 联系方式

- 项目主页: https://github.com/your-org/fnixagent
- 问题反馈: https://github.com/your-org/fnixagent/issues