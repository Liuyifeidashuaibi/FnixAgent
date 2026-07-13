# FnixAgent Makefile
# 提供常用命令的快捷方式:安装 / 测试 / 迁移 / 启动 / 部署 / 清理

# Windows 兼容:PowerShell 默认 sh,但 Python 命令通用
PYTHON := python
PIP := $(PYTHON) -m pip

# 数据库连接(可被环境变量覆盖)
DATABASE_URL ?= postgresql+psycopg2://fnixagent:fnixagent@localhost:5432/fnixagent

# Docker Compose 生产环境编排文件
COMPOSE_PROD := docker compose -f deploy/docker/docker-compose.prod.yml

.PHONY: help install install-dev test test-cov lint format migrate migrate-create migrate-upgrade migrate-downgrade migrate-current migrate-history run clean gen-secrets deploy deploy-prod deploy-ps deploy-logs deploy-down deploy-reset

# ---------------------------------------------------------------------------
# 默认目标
# ---------------------------------------------------------------------------

help:
	@echo "FnixAgent Makefile — 常用命令:"
	@echo ""
	@echo "  make install         安装运行时依赖"
	@echo "  make install-dev     安装开发依赖(含测试/格式化/类型检查)"
	@echo "  make test            运行测试"
	@echo "  make test-cov        运行测试 + 覆盖率报告"
	@echo "  make lint            代码检查(ruff)"
	@echo "  make format          代码格式化(ruff)"
	@echo ""
	@echo "  数据库迁移(Phase 0.3):"
	@echo "  make migrate             应用所有未执行的迁移(= migrate-upgrade)"
	@echo "  make migrate-upgrade     升级到最新版本"
	@echo "  make migrate-downgrade   回滚一个版本"
	@echo "  make migrate-create m=\"描述\"  自动检测模型变化并生成新迁移"
	@echo "  make migrate-current     查看当前版本"
	@echo "  make migrate-history     查看迁移历史"
	@echo ""
	@echo "  make run              启动开发服务器"
	@echo "  make clean            清理构建产物"
	@echo ""
	@echo "  部署(Phase 1.10,详见 docs/DEPLOY.md):"
	@echo "  make gen-secrets      生成随机密码并写入 .env.prod"
	@echo "  make deploy           开发环境一键启动(docker compose up -d)"
	@echo "  make deploy-prod      生产环境一键启动(含 nginx + HTTPS)"
	@echo "  make deploy-ps        查看服务状态"
	@echo "  make deploy-logs      查看最近日志(最近 200 行)"
	@echo "  make deploy-down      停止并移除容器(保留数据)"
	@echo "  make deploy-reset     停止并删除所有数据卷(谨慎!)"

# ---------------------------------------------------------------------------
# 安装
# ---------------------------------------------------------------------------

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements.txt
	$(PIP) install -e ".[dev,security]"

# ---------------------------------------------------------------------------
# 测试 / 代码质量
# ---------------------------------------------------------------------------

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

test-cov:
	$(PYTHON) -m pytest tests/ --cov=src/fnixagent --cov-report=term-missing --cov-report=html

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m pyright src/fnixagent/

format:
	$(PYTHON) -m ruff check --fix src/ tests/
	$(PYTHON) -m ruff format src/ tests/

# ---------------------------------------------------------------------------
# 数据库迁移(Phase 0.3)
# ---------------------------------------------------------------------------

migrate: migrate-upgrade

migrate-upgrade:
	DATABASE_URL="$(DATABASE_URL)" alembic upgrade head

migrate-downgrade:
	DATABASE_URL="$(DATABASE_URL)" alembic downgrade -1

migrate-create:
	@if [ -z "$(m)" ]; then echo "用法: make migrate-create m=\"描述本次迁移\"" ; exit 1 ; fi
	DATABASE_URL="$(DATABASE_URL)" alembic revision --autogenerate -m "$(m)"

migrate-current:
	DATABASE_URL="$(DATABASE_URL)" alembic current

migrate-history:
	DATABASE_URL="$(DATABASE_URL)" alembic history --verbose

# ---------------------------------------------------------------------------
# 运行
# ---------------------------------------------------------------------------

run:
	$(PYTHON) -m uvicorn fnixagent.main:app --host 0.0.0.0 --port 8000 --reload

# ---------------------------------------------------------------------------
# 部署(Phase 1.10) — 详见 docs/DEPLOY.md
# ---------------------------------------------------------------------------

# 生成随机密码并写入 .env.prod(若文件不存在则从模板创建)
gen-secrets:
	@if [ ! -f .env.prod ]; then cp .env.prod.example .env.prod; echo "已从模板创建 .env.prod"; fi
	@echo "生成随机密码..."
	@PG_PW=$$(openssl rand -hex 24) && \
	RD_PW=$$(openssl rand -hex 24) && \
	MN_PW=$$(openssl rand -hex 16) && \
	ES_PW=$$(openssl rand -hex 16) && \
	JWT_PW=$$(openssl rand -hex 32) && \
	sed -i.bak \
		-e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$$PG_PW|" \
		-e "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$$RD_PW|" \
		-e "s|^MINIO_SECRET_KEY=.*|MINIO_SECRET_KEY=$$MN_PW|" \
		-e "s|^ES_PASSWORD=.*|ES_PASSWORD=$$ES_PW|" \
		-e "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$$JWT_PW|" \
		.env.prod && rm -f .env.prod.bak
	@echo "完成。请编辑 .env.prod 填写至少一个 LLM API 密钥:"
	@echo "  GLM_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY / QWEN_API_KEY"

# 开发环境一键启动(端口全部暴露,便于调试)
deploy:
	docker compose up -d --build
	@echo ""
	@echo "开发环境已启动。访问 http://localhost:8000/docs 查看 API"
	@echo "查看状态:make deploy-ps"

# 生产环境一键启动(仅 80/443 对外,含 nginx + HTTPS)
deploy-prod:
	@if [ ! -f .env.prod ]; then echo "错误:.env.prod 不存在,请先执行 make gen-secrets"; exit 1; fi
	@if [ ! -f deploy/nginx/certs/fullchain.pem ]; then \
		echo "提示:SSL 证书不存在,生成自签证书..."; \
		mkdir -p deploy/nginx/certs; \
		openssl req -x509 -newkey rsa:2048 -nodes \
			-keyout deploy/nginx/certs/privkey.pem \
			-out deploy/nginx/certs/fullchain.pem \
			-days 365 -subj "/CN=localhost" \
			-addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null; \
	fi
	$(COMPOSE_PROD) --env-file .env.prod up -d --build
	@echo ""
	@echo "生产环境已启动。等待健康检查(约 90 秒,期间 Milvus 在初始化)..."
	@echo "查看状态:    make deploy-ps"
	@echo "初始化数据库:$(COMPOSE_PROD) exec fnixagent alembic upgrade head"
	@echo "访问 HTTPS:  https://localhost/health"

# 查看服务状态
deploy-ps:
	@if [ -f .env.prod ]; then $(COMPOSE_PROD) --env-file .env.prod ps; \
	else docker compose ps; fi

# 查看最近日志(默认所有服务最近 200 行)
deploy-logs:
	@if [ -f .env.prod ]; then $(COMPOSE_PROD) --env-file .env.prod logs --tail 200; \
	else docker compose logs --tail 200; fi

# 停止并移除容器(保留数据卷)
deploy-down:
	@if [ -f .env.prod ]; then $(COMPOSE_PROD) --env-file .env.prod down; \
	else docker compose down; fi
	@echo "容器已停止,数据卷保留"

# 停止并删除所有数据卷(谨慎!会丢失数据)
deploy-reset:
	@echo "警告:即将删除所有数据卷,数据将永久丢失!"
	@read -p "确认输入 yes 继续:" confirm; [ "$$confirm" = "yes" ] || exit 1
	@if [ -f .env.prod ]; then $(COMPOSE_PROD) --env-file .env.prod down -v; \
	else docker compose down -v; fi
	@echo "所有容器与数据卷已删除"

# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------

clean:
	@echo "清理构建产物..."
	-rm -rf build/ dist/ *.egg-info src/*.egg-info
	-rm -rf .pytest_cache .mypy_cache .coverage htmlcov
	-find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	-find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "完成"
