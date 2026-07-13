"""
信号处理 (Signal Processing)
===============================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  FFT              - 快速傅里叶变换 (Cooley-Tukey, 基2 radix)
  DFT              - 离散傅里叶变换 (朴素 O(n^2), 验证用)
  Convolution      - 卷积 (直接/FFT 加速)
  WindowFunctions  - 窗函数 (Hann/Hamming/Blackman/Kaiser)
  Correlation      - 互相关/自相关
  SpectralAnalysis - 频谱分析 (功率谱/频域特征)
  Filters          - 数字滤波器 (移动平均/Savitzky-Golay/中值)
"""
from __future__ import annotations

import cmath
import math
from typing import Sequence


# ===========================================================================
# FFT — 快速傅里叶变换
# ===========================================================================

class FFT:
    """快速傅里叶变换 (Cooley-Tukey 算法, 基-2)。

    原理:
      - 分治: 将 DFT 分解为偶数项和奇数项
      - 蝶形运算: X[k] = E[k] + W^k * O[k]
      - 要求输入长度为 2 的幂

    复杂度: O(n log n) (朴素 DFT 为 O(n^2))

    Example:
        >>> # 信号: 1Hz 正弦波 + 4Hz 正弦波
        >>> signal = [math.sin(2*math.pi*1*t/8) + math.sin(2*math.pi*4*t/8) for t in range(8)]
        >>> spectrum = FFT.transform(signal)
        >>> magnitudes = [abs(x) for x in spectrum]
    """

    @staticmethod
    def transform(data: Sequence[complex | float]) -> list[complex]:
        """正变换: 时域 → 频域。

        Args:
            data: 输入序列 (长度需为 2 的幂)

        Returns:
            频域复数序列
        """
        n = len(data)
        if n == 0:
            return []
        # 补零到 2 的幂
        if n & (n - 1) != 0:
            n = 1 << (n - 1).bit_length()
            data = list(data) + [0.0] * (n - len(data))
        return FFT._fft(list(data), n)

    @staticmethod
    def inverse(spectrum: Sequence[complex]) -> list[complex]:
        """逆变换: 频域 → 时域。"""
        n = len(spectrum)
        if n == 0:
            return []
        if n & (n - 1) != 0:
            n = 1 << (n - 1).bit_length()
            spectrum = list(spectrum) + [0j] * (n - len(spectrum))
        # 共轭 → 正变换 → 共轭 → 除以 N
        conjugated = [x.conjugate() for x in spectrum]
        result = FFT._fft(conjugated, n)
        return [x.conjugate() / n for x in result]

    @staticmethod
    def _fft(a: list[complex], n: int) -> list[complex]:
        """递归 FFT (长度 n 必须为 2 的幂)。"""
        if n == 1:
            return [a[0]]
        # 分偶奇
        even = FFT._fft([a[i] for i in range(0, n, 2)], n // 2)
        odd = FFT._fft([a[i] for i in range(1, n, 2)], n // 2)
        # 蝶形合并
        result = [0j] * n
        for k in range(n // 2):
            w = cmath.exp(-2j * math.pi * k / n)
            result[k] = even[k] + w * odd[k]
            result[k + n // 2] = even[k] - w * odd[k]
        return result

    @staticmethod
    def transform_real(data: Sequence[float]) -> list[complex]:
        """实数序列 FFT (自动补零到 2 的幂)。"""
        return FFT.transform([complex(x, 0) for x in data])

    @staticmethod
    def magnitude_spectrum(data: Sequence[float]) -> list[float]:
        """幅度谱。"""
        spectrum = FFT.transform_real(data)
        return [abs(x) for x in spectrum]

    @staticmethod
    def power_spectrum(data: Sequence[float]) -> list[float]:
        """功率谱 (幅度平方)。"""
        spectrum = FFT.transform_real(data)
        return [abs(x) ** 2 for x in spectrum]

    @staticmethod
    def phase_spectrum(data: Sequence[float]) -> list[float]:
        """相位谱 (弧度)。"""
        spectrum = FFT.transform_real(data)
        return [cmath.phase(x) for x in spectrum]


# ===========================================================================
# DFT — 离散傅里叶变换 (朴素)
# ===========================================================================

class DFT:
    """离散傅里叶变换: 朴素 O(n^2), 用于验证 FFT 正确性。

    复杂度: O(n^2)

    Example:
        >>> signal = [1, 2, 3, 4]
        >>> DFT.transform(signal)  # [10+0j, -2+2j, -2+0j, -2-2j]
    """

    @staticmethod
    def transform(data: Sequence[complex | float]) -> list[complex]:
        """正变换。"""
        n = len(data)
        if n == 0:
            return []
        result = []
        for k in range(n):
            sum_val = 0j
            for t in range(n):
                angle = -2j * math.pi * k * t / n
                sum_val += complex(data[t]) * cmath.exp(angle)
            result.append(sum_val)
        return result

    @staticmethod
    def inverse(spectrum: Sequence[complex]) -> list[complex]:
        """逆变换。"""
        n = len(spectrum)
        if n == 0:
            return []
        result = []
        for t in range(n):
            sum_val = 0j
            for k in range(n):
                angle = 2j * math.pi * k * t / n
                sum_val += spectrum[k] * cmath.exp(angle)
            result.append(sum_val / n)
        return result


# ===========================================================================
# Convolution — 卷积
# ===========================================================================

class Convolution:
    """卷积运算: 直接法和 FFT 加速法。

    Example:
        >>> Convolution.direct([1, 2, 3], [0, 1, 0.5])
        [0.0, 1.0, 2.5, 4.0, 1.5]
        >>> Convolution.fft([1, 2, 3], [0, 1, 0.5])
        [(0+0j), (1+0j), (2.5+0j), (4+0j), (1.5+0j)]
    """

    @staticmethod
    def direct(a: Sequence[float], b: Sequence[float]) -> list[float]:
        """直接卷积, O(n*m)。"""
        if not a or not b:
            return []
        n, m = len(a), len(b)
        result = [0.0] * (n + m - 1)
        for i in range(n):
            for j in range(m):
                result[i + j] += a[i] * b[j]
        return result

    @staticmethod
    def fft(a: Sequence[float], b: Sequence[float]) -> list[complex]:
        """FFT 加速卷积, O(n log n)。"""
        if not a or not b:
            return []
        n, m = len(a), len(b)
        size = 1
        while size < n + m - 1:
            size <<= 1
        # 补零
        fa = list(a) + [0.0] * (size - n)
        fb = list(b) + [0.0] * (size - m)
        # FFT
        sa = FFT.transform(fa)
        sb = FFT.transform(fb)
        # 频域相乘
        sc = [sa[i] * sb[i] for i in range(size)]
        # IFFT
        result = FFT.inverse(sc)
        return result[:n + m - 1]

    @staticmethod
    def circular(a: Sequence[float], b: Sequence[float]) -> list[float]:
        """循环卷积 (长度必须相同)。"""
        if len(a) != len(b):
            raise ValueError("循环卷积要求两序列等长")
        n = len(a)
        if n == 0:
            return []
        result = [0.0] * n
        for i in range(n):
            for j in range(n):
                result[(i + j) % n] += a[i] * b[j]
        return result


# ===========================================================================
# WindowFunctions — 窗函数
# ===========================================================================

class WindowFunctions:
    """窗函数: 用于减少频谱泄漏。

    Example:
        >>> WindowFunctions.hann(8)  # [0.0, 0.146..., 0.5, 0.853..., 0.853..., 0.5, 0.146..., 0.0]
    """

    @staticmethod
    def rectangular(n: int) -> list[float]:
        """矩形窗 (不加窗)。"""
        return [1.0] * n

    @staticmethod
    def hann(n: int) -> list[float]:
        """Hann 窗 (升余弦窗)。"""
        if n <= 0:
            return []
        if n == 1:
            return [1.0]
        return [0.5 * (1 - math.cos(2 * math.pi * i / (n - 1))) for i in range(n)]

    @staticmethod
    def hamming(n: int) -> list[float]:
        """Hamming 窗。"""
        if n <= 0:
            return []
        if n == 1:
            return [1.0]
        return [0.54 - 0.46 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]

    @staticmethod
    def blackman(n: int) -> list[float]:
        """Blackman 窗 (旁瓣衰减更好)。"""
        if n <= 0:
            return []
        if n == 1:
            return [1.0]
        return [
            0.42 - 0.5 * math.cos(2 * math.pi * i / (n - 1))
            + 0.08 * math.cos(4 * math.pi * i / (n - 1))
            for i in range(n)
        ]

    @staticmethod
    def kaiser(n: int, beta: float = 8.6) -> list[float]:
        """Kaiser 窗 (可调参数 beta)。

        beta 控制主瓣宽度和旁瓣衰减的折中:
          beta=0 → 矩形窗
          beta=5 → Hamming 窗近似
          beta=8.6 → Blackman 窗近似
        """
        if n <= 0:
            return []
        if n == 1:
            return [1.0]
        from math import factorial
        # 修正贝塞尔函数 I0 (级数展开)
        def bessel_i0(x: float) -> float:
            result = 1.0
            term = 1.0
            for k in range(1, 50):
                term *= (x / (2 * k)) ** 2
                result += term
                if term < 1e-12 * result:
                    break
            return result
        denom = bessel_i0(beta)
        return [
            bessel_i0(beta * math.sqrt(1 - ((2 * i / (n - 1)) - 1) ** 2)) / denom
            for i in range(n)
        ]

    @staticmethod
    def apply(signal: Sequence[float], window: Sequence[float]) -> list[float]:
        """对信号施加窗函数。"""
        if len(signal) != len(window):
            raise ValueError(f"长度不匹配: signal={len(signal)}, window={len(window)}")
        return [s * w for s, w in zip(signal, window)]


# ===========================================================================
# Correlation — 互相关 / 自相关
# ===========================================================================

class Correlation:
    """互相关和自相关分析。

    Example:
        >>> Correlation.autocorrelate([1, 2, 3, 4, 5])
        [55, 40, 26, 14, 5]
    """

    @staticmethod
    def autocorrelate(signal: Sequence[float]) -> list[float]:
        """自相关函数 (非归一化)。

        R[k] = Σ_{t=0}^{N-1-k} signal[t] * signal[t+k]

        复杂度: O(n^2), 可用 FFT 加速到 O(n log n)
        """
        n = len(signal)
        if n == 0:
            return []
        result = [0.0] * n
        for k in range(n):
            for t in range(n - k):
                result[k] += signal[t] * signal[t + k]
        return result

    @staticmethod
    def cross_correlate(
        a: Sequence[float], b: Sequence[float]
    ) -> list[float]:
        """互相关函数。

        R_ab[k] = Σ_{t} a[t] * b[t+k]
        """
        n, m = len(a), len(b)
        result_len = n + m - 1
        result = [0.0] * result_len
        for i in range(n):
            for j in range(m):
                result[i + j] += a[i] * b[j]
        return result

    @staticmethod
    def normalized_autocorrelate(signal: Sequence[float]) -> list[float]:
        """归一化自相关 (值域 [-1, 1])。"""
        raw = Correlation.autocorrelate(signal)
        if not raw or raw[0] == 0:
            return [0.0] * len(raw)
        r0 = raw[0]
        return [r / r0 for r in raw]


# ===========================================================================
# SpectralAnalysis — 频谱分析
# ===========================================================================

class SpectralAnalysis:
    """频谱分析: 从时域信号提取频域特征。

    Example:
        >>> signal = [math.sin(2*math.pi*5*t/100) for t in range(128)]
        >>> SpectralAnalysis.dominant_frequency(signal, sample_rate=100)
        5.0  # 5 Hz
    """

    @staticmethod
    def power_spectrum(
        signal: Sequence[float],
        sample_rate: float = 1.0
    ) -> tuple[list[float], list[float]]:
        """计算功率谱密度。

        Returns:
            (frequencies, powers)
        """
        n = len(signal)
        if n == 0:
            return [], []
        psd = FFT.power_spectrum(signal)
        # 只取前一半 (实信号频谱对称)
        half = n // 2
        freqs = [i * sample_rate / n for i in range(half)]
        powers = [psd[i] / n for i in range(half)]
        return freqs, powers

    @staticmethod
    def dominant_frequency(
        signal: Sequence[float],
        sample_rate: float = 1.0
    ) -> float:
        """主频率 (功率最大的频率)。"""
        freqs, powers = SpectralAnalysis.power_spectrum(signal, sample_rate)
        if not freqs:
            return 0.0
        max_idx = max(range(len(powers)), key=lambda i: powers[i])
        return freqs[max_idx]

    @staticmethod
    def spectral_centroid(
        signal: Sequence[float],
        sample_rate: float = 1.0
    ) -> float:
        """频谱质心 (声音"亮度"指标)。"""
        freqs, powers = SpectralAnalysis.power_spectrum(signal, sample_rate)
        if not freqs:
            return 0.0
        total_power = sum(powers)
        if total_power < 1e-15:
            return 0.0
        return sum(f * p for f, p in zip(freqs, powers)) / total_power

    @staticmethod
    def spectral_entropy(
        signal: Sequence[float],
        sample_rate: float = 1.0
    ) -> float:
        """频谱熵 (频谱平坦度指标)。"""
        _, powers = SpectralAnalysis.power_spectrum(signal, sample_rate)
        if not powers:
            return 0.0
        total = sum(powers)
        if total < 1e-15:
            return 0.0
        probs = [p / total for p in powers]
        return -sum(p * math.log2(p) for p in probs if p > 1e-15)

    @staticmethod
    def zero_crossing_rate(signal: Sequence[float]) -> float:
        """过零率 (信号穿过零的频率)。"""
        n = len(signal)
        if n < 2:
            return 0.0
        crossings = sum(
            1 for i in range(1, n)
            if (signal[i - 1] >= 0) != (signal[i] >= 0)
        )
        return crossings / (n - 1)


# ===========================================================================
# Filters — 数字滤波器
# ===========================================================================

class Filters:
    """数字滤波器集。

    Example:
        >>> Filters.moving_average([1, 2, 3, 4, 5], window=3)
        [2.0, 3.0, 4.0]
    """

    @staticmethod
    def moving_average(
        signal: Sequence[float], window: int = 3
    ) -> list[float]:
        """移动平均滤波 (低通)。

        复杂度: O(n) (滑动窗口)
        """
        if window <= 0:
            raise ValueError(f"window 必须为正: {window}")
        n = len(signal)
        if n < window:
            return []
        result = []
        current_sum = sum(signal[:window])
        result.append(current_sum / window)
        for i in range(window, n):
            current_sum += signal[i] - signal[i - window]
            result.append(current_sum / window)
        return result

    @staticmethod
    def median_filter(
        signal: Sequence[float], window: int = 3
    ) -> list[float]:
        """中值滤波 (去除脉冲噪声)。

        复杂度: O(n * w * log w)
        """
        if window <= 0:
            raise ValueError(f"window 必须为正: {window}")
        n = len(signal)
        if n < window:
            return list(signal)
        half = window // 2
        result = []
        for i in range(n):
            lo = max(0, i - half)
            hi = min(n, i + half + 1)
            window_vals = sorted(signal[lo:hi])
            median = window_vals[len(window_vals) // 2]
            result.append(median)
        return result

    @staticmethod
    def savitzky_golay(
        signal: Sequence[float],
        window: int = 5,
        order: int = 2
    ) -> list[float]:
        """Savitzky-Golay 滤波 (多项式拟合平滑)。

        保留信号高阶矩, 比移动平均更好保留峰值。

        复杂度: O(n * window^2)
        """
        if window <= order:
            raise ValueError("window 必须大于 order")
        if window % 2 == 0:
            window += 1
        half = window // 2
        n = len(signal)
        # 构建 Vandermonde 矩阵并求伪逆 (仅用一次)
        # A[i][j] = i^j, i ∈ [-half, half], j ∈ [0, order]
        A = [
            [float(i) ** j for j in range(order + 1)]
            for i in range(-half, half + 1)
        ]
        # 求 A^T * A 的逆, 然后取第一行 (平滑系数)
        AtA = [
            [sum(A[k][i] * A[k][j] for k in range(window)) for j in range(order + 1)]
            for i in range(order + 1)
        ]
        # 矩阵求逆 (小矩阵, 直接用伴随矩阵法)
        AtA_inv = MatrixOps2.inverse(AtA)
        # 平滑系数 = A * AtA_inv 的第 0 列
        coeffs = [
            sum(A[i][j] * AtA_inv[j][0] for j in range(order + 1))
            for i in range(window)
        ]
        # 卷积
        result = []
        for i in range(n):
            if i < half or i >= n - half:
                result.append(signal[i])  # 边界保持
            else:
                val = sum(
                    coeffs[k] * signal[i - half + k]
                    for k in range(window)
                )
                result.append(val)
        return result

    @staticmethod
    def exponential_smoothing(
        signal: Sequence[float], alpha: float = 0.3
    ) -> list[float]:
        """指数平滑 (一阶 IIR 低通滤波)。

        y[t] = α * x[t] + (1-α) * y[t-1]

        α 越大, 跟踪越快但平滑越弱。
        """
        if not 0 < alpha <= 1:
            raise ValueError(f"alpha 必须在 (0, 1]: {alpha}")
        if not signal:
            return []
        result = [signal[0]]
        for i in range(1, len(signal)):
            result.append(alpha * signal[i] + (1 - alpha) * result[-1])
        return result

    @staticmethod
    def high_pass_difference(signal: Sequence[float]) -> list[float]:
        """一阶差分高通滤波。

        y[t] = x[t] - x[t-1]

        提取信号变化部分, 去除直流分量。
        """
        if len(signal) < 2:
            return []
        return [signal[i] - signal[i - 1] for i in range(1, len(signal))]


# ===========================================================================
# MatrixOps2 — 小矩阵运算 (供 Savitzky-Golay 用)
# ===========================================================================

class MatrixOps2:
    """小矩阵运算工具 (供滤波器内部使用)。"""

    @staticmethod
    def inverse(m: list[list[float]]) -> list[list[float]]:
        """矩阵求逆 (高斯消元)。"""
        n = len(m)
        aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)]
               for i, row in enumerate(m)]
        for col in range(n):
            pivot = abs(aug[col][col])
            pivot_row = col
            for row in range(col + 1, n):
                if abs(aug[row][col]) > pivot:
                    pivot = abs(aug[row][col])
                    pivot_row = row
            if pivot < 1e-15:
                raise ValueError("矩阵奇异")
            aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
            pv = aug[col][col]
            for j in range(2 * n):
                aug[col][j] /= pv
            for row in range(n):
                if row == col:
                    continue
                factor = aug[row][col]
                for j in range(2 * n):
                    aug[row][j] -= factor * aug[col][j]
        return [row[n:] for row in aug]
