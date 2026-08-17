# Work 黄金场景（战役 2）

固定可回归的 Craft 任务。验收：产物落在 `.fnix/artifacts/` 下且可打开。

Beta 门槛：**≥ 8/10**；顶级：**≥ 9/10**。

| id | 提示摘要 | 期望产物 |
|----|----------|----------|
| `weekly_xlsx` | 本周销售汇总 xlsx | `.fnix/artifacts/weekly_sales/**/*.xlsx` |
| `hello_html` | 单页 Hello 站 | `.fnix/artifacts/hello_site/**/*.html` |
| `memo_md` | 会议纪要 md | `.fnix/artifacts/meeting_memo/**/*.md` |
| `status_report_docx` | 项目周报 docx | `.fnix/artifacts/status_report/**/*.docx` |
| `pitch_deck_pptx` | 产品介绍 pptx | `.fnix/artifacts/pitch_deck/**/*.pptx` |
| `brief_pdf` | 产品简介 pdf | `.fnix/artifacts/brief/**/*.pdf` |
| `sales_csv` | 销售明细 csv | `.fnix/artifacts/sales_data/**/*.csv` |
| `landing_site` | 落地页 html/css/js | `.fnix/artifacts/landing/**` |
| `todo_json` | 待办 list.json | `.fnix/artifacts/todos/**/*.json` |
| `checklist_txt` | 上线清单 txt | `.fnix/artifacts/release_checklist/**/*.txt` |

运行（需 agentd + Key，默认模型 `qwen3.7-plus`）：

```bash
# 跑全部 10 个
python scripts/e2e-work-golden.py --base http://127.0.0.1:8012 --limit 0

# 只跑前 3 个冒烟
python scripts/e2e-work-golden.py --base http://127.0.0.1:8012 --limit 3
```
