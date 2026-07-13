"""Image Expert(P2-9 扩展)。

图像分析专家:从单张合成分镜图中精确提取网格单元(如 24 格分镜头)。

核心能力:
  - 精确网格检测:扫描白间隙定位 frame 边界,非均匀网格也能精准提取
  - 文字带裁剪:行方差剖面分析,自动检测每格底部文字描述带并裁剪
  - 固定比例裁剪(手动模式,兼容旧接口)

底层依赖:
  - numpy(必需要):行方差剖面分析,网格检测
  - Pillow(PIL,必需要):图像读写与裁剪

设计原则(与 BaseExpert 一致):
  - 统一 ExpertResult 返回
  - _validate_path 前置(扩展名/存在性/大小/穿越)
  - 零硬编码:参数均可配置
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

from fnixagent.office.base import BaseExpert, ExpertResult

# 图像大小上限(50 MB),防止超大图 OOM
_MAX_IMAGE_SIZE = 50 * 1024 * 1024
# 支持的输入扩展名
_SUPPORTED_EXTS = ("png", "jpg", "jpeg", "bmp", "tiff", "tif", "webp")


class ImageExpert(BaseExpert):
    """图像分析专家。

    全部方法返回 ExpertResult。

    能力边界:
      - 仅处理本地光栅图像(不处理矢量/URL)
      - 网格切割:auto_crop_text=True 时扫描白间隙精确定位 frame 边界;
        False 时使用 image_slicer 均匀切割
      - 文字带裁剪:auto_crop_text=True 逐格检测文字带边界;
        crop_text_ratio 固定比例裁剪(手动模式)

    文字带检测算法:
      行方差剖面分析:从底部向上扫描,找到连续高 std 的文字带,
      验证其位置(底部 30% 以内)、高度(5~35% 单元格)、
      平均 std(>=35,文字笔画特征)。返回文字带顶部行号,
      保证同行所有格子裁剪位置一致。
    """

    @property
    def name(self) -> str:
        return "image"

    # ------------------------------------------------------------------
    # 公共 API:网格单元提取
    # ------------------------------------------------------------------

    def extract_grid_cells(
        self,
        image_path: str,
        rows: Optional[int] = None,
        cols: Optional[int] = None,
        expected_count: int = 24,
        output_dir: Optional[str] = None,
        filename_prefix: str = "shot_",
        auto_crop_text: bool = False,
        crop_text_ratio: float = 0.0,
    ) -> ExpertResult:
        """从合成分镜图中提取网格单元,每单元输出一张 PNG。

        两种模式:
          - auto_crop_text=True:精确模式,扫描白间隙定位 frame 边界,
            逐格检测文字带并裁剪。适合分镜图等非均匀网格场景。
          - auto_crop_text=False:均匀模式,等分切割,可选固定比例裁剪。

        Args:
            image_path: 输入图像路径(png/jpg/bmp/tiff/webp)
            rows: 网格行数;省略则自动推断
            cols: 网格列数;省略则自动推断
            expected_count: 期望单元数(默认 24)
            output_dir: 输出目录;省略则在源图同目录建 <stem>_cells/
            filename_prefix: 输出文件名前缀(默认 "shot_")
            auto_crop_text: 是否精确模式(白间隙网格检测+文字带裁剪)
            crop_text_ratio: 底部裁剪比例(0.0~0.5),仅 auto_crop_text=False 时生效

        Returns:
            ExpertResult
        """
        # -- 参数校验 --------------------------------------------------
        err = self._validate_path(
            image_path, must_exist=True,
            allowed_exts=_SUPPORTED_EXTS, max_size=_MAX_IMAGE_SIZE,
        )
        if err:
            return self._failure(err)
        cerr = self._validate_int(
            expected_count, "expected_count", min_value=1, max_value=10000
        )
        if cerr:
            return self._failure(cerr)
        if rows is not None:
            rerr = self._validate_int(rows, "rows", min_value=1, max_value=64)
            if rerr:
                return self._failure(rerr)
        if cols is not None:
            cerr2 = self._validate_int(cols, "cols", min_value=1, max_value=64)
            if cerr2:
                return self._failure(cerr2)
        if not 0.0 <= crop_text_ratio <= 0.5:
            return self._failure(
                f"crop_text_ratio must be in [0.0, 0.5], got {crop_text_ratio}"
            )

        # -- 读取图像 --------------------------------------------------
        from PIL import Image
        try:
            with Image.open(image_path) as im:
                img_arr = np.array(im.convert("RGB"))
                img_w, img_h = im.size
        except Exception as e:
            return self._failure(f"failed to read image: {e}")

        # -- 输出目录 --------------------------------------------------
        if output_dir is None:
            stem = os.path.splitext(os.path.basename(image_path))[0]
            output_dir = os.path.join(
                os.path.dirname(os.path.abspath(image_path)), f"{stem}_cells",
            )
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            return self._failure(f"cannot create output_dir: {e}")

        # -- 网格解析 --------------------------------------------------
        if auto_crop_text:
            # 精确模式:白间隙检测 frame 行边界
            row_regions = self._detect_frame_rows(img_arr)
            r_final = len(row_regions)
            cols = cols or expected_count // r_final
            c_final = cols
            col_w = img_w // c_final
            col_regions = [(c * col_w, (c + 1) * col_w - 1) for c in range(c_final)]
        else:
            # 均匀模式:等分切割
            r_final, c_final = self._resolve_grid(rows, cols, expected_count)
            if r_final is None or c_final is None:
                return self._failure(
                    f"cannot resolve grid: rows={rows} cols={cols} "
                    f"expected_count={expected_count}"
                )
            tile_h = img_h // r_final
            tile_w = img_w // c_final
            row_regions = [(r * tile_h, (r + 1) * tile_h - 1) for r in range(r_final)]
            col_regions = [(c * tile_w, (c + 1) * tile_w - 1) for c in range(c_final)]

        # -- 提取+裁剪 ------------------------------------------------
        warnings: list[str] = []
        out_paths: list[str] = []
        crop_counts: dict[str, int] = {"auto": 0, "manual": 0, "none": 0}

        idx = 1
        for ry1, ry2 in row_regions:
            for cx1, cx2 in col_regions:
                frame = img_arr[ry1:ry2 + 1, cx1:cx2 + 1]
                crop_y = frame.shape[0]

                if auto_crop_text:
                    text_top = self._detect_text_top(frame)
                    if text_top < frame.shape[0]:
                        frame = frame[:text_top]
                        crop_counts["auto"] += 1
                    else:
                        crop_counts["none"] += 1
                elif crop_text_ratio > 0.0:
                    crop_y = int(frame.shape[0] * (1.0 - crop_text_ratio))
                    if 0 < crop_y < frame.shape[0]:
                        frame = frame[:crop_y]
                        crop_counts["manual"] += 1
                    else:
                        crop_counts["none"] += 1

                img = Image.fromarray(frame)
                new_name = f"{filename_prefix}{idx:02d}.png"
                new_path = os.path.join(output_dir, new_name)
                img.save(new_path, "PNG", compress_level=6)
                out_paths.append(os.path.abspath(new_path))
                idx += 1

        if len(out_paths) != expected_count:
            warnings.append(
                f"only {len(out_paths)}/{expected_count} cells saved"
            )

        return self._success(
            output=out_paths,
            rows=r_final,
            cols=c_final,
            cells=len(out_paths),
            image_size=(img_w, img_h),
            auto_crop_text=auto_crop_text,
            crop_text_ratio=crop_text_ratio,
            crop_counts=crop_counts,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # 内部:网格推断
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_grid(
        rows: Optional[int], cols: Optional[int], expected_count: int
    ) -> tuple[Optional[int], Optional[int]]:
        """根据 rows/cols/expected_count 推断最终网格。"""
        if rows is not None and cols is not None:
            return rows, cols
        if rows is not None:
            if expected_count % rows != 0:
                return None, None
            return rows, expected_count // rows
        if cols is not None:
            if expected_count % cols != 0:
                return None, None
            return expected_count // cols, cols
        best_r, best_c = None, None
        best_diff = float("inf")
        for r in range(1, int(expected_count**0.5) + 1):
            if expected_count % r == 0:
                c = expected_count // r
                diff = abs(r - c)
                if diff < best_diff:
                    best_diff = diff
                    best_r, best_c = r, c
        return best_r, best_c

    # ------------------------------------------------------------------
    # 内部:白间隙网格检测
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_frame_rows(img_arr: np.ndarray) -> list[tuple[int, int]]:
        """扫描水平白间隙,定位 frame 行边界。

        找 >=20 行的纯白带(mean>248, std<8)作为 frame 行间分隔,
        返回每行的 (y_start, y_end) 闭区间。

        最少需要 3 个间隙(分隔 4 行 frame),不足时回退到均匀分割。
        """
        g = img_arr.mean(axis=2)
        row_mean = g.mean(axis=1)
        row_std = g.std(axis=1)
        H = img_arr.shape[0]

        gaps: list[tuple[int, int]] = []
        i = 0
        while i < H:
            if row_mean[i] > 248 and row_std[i] < 8:
                start = i
                while i < H and row_mean[i] > 248 and row_std[i] < 8:
                    i += 1
                if i - start >= 20:
                    gaps.append((start, i - 1))
            i += 1

        if len(gaps) < 3:
            # 回退:均匀 4 行
            row_h = H // 4
            return [(r * row_h, (r + 1) * row_h - 1) for r in range(4)]

        # Frame 行:间隙之间
        regions = [(0, gaps[0][0] - 1)]
        for j in range(3):
            regions.append((gaps[j][1] + 1, gaps[j + 1][0] - 1))
        return regions

    # ------------------------------------------------------------------
    # 内部:文字带检测
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_text_top(cell_arr: np.ndarray) -> int:
        """检测单元格底部文字带顶部行号(行方差剖面分析)。

        从底部向上扫描,找到连续高 std 的文字带:
          1. 文字带在底部 30% 以内
          2. 文字带高度 5~35% 单元格
          3. 文字带内平均 std >= 35

        返回文字带顶部行号,保证同行所有格子裁剪位置一致。

        Args:
            cell_arr: 单元格 RGB 数组,shape=(H, W, 3)

        Returns:
            文字带顶部行号,无文字带时返回 H
        """
        g = cell_arr.mean(axis=2)
        row_std = g.std(axis=1)
        row_mean = g.mean(axis=1)
        h = g.shape[0]

        # 1. 从底部找第一个非白行
        p = h - 1
        while p >= 0 and (row_mean[p] > 240 and row_std[p] < 15):
            p -= 1
        if p < h * 0.5:
            return h

        # 2. 找连续 std>15 的文字带
        text_bottom = p
        text_top = p
        while text_top >= 0 and row_std[text_top] > 15:
            text_top -= 1
        text_top += 1

        band_h = text_bottom - text_top + 1
        if band_h < 5 or band_h > h * 0.35:
            return h

        # 3. 文字带在底部 30% 以内
        if text_top < h * 0.70:
            return h

        # 4. 文字带内平均 std 足够高
        if row_std[text_top:text_bottom + 1].mean() < 35:
            return h

        # 返回文字带顶部,保证同行一致
        return text_top
