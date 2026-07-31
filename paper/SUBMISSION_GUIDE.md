# FnixAgent 投稿教程

> 面向项目作者，覆盖从论文完成到 FSE 2027 投稿成功的全流程。
> 论文目标：ACM FSE 2027（截稿 2026-10-02）
> 论文文件：`paper/main.tex` + `paper/refs.bib`（ACM sigconf 格式）

---

## 1. 投稿前检查清单

### 1.1 LaTeX 编译检查
在仓库根目录执行标准四步编译（pdflatex → bibtex → pdflatex → pdflatex），确保无错误：

```bash
cd paper
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

编译成功后生成 `paper/main.pdf`。若使用 latexmk：
```bash
latexmk -pdf main
```

### 1.2 页数检查
- FSE 2027 限制：**正文 12 页**（不含参考文献），参考文献页数不限。
- 检查方法：打开 `main.pdf`，定位到 `\bibliographystyle` 之前的最后一页页码 ≤ 12。
- 若超页：精简实验细节描述、合并表格、将部分内容移至补充材料（appendix/online appendix）。

### 1.3 匿名化检查
FSE 2027 **非双盲**（single-blind），但仍需移除可能暴露身份的信息：
- [ ] 移除正文中的 GitHub/GitLab URL（替换为 `<anonymized>` 占位）
- [ ] 移除 `paper/reproduction/` 中 `<submission-repo-url>` 占位之外的任何真实仓库地址
- [ ] 检查 `main.tex` 的 `\author` 块——FSE 非双盲可保留作者信息，但确认 affiliation 无敏感内部信息
- [ ] 确认复现包已按 `paper/reproduction/README.md` 的 "Anonymization notice" 处理（作者名、affiliation、识别性 URL 已移除）
- [ ] 检查代码注释、commit message 中无个人信息泄露

### 1.4 图表完整性检查
论文引用以下 PDF 图，必须存在且可正常渲染：

| 图文件路径 | 论文位置 | 内容 |
|-----------|----------|------|
| `paper/figures/architecture.pdf` | Figure 1 | 三进程架构：Tauri UI → agentd:8003 → fnix-local:8710 |
| `paper/figures/flywheel.pdf` | Figure 2 | MFP 四阶段：感知执行 → 固化 → 元反思 → 爬坡 |
| `paper/figures/longitudinal.pdf` | Figure 3 | KTG 节点数与 L3 规则随 1/7/30/90 天变化曲线 |

检查命令：
```bash
ls paper/figures/*.pdf
```

> 若图缺失，参见第 6 节"如何生成 figures"。

### 1.5 参考文献格式检查
- 使用 BibTeX，bib 文件为 `paper/refs.bib`
- 引用风格：ACM Reference Format（`\bibliographystyle{ACM-Reference-Format}`）
- 检查项：
  - [ ] 所有 `\cite{}` 引用在 `refs.bib` 中有对应条目（编译时无 `undefined references` 警告）
  - [ ] 无多余未引用的 bib 条目（避免 `unused entry` 警告）
  - [ ] DOI/URL 字段完整（ACM 要求尽量提供 DOI）
  - [ ] 会议名缩写符合 ACM 规范

---

## 2. FSE 2027 投稿流程

### 2.1 注册投稿系统账号
- FSE 通常使用 **EasyChair** 或 **HotCRP**（以 FSE 2027 官网公告为准）。
- 提前注册账号，确认邮箱可接收通知（审稿结果通过系统发送）。
- 所有共同作者需在系统中录入邮箱与 affiliation。

### 2.2 选择 Track
FSE 2027 通常提供以下 track（以官网 CFP 为准）：

| Track | 适合度 | 说明 |
|-------|--------|------|
| Research Track | ★★★★ | 偏方法贡献，强调 KTG/MFP/DAAO 的创新性与实验验证 |
| Tool Track | ★★★★★ | FnixAgent 是完整工具系统（桌面端 + agentd + 本地侧边栏），Tool Track 强调系统完整性与可复现性 |
| Industry Track | ★★★ | 若有工业部署案例可考虑 |

**推荐**：Tool Track 或 Research Track。
- 若强调"本地优先 AI Agent 系统 + 自进化知识拓扑"的系统贡献 → **Tool Track**（复现包是加分项）。
- 若强调 KTG/MFP/DAAO 的方法创新与消融实验 → **Research Track**。

### 2.3 上传文件
- **PDF**：`paper/main.pdf`（编译生成的最终版）
- **源码 zip**：包含 `main.tex` + `refs.bib` + `figures/` + 自定义 `.cls`/`.sty`（供 AC 验证编译）
- **复现包**：`paper/reproduction/` 目录（Dockerfile, docker-compose.yml, eval_mock.py, README.md, REPRODUCE.md）+ `paper/experiments/` 脚本

打包命令（示例）：
```bash
# 源码包
cd paper
zip submission-src.zip main.tex refs.bib figures/*.pdf
# 复现包（从仓库根目录打包）
cd ..
zip reproduction.zip paper/reproduction/ paper/experiments/
```

### 2.4 填写 Metadata
- **Title**：与 `main.tex` 中 `\title` 完全一致
- **Abstract**：与 `main.tex` 中 `\begin{abstract}` 完全一致（注意 LaTeX 特殊字符转义）
- **Keywords**：建议 `AI for SE, knowledge graph, self-evolving agent, local-first, code generation`
- **CCS Classifications**：建议
  - `Software and its engineering ~ Software development techniques` (主)
  - `Computing methodologies ~ Artificial intelligence` (次)
  - `Information systems ~ Information retrieval` (次)
- **Subject Area**：选择 `Software Engineering AI/ML` 或最接近的 SE 子领域

### 2.5 提交前最终确认
- [ ] PDF 在不同 PDF 阅读器中显示正常
- [ ] 所有图表标题、编号正确
- [ ] 参考文献列表无格式错乱
- [ ] 共同作者顺序与排序无争议
- [ ] 提交系统上传的 PDF 与本地 `main.pdf` 一致（hash 校验）

---

## 3. 论文修改建议（基于审稿人视角）

### 3.1 实验补强（高优先级）
1. **KTG vs GraphRAG 对比需真实运行**
   当前 exp2 中 `graph_rag_sim` 为模拟配置，任务分数为 mock 占位（`placeholder: true`）。审稿人会质疑对比公平性。
   - **行动**：启动 `agentd` + LLM，运行 `python paper/experiments/exp2_ktg_ablation.py --base http://127.0.0.1:8003`，用真实分数替换占位值。

2. **MFP vs EvolveR 对比讨论**
   论文需补充与 EvolveR 类方法的对比讨论，说明 MFP 四阶段爬坡机制与 EvolveR 的差异。

3. **补充 User Study**
   exp4 为纯模拟（seed=42 注入轨迹），审稿人可能质疑真实性。
   - **行动**：至少 10 用户、1 周真实使用，收集任务完成率、KTG 增长、满意度数据。

4. **FCS 基准 inter-annotator agreement**
   当前 FCS 任务由项目方自建自标，缺第三方验证。
   - **行动**：引入第三方标注者对 FCS 任务做标注一致性检验（Cohen's κ ≥ 0.7）。

5. **与 SWE-agent / OpenHands 直接对比**
   当前论文缺失与主流 Agent 框架的 head-to-head 对比，这是明显弱点。
   - **行动**：在 SWE-bench 或 FCS 子集上跑 SWE-agent / OpenHands baseline，提供对比表。

### 3.2 写作优化
- exp1 能力分布不均（write 占 83%，部分维度仅 1 任务），需在论文中说明分布原因与采样策略。
- exp4 命中率 33.33% 偏低，需解释这是模拟环境冷启动局限，补充真实使用数据支撑。
- 强调"本地优先"（local-first）的差异化贡献，避免与云端 Agent 框架正面比较 API 覆盖面。

---

## 4. 备选投稿策略

若 FSE 2027 被拒，按以下顺序备选：

### 4.1 会议备选
| 目标会议 | 预计截稿 | Track 建议 | 备注 |
|----------|---------|-----------|------|
| ASE 2027 | 2027-03 | Research / Tool | 自动化软件工程，与 FSE 同领域，可吸收 FSE 审稿意见修改 |
| NeurIPS 2027 | 2027-05 | 方法论文 | 若系统论文被拒，可拆出 KTG/MFP 方法部分投方法论文 |

### 4.2 期刊备选
| 期刊 | 类型 | 适合场景 |
|------|------|----------|
| TOSEM（ACM Transactions on Software Engineering and Methodology） | 滚动投稿 | 系统完整性高、实验充分后投期刊，无截稿压力 |
| TSE（IEEE Transactions on Software Engineering） | 滚动投稿 | 同上，备选 |

> 策略建议：FSE 被拒后，根据审稿意见决定——若审稿人认可系统贡献但要求更多实验 → 补实验后投 ASE；若审稿人认为方法贡献不足 → 拆方法投 NeurIPS 或转期刊长文。

---

## 5. 时间线规划

| 时间节点 | 里程碑 | 状态 |
|----------|--------|------|
| 2026-08 | 完成论文初稿 + 实验框架 | ✅ 已完成（exp1/exp4 真实数据，exp2/exp3 mock 占位） |
| 2026-08 ~ 2026-09 | 补强实验：真实 LLM ablation + user study + SWE-bench 对比 | ⏳ 待执行 |
| 2026-09-15 | 内审 + 修改（co-authors 交叉审阅） | ⏳ 待执行 |
| 2026-09-25 | 提交 FSE 2027 | ⏳ 待执行（截稿 2026-10-02，预留 1 周缓冲） |
| 2026-12 | 收到审稿结果 | ⏳ 待执行 |
| 2027-01 | rebuttal / camera-ready | ⏳ 待执行 |

### 关键路径提醒
- **8-9 月补强实验是关键路径**：exp2/exp3 真实运行依赖 `agentd` + API Key，需尽早配置。
- user study 需 1 周以上，必须在 9 月初启动。
- 9-15 前完成内审，留 10 天修改+编译+打包。

---

## 6. 编译与生成 PDF

### 6.1 环境要求
- **TeX Live 2024+** 或 **MiKTeX**（推荐 TeX Live，ACM 模板兼容性更好）
- Python 3.11+（生成 figures 用）
- 所需 LaTeX 包：`acmart`（ACM 文档类）、`bibtex`、`hyperref`、`graphicx`、`booktabs` 等

### 6.2 编译命令序列
```bash
cd paper
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

为什么需要四步：
1. 第一次 `pdflatex`：生成 `main.aux`（记录引用键）
2. `bibtex`：根据 `main.aux` 从 `refs.bib` 提取参考文献，生成 `main.bbl`
3. 第二次 `pdflatex`：将 `main.bbl` 与交叉引用写入
4. 第三次 `pdflatex`：解析所有交叉引用，确保编号正确

### 6.3 常见编译错误排查

| 错误 | 原因 | 解决 |
|------|------|------|
| `! LaTeX Error: File 'acmart.cls' not found` | 未安装 ACM 模板 | `tlmgr install acmart`（TeX Live）或更新 MiKTeX 包 |
| `Citation 'xxx' undefined` | `refs.bib` 缺条目或 `bibtex` 未运行 | 检查 `\cite{xxx}` 键名匹配；重跑 bibtex + 两次 pdflatex |
| `! Undefined control sequence` | 用了未定义命令 | 检查 `\usepackage` 是否齐全 |
| `Overfull \hbox` | 行宽溢出 | 微调措辞或加 `\sloppy`，非致命 |
| `! Cannot determine size of graphic` | 图片路径错误或格式不支持 | 确认 `figures/xxx.pdf` 存在；PDF 推荐用矢量格式 |
| 中文乱码 | 非 UTF-8 编码 | 确认 `main.tex` 保存为 UTF-8 |

### 6.4 如何生成 figures
论文 3 张图建议用 Python matplotlib 从实验数据生成 PDF（矢量格式）：

```bash
# 确保 Python 环境可用
python -c "import matplotlib; print(matplotlib.__version__)"

# 图的数据源已在实验结果中：
# - architecture.pdf: 架构图（建议手动绘制或用 draw.io 导出 PDF）
# - flywheel.pdf: MFP 流程图（建议手动绘制或用 draw.io 导出 PDF）
# - longitudinal.pdf: 基于 exp4 数据绘制
#   数据源: paper/experiments/results/exp4_longitudinal.json
#   X 轴: 1/7/30/90 天
#   Y 轴左: active_nodes (17→18→23→23)
#   Y 轴右: solidified_patterns (0→1→6→6)
```

`longitudinal.pdf` 绘制示例逻辑（参考 `exp4_longitudinal.json` 的 `horizons` 数组）：
- 读取每个 horizon 的 `final.active_nodes` 与 `final.solidified_patterns`
- 绘制双 Y 轴折线图，节点数上升后平台化，固化范式 7 天后稳定在 6

> `architecture.pdf` 与 `flywheel.pdf` 为结构示意图，建议用 draw.io / Excalidraw 绘制后导出 PDF。

---

## 7. 复现包使用说明

复现包位于 `paper/reproduction/`，供审稿人无 API Key 验证实验结构。详细协议见 `paper/reproduction/REPRODUCE.md`。

### 7.1 Docker 一键复现（推荐审稿人路径）
```bash
cd paper/reproduction
docker compose build
docker compose run repro
# 默认运行 exp1 + exp4（无 LLM），结果写入 paper/experiments/results/
```

容器内默认设置 `FNIX_MOCK_LLM=1`，并将 `paper/experiments/results/` 挂载到宿主机，结果持久化。

补充运行 mock ablation：
```bash
docker compose run repro python paper/reproduction/eval_mock.py
```

### 7.2 手动复现（Native 路径）
```bash
# 1. 创建虚拟环境
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# 2. 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 3. 运行测试套件（验证代码完整性）
python -m pytest tests -q

# 4. 启用 mock 模式
# Linux/macOS
export FNIX_MOCK_LLM=1
# Windows PowerShell
$env:FNIX_MOCK_LLM="1"

# 5. 运行全部实验（exp2/exp3 降级为占位）
python paper/experiments/run_all.py

# 6. 生成 mock 占位分数
python paper/reproduction/eval_mock.py
```

### 7.3 真实 LLM 运行（BYOK，可选）
```bash
# 1. 配置 API Key
cp .env.example .env
# 编辑 .env，填入任一 key:
#   OPENAI_API_KEY=sk-...
#   QWEN_API_KEY=sk-...
#   DEEPSEEK_API_KEY=sk-...
#   GLM_API_KEY=...

# 2. 启动 agentd（端口 8003）
python -m fnixagent

# 3. 验证 agentd 可达
curl -s http://127.0.0.1:8003 || echo "agentd not ready"

# 4. 运行真实实验（不带 --no-agent）
python paper/experiments/run_all.py --base http://127.0.0.1:8003
```

### 7.4 结果文件说明
运行后结果存放于 `paper/experiments/results/`：

| 文件 | 内容 | LLM 依赖 |
|------|------|----------|
| `exp1_fcs_stats.json` | FCS 基准统计（1000 任务） | 否 |
| `exp2_ktg_ablation.json` | KTG 消融（检索指标真实，分数 null/占位） | 分数:是 |
| `exp3_ablation.json` | MFP×DAAO 消融（路由指标真实，分数 null/占位） | 分数:是 |
| `exp4_longitudinal.json` | 纵向自进化（1/7/30/90 天） | 否 |
| `all_results.json` | 全部实验汇总 | — |
| `mock_ablation_results.json` | exp2/exp3 的 mock 占位分数 | 否(mock) |

### 7.5 常见问题
| 症状 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: fnixagent` | `src/` 不在路径中 | 从仓库根目录运行；或 `export PYTHONPATH=src` |
| exp2/exp3 `task_score_avg` 为 null | agentd 未运行（mock 模式预期行为） | 启动 `python -m fnixagent` 后去掉 `--no-agent` 重跑 |
| `Address already in use: 8003` | 端口被占用 | `netstat -ano \| findstr :8003`（Windows）停止占用进程 |
| exp1 `total_tasks ≠ 1000` | 基准包不完整 | 检查 `benchmarks/code/seed/` 与 `benchmarks/code/generated/` |

---

## 附录：关键文件路径速查

| 文件 | 用途 |
|------|------|
| `paper/main.tex` | 论文主文件（ACM sigconf） |
| `paper/refs.bib` | 参考文献 |
| `paper/figures/architecture.pdf` | Figure 1 架构图 |
| `paper/figures/flywheel.pdf` | Figure 2 MFP 流程图 |
| `paper/figures/longitudinal.pdf` | Figure 3 纵向演化曲线 |
| `paper/experiments/run_all.py` | 实验编排脚本 |
| `paper/experiments/exp1_fcs_scale.py` | exp1 脚本 |
| `paper/experiments/exp2_ktg_ablation.py` | exp2 脚本 |
| `paper/experiments/exp3_mfp_daao_ablation.py` | exp3 脚本 |
| `paper/experiments/exp4_longitudinal.py` | exp4 脚本 |
| `paper/reproduction/Dockerfile` | 复现包容器定义 |
| `paper/reproduction/docker-compose.yml` | 复现包编排 |
| `paper/reproduction/eval_mock.py` | Mock 评估脚本 |
| `paper/reproduction/README.md` | 复现包快速开始 |
| `paper/reproduction/REPRODUCE.md` | 复现包详细协议 |
| `paper/EXPERIMENT_REPORT.md` | 实验报告（本投稿配套） |
