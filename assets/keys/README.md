# 开发密钥目录

此目录存放开发环境使用的密钥对，仅用于本地测试。

- `default.public.pem` — 开发公钥（可提交到仓库）
- `default.private.pem` — 开发私钥（**禁止提交**，已加入 .gitignore）

生产环境必须使用独立的密钥对，通过 KMS 或环境变量注入。