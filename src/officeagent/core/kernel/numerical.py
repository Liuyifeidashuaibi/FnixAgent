"""
数值方法 (Numerical Methods)
=============================
纯 Python + stdlib 实现,零外部依赖。

模块清单:
  NewtonMethod       - 牛顿法求根, 二次收敛
  GradientDescent    - 梯度下降优化器 (含 Adam / RMSProp 变体)
  Interpolation      - 线性/多项式插值
  Integration        - 数值积分 (梯形/辛普森/高斯)
  RootFinding        - 通用求根 (二分法/割线法/Brent)
  MatrixOps          - 矩阵运算 (乘/转置/行列式/逆/LU)
  Statistics         - 高级统计 (在线方差/协方差/分位数)
"""
from __future__ import annotations

import math
from typing import Callable, Sequence


# ===========================================================================
# NewtonMethod — 牛顿法求根
# ===========================================================================

class NewtonMethod:
    """牛顿法求根: x_{n+1} = x_n - f(x_n)/f'(x_n)。

    收敛性:
      - 二次收敛 (如果初始值足够接近根)
      - 需要 f'(x) ≠ 0

    复杂度: 每次迭代 O(1) (函数求值开销)

    Example:
        >>> f = lambda x: x**2 - 2
        >>> df = lambda x: 2*x
        >>> NewtonMethod.find_root(f, df, x0=1.5)  # ≈ 1.4142...
    """

    @staticmethod
    def find_root(
        f: Callable[[float], float],
        df: Callable[[float], float],
        x0: float,
        tol: float = 1e-8,
        max_iter: int = 100
    ) -> float:
        """牛顿法求 f(x) = 0 的根。

        Args:
            f: 目标函数
            df: 导函数
            x0: 初始猜测值
            tol: 收敛容差
            max_iter: 最大迭代次数

        Returns:
            近似根

        Raises:
            RuntimeError: 不收敛或导数为零
        """
        x = x0
        for _ in range(max_iter):
            fx = f(x)
            if abs(fx) < tol:
                return x
            dfx = df(x)
            if abs(dfx) < 1e-15:
                raise RuntimeError(f"导数为零, 牛顿法停滞: f'({x}) = {dfx}")
            x = x - fx / dfx
        raise RuntimeError(f"牛顿法在 {max_iter} 次迭代后未收敛, 当前 x={x}, f(x)={f(x)}")

    @staticmethod
    def find_root_secant(
        f: Callable[[float], float],
        x0: float,
        x1: float,
        tol: float = 1e-8,
        max_iter: int = 100
    ) -> float:
        """割线法求根 (无需导数, 用差商近似)。

        适用场景: 导数难以计算或计算成本高。
        收敛速度: 超线性 (≈ 1.618), 低于牛顿法的二次收敛。

        x_{n+1} = x_n - f(x_n) * (x_n - x_{n-1}) / (f(x_n) - f(x_{n-1}))
        """
        f0, f1 = f(x0), f(x1)
        for _ in range(max_iter):
            if abs(f1) < tol:
                return x1
            denom = f1 - f0
            if abs(denom) < 1e-15:
                raise RuntimeError("割线法分母为零, 无法继续")
            x2 = x1 - f1 * (x1 - x0) / denom
            x0, x1 = x1, x2
            f0, f1 = f1, f(x2)
        raise RuntimeError(f"割线法在 {max_iter} 次迭代后未收敛")


# ===========================================================================
# GradientDescent — 梯度下降优化器
# ===========================================================================

class GradientDescent:
    """梯度下降优化器家族。

    支持:
      - SGD (随机梯度下降, 含 momentum)
      - RMSProp (自适应学习率)
      - Adam (自适应矩估计, 默认推荐)

    Example:
        >>> # 最小化 f(x) = (x-3)^2, 最优解 x=3
        >>> f = lambda x: (x - 3) ** 2
        >>> grad = lambda x: 2 * (x - 3)
        >>> gd = GradientDescent(lr=0.1)
        >>> x = gd.optimize_sgd(f, grad, x0=0.0, n_iter=50)
        >>> abs(x - 3) < 0.001  # True
    """

    def __init__(self, lr: float = 0.01):
        self._lr = lr

    def optimize_sgd(
        self,
        f: Callable[[list[float]], float],
        grad: Callable[[list[float]], list[float]],
        x0: list[float],
        n_iter: int = 100,
        momentum: float = 0.0,
        tol: float = 1e-6
    ) -> list[float]:
        """SGD + 动量。

        Args:
            f: 目标函数
            grad: 梯度函数
            x0: 初始点
            n_iter: 迭代次数
            momentum: 动量系数 (0 = 纯 SGD, 0.9 = 典型动量)
            tol: 梯度范数收敛阈值

        Returns:
            优化后的参数
        """
        x = list(x0)
        v = [0.0] * len(x)
        for _ in range(n_iter):
            g = grad(x)
            # 收敛检查
            g_norm = math.sqrt(sum(gi * gi for gi in g))
            if g_norm < tol:
                break
            for i in range(len(x)):
                v[i] = momentum * v[i] + self._lr * g[i]
                x[i] -= v[i]
        return x

    def optimize_adam(
        self,
        f: Callable[[list[float]], float],
        grad: Callable[[list[float]], list[float]],
        x0: list[float],
        n_iter: int = 100,
        beta1: float = 0.9,
        beta2: float = 0.999,
        eps: float = 1e-8,
        tol: float = 1e-6
    ) -> list[float]:
        """Adam 优化器。

        原理:
          m_t = β1*m_{t-1} + (1-β1)*g_t       (一阶矩估计, 动量)
          v_t = β2*v_{t-1} + (1-β2)*g_t^2     (二阶矩估计, RMSProp)
          m̂_t = m_t / (1-β1^t)                (偏差修正)
          v̂_t = v_t / (1-β2^t)
          x_t = x_{t-1} - lr * m̂_t / (√v̂_t + ε)

        复杂度: 每步 O(d)  (d = 参数维度)
        """
        x = list(x0)
        d = len(x)
        m = [0.0] * d
        v = [0.0] * d
        beta1_pow = 1.0
        beta2_pow = 1.0
        for _ in range(n_iter):
            g = grad(x)
            g_norm = math.sqrt(sum(gi * gi for gi in g))
            if g_norm < tol:
                break
            beta1_pow *= beta1
            beta2_pow *= beta2
            for i in range(d):
                m[i] = beta1 * m[i] + (1 - beta1) * g[i]
                v[i] = beta2 * v[i] + (1 - beta2) * g[i] * g[i]
                m_hat = m[i] / (1 - beta1_pow)
                v_hat = v[i] / (1 - beta2_pow)
                x[i] -= self._lr * m_hat / (math.sqrt(v_hat) + eps)
        return x

    def optimize_rmsprop(
        self,
        f: Callable[[list[float]], float],
        grad: Callable[[list[float]], list[float]],
        x0: list[float],
        n_iter: int = 100,
        decay: float = 0.9,
        eps: float = 1e-8,
        tol: float = 1e-6
    ) -> list[float]:
        """RMSProp 优化器 (自适应学习率, 适合非平稳目标)。"""
        x = list(x0)
        d = len(x)
        cache = [0.0] * d
        for _ in range(n_iter):
            g = grad(x)
            g_norm = math.sqrt(sum(gi * gi for gi in g))
            if g_norm < tol:
                break
            for i in range(d):
                cache[i] = decay * cache[i] + (1 - decay) * g[i] * g[i]
                x[i] -= self._lr * g[i] / (math.sqrt(cache[i]) + eps)
        return x


# ===========================================================================
# Interpolation — 插值方法
# ===========================================================================

class Interpolation:
    """插值方法: 用已知数据点估算中间值。

    Example:
        >>> xs = [0, 1, 2]
        >>> ys = [0, 2, 6]
        >>> Interpolation.linear(xs, ys, 1.5)  # ≈ 4.0
    """

    @staticmethod
    def linear(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
        """线性插值: 在相邻两点间线性估算。

        复杂度: O(log n) 二分查找 + O(1) 计算

        要求: xs 必须单调递增, len(xs) == len(ys) >= 2
        """
        import bisect
        n = len(xs)
        if n < 2:
            raise ValueError(f"至少需要 2 个点, 当前 {n}")
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_right(xs, x) - 1
        if i < 0:
            i = 0
        t = (x - xs[i]) / (xs[i + 1] - xs[i])
        return ys[i] + t * (ys[i + 1] - ys[i])

    @staticmethod
    def lagrange(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
        """拉格朗日多项式插值。

        复杂度: O(n^2)  (n = 点数, 不建议 n > 10)
        """
        n = len(xs)
        if n < 2:
            raise ValueError(f"至少需要 2 个点, 当前 {n}")
        result = 0.0
        for i in range(n):
            term = ys[i]
            for j in range(n):
                if i != j:
                    term *= (x - xs[j]) / (xs[i] - xs[j])
            result += term
        return result

    @staticmethod
    def cubic_spline(
        xs: Sequence[float],
        ys: Sequence[float],
        x: float
    ) -> float:
        """三次样条插值 (自然边界条件: 二阶导端点为零)。

        复杂度: 预处理 O(n), 每次查询 O(log n)
        """
        import bisect
        n = len(xs)
        if n < 3:
            # 退化为线性
            return Interpolation.linear(xs, ys, x)
        # 构建三对角矩阵解算二阶导数
        h = [xs[i + 1] - xs[i] for i in range(n - 1)]
        alpha = [0.0] * n
        for i in range(1, n - 1):
            alpha[i] = 3 * (ys[i + 1] - ys[i]) / h[i] - 3 * (ys[i] - ys[i - 1]) / h[i - 1]
        # Thomas 算法
        l = [1.0] * n
        mu = [0.0] * n
        z = [0.0] * n
        for i in range(1, n - 1):
            l[i] = 2 * (xs[i + 1] - xs[i - 1]) - h[i - 1] * mu[i - 1]
            mu[i] = h[i] / l[i]
            z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]
        # 二阶导数
        c = [0.0] * n
        for i in range(n - 2, -1, -1):
            c[i] = z[i] - mu[i] * c[i + 1]
        # 查询
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_right(xs, x) - 1
        if i < 0:
            i = 0
        if i >= n - 1:
            i = n - 2
        dx = xs[i + 1] - xs[i]
        a = (xs[i + 1] - x) / dx
        b = (x - xs[i]) / dx
        return (
            a * ys[i] + b * ys[i + 1]
            + ((a**3 - a) * c[i] + (b**3 - b) * c[i + 1]) * dx * dx / 6
        )


# ===========================================================================
# Integration — 数值积分
# ===========================================================================

class Integration:
    """数值积分方法。

    Example:
        >>> f = lambda x: x**2
        >>> Integration.trapezoidal(f, 0, 1, n=1000)  # ≈ 1/3
    """

    @staticmethod
    def trapezoidal(
        f: Callable[[float], float],
        a: float,
        b: float,
        n: int = 1000
    ) -> float:
        """复合梯形法则。

        误差: O(h^2), h = (b-a)/n
        """
        if n <= 0:
            raise ValueError(f"n 必须为正: {n}")
        if a == b:
            return 0.0
        h = (b - a) / n
        total = (f(a) + f(b)) / 2.0
        for i in range(1, n):
            total += f(a + i * h)
        return total * h

    @staticmethod
    def simpson(
        f: Callable[[float], float],
        a: float,
        b: float,
        n: int = 1000
    ) -> float:
        """复合辛普森法则 (n 必须为偶数)。

        误差: O(h^4)
        """
        if n <= 0:
            raise ValueError(f"n 必须为正: {n}")
        if n % 2 != 0:
            n += 1  # 强制偶数
        if a == b:
            return 0.0
        h = (b - a) / n
        total = f(a) + f(b)
        for i in range(1, n, 2):
            total += 4 * f(a + i * h)
        for i in range(2, n - 1, 2):
            total += 2 * f(a + i * h)
        return total * h / 3.0

    @staticmethod
    def gauss_legendre(
        f: Callable[[float], float],
        a: float,
        b: float,
        n: int = 5
    ) -> float:
        """高斯-勒让德积分 (n 点, n <= 5)。

        高精度低点数: 3 点足以精确积分 5 次多项式。
        复杂度: O(n) 求值
        """
        if a == b:
            return 0.0
        # 预计算的高斯点 (n=1..5)
        _nodes = {
            1: ([0.0], [2.0]),
            2: ([-0.5773502691896257, 0.5773502691896257], [1.0, 1.0]),
            3: (
                [-0.7745966692414834, 0.0, 0.7745966692414834],
                [0.5555555555555556, 0.8888888888888888, 0.5555555555555556]
            ),
            4: (
                [-0.8611363115940526, -0.3399810435848563, 0.3399810435848563, 0.8611363115940526],
                [0.3478548451374538, 0.6521451548625461, 0.6521451548625461, 0.3478548451374538]
            ),
            5: (
                [-0.9061798459386640, -0.5384693101056831, 0.0, 0.5384693101056831, 0.9061798459386640],
                [0.2369268850561891, 0.4786286704993665, 0.5688888888888889, 0.4786286704993665, 0.2369268850561891]
            ),
        }
        if n < 1 or n > 5:
            raise ValueError(f"n 必须在 [1, 5]: {n}")
        nodes, weights = _nodes[n]
        mid = (b + a) / 2.0
        half = (b - a) / 2.0
        total = 0.0
        for xi, wi in zip(nodes, weights):
            total += wi * f(mid + half * xi)
        return total * half


# ===========================================================================
# RootFinding — 通用求根
# ===========================================================================

class RootFinding:
    """通用求根方法 (不需要导数)。

    Example:
        >>> f = lambda x: x**3 - x - 2
        >>> RootFinding.bisect(f, 1, 2)  # ≈ 1.521...
    """

    @staticmethod
    def bisect(
        f: Callable[[float], float],
        a: float,
        b: float,
        tol: float = 1e-8,
        max_iter: int = 100
    ) -> float:
        """二分法求根: 保证收敛 (f(a) 和 f(b) 符号相反)。

        收敛: 线性, 每次迭代区间减半。
        """
        fa, fb = f(a), f(b)
        if fa * fb > 0:
            raise ValueError(f"f(a) 和 f(b) 符号相同: f({a})={fa}, f({b})={fb}")
        if abs(fa) < tol:
            return a
        if abs(fb) < tol:
            return b
        for _ in range(max_iter):
            c = (a + b) / 2.0
            fc = f(c)
            if abs(fc) < tol or abs(b - a) < tol:
                return c
            if fa * fc < 0:
                b, fb = c, fc
            else:
                a, fa = c, fc
        return (a + b) / 2.0

    @staticmethod
    def brent(
        f: Callable[[float], float],
        a: float,
        b: float,
        tol: float = 1e-8,
        max_iter: int = 100
    ) -> float:
        """Brent 方法: 组合二分法+割线法+逆二次插值, 鲁棒且快速。

        收敛: 超线性 (通常比二分法快 10x)
        """
        fa, fb = f(a), f(b)
        if fa * fb > 0:
            raise ValueError(f"f(a) 和 f(b) 符号相同: f({a})={fa}, f({b})={fb}")
        if abs(fa) < abs(fb):
            a, b = b, a
            fa, fb = fb, fa
        c = a
        fc = fa
        mflag = True
        for _ in range(max_iter):
            if abs(b - a) < tol:
                return b
            if fb != fc and fa != fc:
                # 逆二次插值
                s = (a * fb * fc / ((fa - fb) * (fa - fc))
                     + b * fa * fc / ((fb - fa) * (fb - fc))
                     + c * fa * fb / ((fc - fa) * (fc - fb)))
            else:
                # 割线法
                s = b - fb * (b - a) / (fb - fa)
            # 检查是否接受插值
            cond1 = not ((3 * a + b) / 4 <= s <= b)
            cond2 = mflag and abs(s - b) >= abs(b - c) / 2
            cond3 = (not mflag) and abs(s - b) >= abs(c - d_prev) / 2 if '_d_prev' in dir() else False
            if cond1 or cond2 or cond3:
                s = (a + b) / 2
                mflag = True
            else:
                mflag = False
            d_prev = c
            c = b
            fc = fb
            fs = f(s)
            if abs(fs) < tol:
                return s
            if fa * fs < 0:
                b = s
                fb = fs
            else:
                a = s
                fa = fs
            if abs(fa) < abs(fb):
                a, b = b, a
                fa, fb = fb, fa
        return b


# ===========================================================================
# MatrixOps — 矩阵运算
# ===========================================================================

class MatrixOps:
    """基本矩阵运算, 纯 Python 实现。

    适用场景: 小到中等矩阵 (n < 100), 大矩阵用 numpy/scipy。
    """

    @staticmethod
    def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
        """矩阵乘法: C = A @ B,  O(n*m*p)。"""
        if not a or not b:
            raise ValueError("矩阵不能为空")
        if not a[0] or not b[0]:
            raise ValueError("矩阵不能有空行")
        ra, ca = len(a), len(a[0])
        rb, cb = len(b), len(b[0])
        if ca != rb:
            raise ValueError(f"维度不匹配: ({ra},{ca}) @ ({rb},{cb})")
        result = [[0.0] * cb for _ in range(ra)]
        for i in range(ra):
            a_row = a[i]
            res_row = result[i]
            for k in range(ca):
                aik = a_row[k]
                if aik == 0.0:
                    continue
                b_row = b[k]
                for j in range(cb):
                    res_row[j] += aik * b_row[j]
        return result

    @staticmethod
    def transpose(m: list[list[float]]) -> list[list[float]]:
        """矩阵转置: O(r*c)。"""
        if not m or not m[0]:
            return [[]] if m else []
        return [[m[i][j] for i in range(len(m))] for j in range(len(m[0]))]

    @staticmethod
    def identity(n: int) -> list[list[float]]:
        """n×n 单位矩阵。"""
        result = [[0.0] * n for _ in range(n)]
        for i in range(n):
            result[i][i] = 1.0
        return result

    @staticmethod
    def determinant(m: list[list[float]]) -> float:
        """行列式 (LU 分解法), O(n^3)。"""
        n = len(m)
        if n == 0:
            return 1.0
        if n == 1:
            return m[0][0]
        if n == 2:
            return m[0][0] * m[1][1] - m[0][1] * m[1][0]
        # LU 分解
        lu = [row[:] for row in m]
        det = 1.0
        for i in range(n):
            # 选主元
            pivot = abs(lu[i][i])
            pivot_row = i
            for k in range(i + 1, n):
                if abs(lu[k][i]) > pivot:
                    pivot = abs(lu[k][i])
                    pivot_row = k
            if pivot < 1e-15:
                return 0.0
            if pivot_row != i:
                lu[i], lu[pivot_row] = lu[pivot_row], lu[i]
                det = -det
            det *= lu[i][i]
            for j in range(i + 1, n):
                lu[i][j] /= lu[i][i]
            for j in range(i + 1, n):
                for k in range(i + 1, n):
                    lu[j][k] -= lu[j][i] * lu[i][k]
        return det

    @staticmethod
    def inverse(m: list[list[float]]) -> list[list[float]]:
        """矩阵求逆 (高斯-若尔当消元), O(n^3)。

        Raises:
            ValueError: 矩阵奇异
        """
        n = len(m)
        if n == 0:
            return []
        # 增广矩阵 [A|I]
        aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
        for col in range(n):
            # 选主元
            pivot = abs(aug[col][col])
            pivot_row = col
            for row in range(col + 1, n):
                if abs(aug[row][col]) > pivot:
                    pivot = abs(aug[row][col])
                    pivot_row = row
            if pivot < 1e-15:
                raise ValueError("矩阵奇异, 无法求逆")
            if pivot_row != col:
                aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
            # 归一化主元行
            pivot_val = aug[col][col]
            for j in range(2 * n):
                aug[col][j] /= pivot_val
            # 消去其他行
            for row in range(n):
                if row == col:
                    continue
                factor = aug[row][col]
                for j in range(2 * n):
                    aug[row][j] -= factor * aug[col][j]
        return [row[n:] for row in aug]

    @staticmethod
    def solve(a: list[list[float]], b: list[float]) -> list[float]:
        """解线性方程组 Ax = b (高斯消元), O(n^3)。"""
        return [sum(a_inv[i][j] * b[j] for j in range(len(b)))
                for i, a_inv in enumerate(MatrixOps.inverse(a))]


# ===========================================================================
# OnlineStatistics — 在线统计
# ===========================================================================

class OnlineStatistics:
    """在线统计算法 (Welford 方法), 单次遍历, O(1) 更新。

    适用场景: 流式数据, 不知道总数据量时计算方差/标准差。

    Example:
        >>> stats = OnlineStatistics()
        >>> for x in [1, 2, 3, 4, 5]:
        ...     stats.update(x)
        >>> stats.mean  # 3.0
        >>> stats.std   # ≈ 1.581
    """

    def __init__(self):
        self._count = 0
        self._mean = 0.0
        self._m2 = 0.0   # 二阶中心矩的 (n-1) 倍和
        self._min = float("inf")
        self._max = float("-inf")

    def update(self, x: float) -> None:
        """Welford 在线方差更新。"""
        self._count += 1
        delta = x - self._mean
        self._mean += delta / self._count
        delta2 = x - self._mean
        self._m2 += delta * delta2
        if x < self._min:
            self._min = x
        if x > self._max:
            self._max = x

    def merge(self, other: OnlineStatistics) -> OnlineStatistics:
        """合并两个在线统计量 (并行归约)。"""
        if other._count == 0:
            return self
        if self._count == 0:
            self._count = other._count
            self._mean = other._mean
            self._m2 = other._m2
            self._min = other._min
            self._max = other._max
            return self
        total = self._count + other._count
        delta = other._mean - self._mean
        self._m2 = (self._m2 + other._m2
                    + delta * delta * self._count * other._count / total)
        self._mean = (self._count * self._mean + other._count * other._mean) / total
        self._count = total
        self._min = min(self._min, other._min)
        self._max = max(self._max, other._max)
        return self

    @property
    def mean(self) -> float:
        if self._count == 0:
            return 0.0
        return self._mean

    @property
    def variance(self) -> float:
        """总体方差 (除以 n)。"""
        if self._count < 1:
            return 0.0
        return self._m2 / self._count

    @property
    def sample_variance(self) -> float:
        """样本方差 (除以 n-1)。"""
        if self._count < 2:
            return 0.0
        return self._m2 / (self._count - 1)

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    @property
    def sample_std(self) -> float:
        return math.sqrt(self.sample_variance)

    @property
    def count(self) -> int:
        return self._count

    @property
    def min(self) -> float:
        return self._min if self._count > 0 else float("nan")

    @property
    def max(self) -> float:
        return self._max if self._count > 0 else float("nan")


# ===========================================================================
# OnlineCovariance — 在线协方差/相关系数
# ===========================================================================

class OnlineCovariance:
    """在线协方差和 Pearson 相关系数 (并行 Welford 扩展)。

    Example:
        >>> cov = OnlineCovariance()
        >>> for x, y in [(1, 2), (2, 4), (3, 6)]:
        ...     cov.update(x, y)
        >>> cov.pearson  # 1.0 (完全正相关)
    """

    def __init__(self):
        self._count = 0
        self._mean_x = 0.0
        self._mean_y = 0.0
        self._c = 0.0  # 协方差累加量
        self._m2_x = 0.0
        self._m2_y = 0.0

    def update(self, x: float, y: float) -> None:
        self._count += 1
        dx = x - self._mean_x
        dy = y - self._mean_y
        self._mean_x += dx / self._count
        self._mean_y += dy / self._count
        self._c += dx * (y - self._mean_y)
        self._m2_x += dx * (x - self._mean_x)
        self._m2_y += dy * (y - self._mean_y)

    @property
    def covariance(self) -> float:
        """总体协方差。"""
        if self._count < 1:
            return 0.0
        return self._c / self._count

    @property
    def sample_covariance(self) -> float:
        """样本协方差 (除以 n-1)。"""
        if self._count < 2:
            return 0.0
        return self._c / (self._count - 1)

    @property
    def pearson(self) -> float:
        """Pearson 相关系数。"""
        if self._m2_x < 1e-15 or self._m2_y < 1e-15:
            return 0.0
        return self._c / math.sqrt(self._m2_x * self._m2_y)

    @property
    def count(self) -> int:
        return self._count


# ===========================================================================
# QuantileEstimator — 在线分位数估算
# ===========================================================================

class QuantileEstimator:
    """在线分位数估算 (P² 算法), O(1) 更新, O(1) 查询。

    适用场景: 流式数据的 p50/p90/p95/p99 延迟监控。
    限制: 单分位数, 若需多分位数请创建多个实例。

    Example:
        >>> q = QuantileEstimator(0.5)  # 中位数
        >>> for x in [3, 1, 4, 1, 5, 9, 2, 6]:
        ...     q.update(x)
        >>> q.quantile  # ≈ 3.5
    """

    def __init__(self, p: float):
        if not (0 < p < 1):
            raise ValueError(f"p 必须在 (0, 1): {p}")
        self._p = p
        self._n = 0
        self._q: list[float] = []  # 5 个标记点
        self._ns: list[float] = []
        self._dns: list[float] = []

    def update(self, x: float) -> None:
        self._n += 1
        if self._n <= 5:
            # 前 5 个点直接插入排序
            self._q.append(x)
            self._q.sort()
            if self._n == 5:
                self._ns = [1.0, 1 + 2 * self._p, 1 + 4 * self._p, 3 + 2 * self._p, 5.0]
                self._dns = [0.0, self._p / 2, self._p, (1 + self._p) / 2, 1.0]
            return
        # 找到 x 所属区间
        k = 0
        if x < self._q[0]:
            self._q[0] = x
            k = 0
        elif x >= self._q[4]:
            self._q[4] = x
            k = 3
        else:
            for i in range(4):
                if self._q[i] <= x < self._q[i + 1]:
                    k = i
                    break
        # 更新 ns 和 dns
        for i in range(k + 1, 5):
            self._ns[i] += 1
        for i in range(5):
            self._dns[i] = self._ns[i] * self._p + (i - self._ns[i]) * (1 - self._p) if __debug__ else 0.0
        # 调整标记点
        for i in range(1, 4):
            d = self._ns[i] - self._dns[i]
            if (d >= 1 and self._ns[i + 1] - self._ns[i] > 1) or (d <= -1 and self._ns[i] - self._ns[i - 1] > 1):
                d_sign = 1 if d >= 0 else -1
                qs = self._parabolic(i, d_sign)
                if self._q[i - 1] < qs < self._q[i + 1]:
                    self._q[i] = qs
                else:
                    self._q[i] = self._linear(i, d_sign)
                self._ns[i] += d_sign
        # 更新 dns
        for i in range(5):
            self._dns[i] = self._ns[i] * self._p + (i - self._ns[i]) * (1 - self._p)

    def _parabolic(self, i: int, d: int) -> float:
        q = self._q
        n = self._ns
        return (q[i]
                + d / (n[i + 1] - n[i - 1])
                * ((n[i] - n[i - 1] + d) * (q[i + 1] - q[i]) / (n[i + 1] - n[i])
                   + (n[i + 1] - n[i] - d) * (q[i] - q[i - 1]) / (n[i] - n[i - 1])))

    def _linear(self, i: int, d: int) -> float:
        q = self._q
        n = self._ns
        if d > 0:
            return q[i] + d * (q[i + 1] - q[i]) / (n[i + 1] - n[i])
        else:
            return q[i] + d * (q[i] - q[i - 1]) / (n[i] - n[i - 1])

    @property
    def quantile(self) -> float:
        if self._n == 0:
            return float("nan")
        if self._n <= 5:
            # 线性插值
            pos = self._p * (self._n - 1)
            lo = int(pos)
            hi = min(lo + 1, self._n - 1)
            frac = pos - lo
            return self._q[lo] + frac * (self._q[hi] - self._q[lo])
        return self._q[2]

    @property
    def count(self) -> int:
        return self._n