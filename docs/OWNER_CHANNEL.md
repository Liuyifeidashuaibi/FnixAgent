# 所有者 / 管理员特殊通道

给项目所有者进入 Desktop Work / Admin 的专用入口，避免手机号/SSO 摩擦，同时不向公网开放自助提权。

## 怎么用（本机）

1. `.env` 中已有你的 `DASHSCOPE_API_KEY`（管理员 LLM）
2. 开发环境所有者口令默认：`fnix-owner-local-2026`（也可在 `.env` 配 `FNIX_OWNER_TOKEN`）
3. 重启 API
4. Desktop 登录页：**连点 Logo 5 次** →「所有者通道」
5. 账号 `admin`、密码（首次即创建）、口令（已预填）→ 进入工作台（JWT `role=admin`）
6. AI 设置会显示「服务端管理员 Key」掩码；Work 直接可用，无需再填 API Key

## LLM 策略

| 角色 | API Key |
|---|---|
| 管理员（所有者通道） | 自动用服务端 `.env` 的 DashScope/Qwen |
| 普通用户 | 必须在设置里自己填（BYOK） |

`GET /api/v1/work/llm-profile` 返回 provider/model/key_hint（不返回真实 Key）。

## API

`POST /api/v1/auth/owner/login`

```json
{
  "username": "admin",
  "password": "your-password",
  "owner_token": "fnix-owner-local-2026"
}
```

## 安全边界

| 项 | 行为 |
|---|---|
| 公开注册 | 强制 `role=user`，不能再自助注册 admin |
| 所有者口令 | 必须与服务端 `FNIX_OWNER_TOKEN`（或开发默认）一致 |
| 未配置 Token（生产） | 通道返回 403（关闭） |
| MFA | 本通道跳过（专供所有者本机） |
| 审计 | `LOGIN_SUCCESS` / `LOGIN_FAILED` 带 `channel=owner` |

生产环境请更换强 `FNIX_OWNER_TOKEN`，不要使用开发默认值。
