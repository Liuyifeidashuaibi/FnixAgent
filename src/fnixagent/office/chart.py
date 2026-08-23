"""Chart Expert(P2-9)。

图表生成:bar/line/pie/scatter/area/radar/heatmap。

专家职责:
  - 生成静态图表(.png/.jpg/.svg)或 base64 字符串
  - 支持 CSV 直读、中文字体自动检测

底层依赖:
  - matplotlib(可选,不可用时降级为 ExpertError)
  - numpy(部分图表类型需要)

降级策略:
  - 强制使用 Agg 后端(无 GUI,适合服务器)
  - matplotlib 依赖缺失 → ExpertError 提示安装
  - 字体检测缓存,避免重复扫描 ttflist
  - plt.close(fig) 在 finally 中执行,防止内存泄漏

输出:
  - 静态图片文件(.png/.jpg/.svg)
  - 或 base64 编码字符串(用于内嵌报告)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import base64
import io
import logging
from functools import lru_cache
from typing import Any

from fnixagent.office.base import BaseExpert, ExpertError, ExpertResult

_logger = logging.getLogger(__name__)


# 支持的图表类型
_CHART_TYPES = {"bar", "line", "pie", "scatter", "area", "radar", "heatmap", "histogram"}


class ChartExpert(BaseExpert):
    """图表生成专家。

    全部方法返回 ExpertResult,output 为文件路径或 base64 字符串。

    能力边界:
      - 仅生成静态图,无交互
      - 中文字体依赖系统已安装字体
      - heatmap/histogram 需 numpy
    """

    @property
    def name(self) -> str:
        return "chart"

    # ------------------------------------------------------------------
    # 创建图表(主入口)
    # ------------------------------------------------------------------

    def create_chart(
        self,
        chart_type: str,
        data: dict[str, Any],
        output_path: str | None = None,
        title: str = "",
        xlabel: str = "",
        ylabel: str = "",
        figsize: tuple[float, float] = (8.0, 5.0),
        dpi: int = 120,
        style: str = "default",
        **options: Any,
    ) -> ExpertResult:
        """创建图表。

        Args:
            chart_type: bar/line/pie/scatter/area/radar/heatmap/histogram
            data: 数据结构,因图表类型而异:
                - bar/line/area: {categories: [...], series: {name: [values]}}
                - pie: {labels: [...], values: [...]}
                - scatter: {x: [...], y: [...], series: {name: {x:[], y:[]}}}
                - radar: {categories: [...], series: {name: [values]}}
                - heatmap: {matrix: [[...]], xticks: [...], yticks: [...]}
                - histogram: {values: [...], bins: 20}
            output_path: 输出文件路径(.png/.jpg/.svg);None 返回 base64
            title: 图表标题
            xlabel/ylabel: 坐标轴标签
            figsize: 画布尺寸(英寸)
            dpi: 分辨率
            style: matplotlib style 名
            **options: 其他 matplotlib 参数

        Returns:
            ExpertResult(output=output_path 或 base64 字符串)
        """
        # 输出路径校验(若指定)
        if output_path:
            err = self._validate_path(
                output_path,
                allowed_exts=("png", "jpg", "jpeg", "svg", "pdf", "bmp"),
                max_size=None,
            )
            if err:
                return self._failure(err)
        err = self._validate_string(chart_type, "chart_type")
        if err:
            return self._failure(err)
        err = self._validate_int(dpi, "dpi", min_value=1)
        if err:
            return self._failure(err)

        try:
            self._require_lib("matplotlib")
            import matplotlib

            # 强制 Agg 后端(无 GUI,线程安全,适合服务端)
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ExpertError as e:
            return self._failure(str(e))

        ct = chart_type.lower()
        if ct not in _CHART_TYPES:
            return self._failure(
                f"unsupported chart_type: {chart_type}. supported: {sorted(_CHART_TYPES)}",
            )

        fig = None
        try:
            if style and style != "default":
                try:
                    plt.style.use(style)
                except (ValueError, OSError):
                    # 未知 style 名或样式文件错误,降级为默认样式
                    pass

            # 中文字体支持(已缓存)
            self._setup_chinese_font(plt)

            fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

            if ct == "bar":
                self._draw_bar(ax, data, **options)
            elif ct == "line":
                self._draw_line(ax, data, **options)
            elif ct == "area":
                self._draw_area(ax, data, **options)
            elif ct == "pie":
                self._draw_pie(ax, data, **options)
            elif ct == "scatter":
                self._draw_scatter(ax, data, **options)
            elif ct == "radar":
                self._draw_radar(fig, ax, data, **options)
            elif ct == "heatmap":
                self._draw_heatmap(ax, data, **options)
            elif ct == "histogram":
                self._draw_histogram(ax, data, **options)

            if title:
                ax.set_title(title)
            if xlabel and ct not in ("pie", "heatmap", "radar"):
                ax.set_xlabel(xlabel)
            if ylabel and ct not in ("pie", "heatmap", "radar"):
                ax.set_ylabel(ylabel)

            # 仅当有多系列时显示图例
            if ct in ("bar", "line", "area", "scatter", "radar"):
                handles, labels = ax.get_legend_handles_labels()
                if labels:
                    ax.legend(loc=options.get("legend_loc", "best"))

            fig.tight_layout()

            # 输出
            if output_path:
                fig.savefig(output_path, bbox_inches="tight")
                return self._success(output_path, chart_type=ct)
            else:
                buf = io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                return self._success(f"data:image/png;base64,{b64}", chart_type=ct)
        except (OSError, PermissionError) as e:
            return self._failure(f"create_chart IO failed: {e}")
        except Exception as e:
            return self._failure(f"create_chart failed: {e}")
        finally:
            # 确保 figure 资源释放,避免内存泄漏与 Agg 后端资源占用
            if fig is not None:
                try:
                    plt.close(fig)
                except Exception:
                    _logger.debug('Unhandled exception', exc_info=True)

    # ------------------------------------------------------------------
    # 从 CSV 创建
    # ------------------------------------------------------------------

    def create_from_csv(
        self,
        csv_path: str,
        chart_type: str,
        x_column: str,
        y_columns: list[str],
        output_path: str | None = None,
        title: str = "",
        **options: Any,
    ) -> ExpertResult:
        """从 CSV 文件创建图表。

        Args:
            csv_path: CSV 文件路径
            chart_type: 图表类型
            x_column: X 轴列名
            y_columns: Y 轴列名列表(多列=多系列)
            output_path: 输出文件路径;None 返回 base64
            title: 图表标题
            **options: 透传给 create_chart

        Returns:
            ExpertResult(output=output_path 或 base64)
        """
        err = self._validate_path(csv_path, must_exist=True, allowed_exts=("csv",))
        if err:
            return self._failure(err)
        err = self._validate_string(x_column, "x_column")
        if err:
            return self._failure(err)
        if not y_columns:
            return self._failure("y_columns is empty")

        import csv

        try:
            # utf-8-sig 兼容 Excel 导出的 BOM
            with open(csv_path, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if not rows:
                return self._failure("empty CSV")
            categories = [row.get(x_column, "") for row in rows]
            series = {}
            for col in y_columns:
                values = []
                for row in rows:
                    try:
                        values.append(float(row.get(col, 0) or 0))
                    except (ValueError, TypeError):
                        values.append(0)
                series[col] = values
            data = {"categories": categories, "series": series}
            return self.create_chart(
                chart_type, data, output_path=output_path, title=title, **options
            )
        except (OSError, PermissionError) as e:
            return self._failure(f"create_from_csv IO failed: {e}")
        except Exception as e:
            return self._failure(f"create_from_csv failed: {e}")

    # ------------------------------------------------------------------
    # 支持的类型列表
    # ------------------------------------------------------------------

    def supported_types(self) -> list[str]:
        """返回支持的图表类型列表。"""
        return sorted(_CHART_TYPES)

    # ------------------------------------------------------------------
    # 内部绘图实现
    # ------------------------------------------------------------------

    def _draw_bar(self, ax, data: dict, **options: Any) -> None:
        import numpy as np

        categories = data.get("categories", [])
        series = data.get("series", {})
        if not series:
            return
        x = np.arange(len(categories))
        width = options.get("bar_width", 0.8 / max(len(series), 1))
        for i, (name, values) in enumerate(series.items()):
            offset = (i - (len(series) - 1) / 2) * width
            ax.bar(x + offset, values, width=width, label=name)
        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=options.get("x_rotation", 0))

    def _draw_line(self, ax, data: dict, **options: Any) -> None:
        import numpy as np

        categories = data.get("categories", [])
        series = data.get("series", {})
        x = np.arange(len(categories)) if categories else None
        for name, values in series.items():
            xs = x if x is not None else range(len(values))
            ax.plot(
                xs,
                values,
                marker=options.get("marker", "o"),
                label=name,
                linestyle=options.get("linestyle", "-"),
            )
        if categories:
            ax.set_xticks(range(len(categories)))
            ax.set_xticklabels(categories, rotation=options.get("x_rotation", 0))

    def _draw_area(self, ax, data: dict, **options: Any) -> None:
        import numpy as np

        categories = data.get("categories", [])
        series = data.get("series", {})
        x = np.arange(len(categories)) if categories else None
        for name, values in series.items():
            xs = x if x is not None else range(len(values))
            ax.fill_between(xs, values, alpha=options.get("alpha", 0.5), label=name)
        if categories:
            ax.set_xticks(range(len(categories)))
            ax.set_xticklabels(categories, rotation=options.get("x_rotation", 0))

    def _draw_pie(self, ax, data: dict, **options: Any) -> None:
        labels = data.get("labels", [])
        values = data.get("values", [])
        if not labels or not values:
            return
        ax.pie(
            values,
            labels=labels,
            autopct=options.get("autopct", "%1.1f%%"),
            startangle=options.get("startangle", 90),
            colors=options.get("colors"),
        )
        ax.axis("equal")

    def _draw_scatter(self, ax, data: dict, **options: Any) -> None:
        if "series" in data:
            for name, sdata in data["series"].items():
                ax.scatter(
                    sdata.get("x", []), sdata.get("y", []), label=name, s=options.get("s", 30)
                )
        else:
            ax.scatter(data.get("x", []), data.get("y", []), s=options.get("s", 30))

    def _draw_radar(self, fig, ax, data: dict, **options: Any) -> None:
        import numpy as np

        # radar 需要 polar projection
        ax.remove()
        ax = fig.add_subplot(111, projection="polar")
        categories = data.get("categories", [])
        series = data.get("series", {})
        n = len(categories)
        if n == 0:
            return
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles += angles[:1]
        for name, values in series.items():
            vv = list(values) + [values[0]] if values else []
            ax.plot(angles, vv, marker="o", label=name)
            ax.fill(angles, vv, alpha=options.get("alpha", 0.25))
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories)

    def _draw_heatmap(self, ax, data: dict, **options: Any) -> None:
        import numpy as np

        matrix = np.array(data.get("matrix", []))
        if matrix.size == 0:
            return
        im = ax.imshow(matrix, cmap=options.get("cmap", "viridis"), aspect="auto")
        xticks = data.get("xticks", [])
        yticks = data.get("yticks", [])
        if xticks:
            ax.set_xticks(range(len(xticks)))
            ax.set_xticklabels(xticks, rotation=options.get("x_rotation", 0))
        if yticks:
            ax.set_yticks(range(len(yticks)))
            ax.set_yticklabels(yticks)
        fig = ax.get_figure()
        fig.colorbar(im, ax=ax)
        # 写数值
        if options.get("annotate", True):
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    ax.text(
                        j,
                        i,
                        str(matrix[i, j]),
                        ha="center",
                        va="center",
                        color="white" if matrix[i, j] > matrix.mean() else "black",
                    )

    def _draw_histogram(self, ax, data: dict, **options: Any) -> None:
        values = data.get("values", [])
        bins = data.get("bins", options.get("bins", 20))
        ax.hist(
            values,
            bins=bins,
            alpha=options.get("alpha", 0.7),
            color=options.get("color", "steelblue"),
            edgecolor=options.get("edgecolor", "black"),
        )

    # ------------------------------------------------------------------
    # 中文字体
    # ------------------------------------------------------------------

    def _setup_chinese_font(self, plt) -> None:
        """配置中文字体(Windows 优先 SimHei)。

        字体可用列表经 lru_cache 缓存,避免每次画图都扫描 ttflist。
        """
        font = self._find_chinese_font()
        if font:
            plt.rcParams["font.sans-serif"] = [font]
            plt.rcParams["axes.unicode_minus"] = False

    @staticmethod
    @lru_cache(maxsize=1)
    def _find_chinese_font() -> str | None:
        """扫描 matplotlib 字体列表,返回首个可用的中文字体名(缓存)。"""
        try:
            import matplotlib
        except ImportError:
            return None
        candidates = ["SimHei", "Microsoft YaHei", "STSong", "Arial Unicode MS"]
        try:
            available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
        except Exception:
            return None
        for font in candidates:
            if font in available:
                return font
        return None
