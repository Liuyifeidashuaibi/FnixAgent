# L6 — 商业化打包报告

## 1. 目标与边界

Community 安装包可复现 + Enterprise 边界定稿（2B 双轨）。

| 做                                       | 不做                               |
| ---------------------------------------- | ---------------------------------- |
| COMMERCIAL 定稿、Release/README 双轨说明 | 本轮强制打出全平台二进制（CI tag） |
| profile 注释门控                         | 另起闭源仓                         |

## 2. 实现清单

| 项                          | 路径                                 | 状态 |
| --------------------------- | ------------------------------------ | ---- |
| COMMERCIAL 定稿             | `docs/layers/COMMERCIAL.md`          | ✅   |
| Release checklist           | `docs/internal/RELEASE_CHECKLIST.md` | ✅   |
| DEPLOY 标明 Enterprise      | `docs/DEPLOY.md`                     | ✅   |
| BETA_RELEASE Community 说明 | `docs/BETA_RELEASE.md`               | ✅   |
| README 双轨表               | `README.md`                          | ✅   |
| profile.py 双轨注释         | `src/fnixagent/core/profile.py`      | ✅   |
| Release CI（既有）          | `.github/workflows/release.yml`      | ✅   |

## 3. 验收命令与证据

```bash
# 本地打包（需 MSVC / WebView2 / 磁盘空间）
pnpm prepare:release
pnpm --filter @fnixagent/workbench build
# → apps/workbench/.../bundle/nsis/*.exe

# 发版
git tag v1.0.0-beta.1
git push origin v1.0.0-beta.1
```

证据：文档与 profile 门控已就位；安装包由本地 `pnpm build` 或 tag CI 产出。

## 4. 下一层入口

六层闭环完成。后续迭代按层报告追加「变更附录」，不必重开契约。
