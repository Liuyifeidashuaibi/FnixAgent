"""
信息论 (Information Theory)
==============================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  Entropy          - Shannon 熵 / 条件熵 / 联合熵
  KLDivergence     - KL 散度 (相对熵)
  CrossEntropy     - 交叉熵
  MutualInformation - 互信息
  InformationGain  - 信息增益 (决策树分裂准则)
  ChannelCapacity  - 信道容量
  DataProcessing   - 数据处理不等式验证
  RateDistortion   - 率失真理论
  SourceCoding     - 香农信源编码定理
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Sequence


# ===========================================================================
# Entropy — 熵
# ===========================================================================

class Entropy:
    """Shannon 熵及相关信息度量。

    Example:
        >>> Entropy.shannon([0.5, 0.5])      # 1.0 bit
        >>> Entropy.shannon([1.0, 0.0])       # 0.0 bit (确定)
        >>> Entropy.shannon([0.25]*4)         # 2.0 bits
    """

    @staticmethod
    def shannon(probs: Sequence[float], base: float = 2.0) -> float:
        """Shannon 熵: H(X) = -Σ p(x) * log p(x)。

        Args:
            probs: 概率分布 (和为 1)
            base: 对数底 (2=bits, e=nats, 10=dits)

        Returns:
            熵值
        """
        if not probs:
            return 0.0
        log_base = math.log(base)
        h = 0.0
        for p in probs:
            if p > 1e-15:
                h -= p * math.log(p) / log_base
        return h

    @staticmethod
    def shannon_from_counts(
        counts: Sequence[int], base: float = 2.0
    ) -> float:
        """从计数序列计算熵。"""
        total = sum(counts)
        if total == 0:
            return 0.0
        probs = [c / total for c in counts if c > 0]
        return Entropy.shannon(probs, base)

    @staticmethod
    def shannon_from_data(
        data: Iterable, base: float = 2.0
    ) -> float:
        """从数据序列估计熵 (经验分布)。"""
        counts = Counter(data)
        total = sum(counts.values())
        if total == 0:
            return 0.0
        probs = [c / total for c in counts.values()]
        return Entropy.shannon(probs, base)

    @staticmethod
    def joint(
        joint_probs: list[list[float]], base: float = 2.0
    ) -> float:
        """联合熵: H(X,Y) = -ΣΣ p(x,y) * log p(x,y)。

        Args:
            joint_probs: 联合概率矩阵 P[X][Y]

        Returns:
            联合熵
        """
        h = 0.0
        log_base = math.log(base)
        for row in joint_probs:
            for p in row:
                if p > 1e-15:
                    h -= p * math.log(p) / log_base
        return h

    @staticmethod
    def conditional(
        joint_probs: list[list[float]],
        marginal_y: list[float],
        base: float = 2.0,
    ) -> float:
        """条件熵: H(X|Y) = Σ_y p(y) * H(X|Y=y)。

        等价: H(X|Y) = H(X,Y) - H(Y)

        Args:
            joint_probs: P(X=x, Y=y) 联合概率矩阵
            marginal_y: P(Y=y) 边缘概率

        Returns:
            条件熵
        """
        h_y = Entropy.shannon(marginal_y, base)
        h_xy = Entropy.joint(joint_probs, base)
        return h_xy - h_y

    @staticmethod
    def renyi(
        probs: Sequence[float], alpha: float, base: float = 2.0
    ) -> float:
        """Rényi 熵 (α 阶广义熵)。

        H_α(X) = (1/(1-α)) * log(Σ p(x)^α)

        特例:
          α=0 → Hartley 熵 (log |X|)
          α=1 → Shannon 熵 (极限)
          α=2 → 碰撞熵
          α→∞ → min-entropy
        """
        if abs(alpha - 1.0) < 1e-10:
            return Entropy.shannon(probs, base)
        if alpha < 0:
            raise ValueError(f"alpha 必须 >= 0: {alpha}")
        log_base = math.log(base)
        s = sum(p ** alpha for p in probs if p > 1e-15)
        if s < 1e-15:
            return 0.0
        return math.log(s) / ((1 - alpha) * log_base)

    @staticmethod
    def min_entropy(probs: Sequence[float], base: float = 2.0) -> float:
        """最小熵: H_∞(X) = -log max(p(x))。

        密码学中常用, 表示单次猜测的最大成功率。
        """
        if not probs:
            return 0.0
        p_max = max(probs)
        if p_max < 1e-15:
            return 0.0
        return -math.log(p_max) / math.log(base)


# ===========================================================================
# KLDivergence — KL 散度
# ===========================================================================

class KLDivergence:
    """KL 散度 (相对熵): 衡量两个分布的差异。

    性质:
      - D(P||Q) ≥ 0 (Gibbs 不等式)
      - D(P||Q) = 0 ⟺ P = Q
      - 不对称: D(P||Q) ≠ D(Q||P)
      - 非度量: 不满足三角不等式

    Example:
        >>> P = [0.5, 0.5]
        >>> Q = [0.9, 0.1]
        >>> KLDivergence.kl(P, Q)  # 0.368 bits
    """

    @staticmethod
    def kl(
        p: Sequence[float],
        q: Sequence[float],
        base: float = 2.0,
    ) -> float:
        """KL 散度: D(P||Q) = Σ p(x) * log(p(x)/q(x))。

        Args:
            p: 真实分布 P
            q: 近似分布 Q
            base: 对数底

        Returns:
            D(P||Q) ≥ 0
        """
        if len(p) != len(q):
            raise ValueError(f"分布长度不一致: len(p)={len(p)}, len(q)={len(q)}")
        log_base = math.log(base)
        d = 0.0
        for pi, qi in zip(p, q):
            if pi > 1e-15:
                if qi < 1e-15:
                    return float("inf")  # P 有而 Q 无 → 无穷大
                d += pi * math.log(pi / qi) / log_base
        return d

    @staticmethod
    def symmetric(
        p: Sequence[float],
        q: Sequence[float],
        base: float = 2.0,
    ) -> float:
        """对称 KL 散度 (Jeffreys 散度): D_sym = (D(P||Q) + D(Q||P)) / 2。"""
        return (
            KLDivergence.kl(p, q, base) + KLDivergence.kl(q, p, base)
        ) / 2.0

    @staticmethod
    def jensen_shannon(
        p: Sequence[float],
        q: Sequence[float],
        base: float = 2.0,
    ) -> float:
        """Jensen-Shannon 散度: 对称且有界的 KL 散度变体。

        JSD(P||Q) = (D(P||M) + D(Q||M)) / 2, M = (P+Q)/2

        性质:
          - 对称: JSD(P||Q) = JSD(Q||P)
          - 有界: 0 ≤ JSD ≤ log(2) (以 2 为底时 ≤ 1 bit)
          - 是度量: 满足三角不等式
          - JSD 的平方根是合法距离度量

        Returns:
            JSD 值
        """
        if len(p) != len(q):
            raise ValueError("分布长度不一致")
        m = [(pi + qi) / 2.0 for pi, qi in zip(p, q)]
        return (
            KLDivergence.kl(p, m, base) + KLDivergence.kl(q, m, base)
        ) / 2.0

    @staticmethod
    def js_distance(
        p: Sequence[float],
        q: Sequence[float],
        base: float = 2.0,
    ) -> float:
        """Jensen-Shannon 距离: sqrt(JSD)。

        这是合法的度量 (满足三角不等式)。
        """
        return math.sqrt(KLDivergence.jensen_shannon(p, q, base))


# ===========================================================================
# CrossEntropy — 交叉熵
# ===========================================================================

class CrossEntropy:
    """交叉熵: 机器学习损失函数的核心。

    H(P, Q) = -Σ p(x) * log q(x) = H(P) + D(P||Q)

    Example:
        >>> # 二分类: 真实标签 1, 预测概率 0.8
        >>> CrossEntropy.binary(1, 0.8)  # 0.322...
    """

    @staticmethod
    def cross(
        p: Sequence[float],
        q: Sequence[float],
        base: float = 2.0,
    ) -> float:
        """交叉熵: H(P, Q) = -Σ p(x) * log q(x)。

        Args:
            p: 真实分布
            q: 预测分布
            base: 对数底

        Returns:
            交叉熵
        """
        if len(p) != len(q):
            raise ValueError("分布长度不一致")
        log_base = math.log(base)
        h = 0.0
        for pi, qi in zip(p, q):
            if pi > 1e-15:
                if qi < 1e-15:
                    return float("inf")
                h -= pi * math.log(qi) / log_base
        return h

    @staticmethod
    def binary(label: int, pred: float, base: float = math.e) -> float:
        """二分类交叉熵 (二元交叉熵)。

        H = -(y * log(p) + (1-y) * log(1-p))

        Args:
            label: 真实标签 (0 或 1)
            pred: 预测概率 (0, 1)
            base: 对数底 (默认 e → nats)

        Returns:
            交叉熵损失
        """
        if not (0 < pred < 1):
            # 边界处理
            if pred <= 0:
                pred = 1e-15
            elif pred >= 1:
                pred = 1 - 1e-15
        log_base = math.log(base)
        if label == 1:
            return -math.log(pred) / log_base
        else:
            return -math.log(1 - pred) / log_base

    @staticmethod
    def categorical(
        labels: Sequence[int],
        predictions: Sequence[Sequence[float]],
        base: float = math.e,
    ) -> float:
        """多分类交叉熵。

        Args:
            labels: 真实标签索引列表 (如 [0, 2, 1])
            predictions: 预测概率分布列表 (每个是各类概率)

        Returns:
            平均交叉熵损失
        """
        if len(labels) != len(predictions):
            raise ValueError("labels 和 predictions 长度不一致")
        log_base = math.log(base)
        total = 0.0
        for label, pred in zip(labels, predictions):
            p = pred[label]
            if p < 1e-15:
                p = 1e-15
            total -= math.log(p) / log_base
        return total / len(labels)


# ===========================================================================
# MutualInformation — 互信息
# ===========================================================================

class MutualInformation:
    """互信息: 两个随机变量的相互依赖程度。

    I(X;Y) = H(X) - H(X|Y) = H(Y) - H(Y|X) = H(X) + H(Y) - H(X,Y)

    性质:
      - I(X;Y) ≥ 0 (当且仅当 X,Y 独立时为 0)
      - 对称: I(X;Y) = I(Y;X)
      - I(X;X) = H(X) (自信息 = 熵)

    Example:
        >>> # 完全相关: X=Y
        >>> joint = [[0.5, 0], [0, 0.5]]
        >>> MutualInformation.mutual(joint)  # 1.0 bit
    """

    @staticmethod
    def mutual(
        joint_probs: list[list[float]],
        base: float = 2.0,
    ) -> float:
        """互信息: I(X;Y) = ΣΣ p(x,y) * log(p(x,y) / (p(x)*p(y)))。

        Args:
            joint_probs: P(X=x, Y=y) 联合概率矩阵
            base: 对数底

        Returns:
            互信息
        """
        n_x = len(joint_probs)
        if n_x == 0:
            return 0.0
        n_y = len(joint_probs[0])
        # 边缘概率
        p_x = [sum(joint_probs[i]) for i in range(n_x)]
        p_y = [sum(joint_probs[i][j] for i in range(n_x)) for j in range(n_y)]
        log_base = math.log(base)
        mi = 0.0
        for i in range(n_x):
            for j in range(n_y):
                p_xy = joint_probs[i][j]
                if p_xy > 1e-15 and p_x[i] > 1e-15 and p_y[j] > 1e-15:
                    mi += p_xy * math.log(
                        p_xy / (p_x[i] * p_y[j])
                    ) / log_base
        return mi

    @staticmethod
    def normalized(
        joint_probs: list[list[float]],
        base: float = 2.0,
    ) -> float:
        """归一化互信息: NMI = I(X;Y) / sqrt(H(X) * H(Y))。

        值域 [0, 1], 1 = 完全相关。
        """
        n_x = len(joint_probs)
        if n_x == 0:
            return 0.0
        n_y = len(joint_probs[0])
        p_x = [sum(joint_probs[i]) for i in range(n_x)]
        p_y = [sum(joint_probs[i][j] for i in range(n_x)) for j in range(n_y)]
        h_x = Entropy.shannon(p_x, base)
        h_y = Entropy.shannon(p_y, base)
        if h_x < 1e-15 or h_y < 1e-15:
            return 0.0
        mi = MutualInformation.mutual(joint_probs, base)
        return mi / math.sqrt(h_x * h_y)

    @staticmethod
    def from_data(
        x: Sequence,
        y: Sequence,
        base: float = 2.0,
    ) -> float:
        """从配对数据序列估计互信息。

        Args:
            x: X 的观测序列
            y: Y 的观测序列 (等长)

        Returns:
            经验互信息
        """
        if len(x) != len(y):
            raise ValueError("x 和 y 长度不一致")
        n = len(x)
        if n == 0:
            return 0.0
        x_counts = Counter(x)
        y_counts = Counter(y)
        xy_counts = Counter(zip(x, y))
        log_base = math.log(base)
        mi = 0.0
        for (xi, yi), c_xy in xy_counts.items():
            p_xy = c_xy / n
            p_x = x_counts[xi] / n
            p_y = y_counts[yi] / n
            mi += p_xy * math.log(p_xy / (p_x * p_y)) / log_base
        return mi

    @staticmethod
    def conditional_mutual(
        joint_xyz: dict[tuple, float],
        base: float = 2.0,
    ) -> float:
        """条件互信息: I(X;Y|Z) = Σ p(x,y,z) * log(p(x,y|z) / (p(x|z)*p(y|z)))。

        Args:
            joint_xyz: {(x, y, z): probability} 联合概率
            base: 对数底

        Returns:
            条件互信息
        """
        # 计算 p(z) 和 p(x,y|z) 等
        p_z: dict = {}
        p_xz: dict = {}
        p_yz: dict = {}
        for (x, y, z), p in joint_xyz.items():
            p_z[z] = p_z.get(z, 0) + p
            p_xz[(x, z)] = p_xz.get((x, z), 0) + p
            p_yz[(y, z)] = p_yz.get((y, z), 0) + p
        log_base = math.log(base)
        cmi = 0.0
        for (x, y, z), p_xyz in joint_xyz.items():
            if p_xyz < 1e-15:
                continue
            pz = p_z.get(z, 0)
            pxz = p_xz.get((x, z), 0)
            pyz = p_yz.get((y, z), 0)
            if pz > 1e-15 and pxz > 1e-15 and pyz > 1e-15:
                # p(x,y|z) / (p(x|z) * p(y|z))
                ratio = (p_xyz * pz) / (pxz * pyz)
                cmi += p_xyz * math.log(ratio) / log_base
        return cmi


# ===========================================================================
# InformationGain — 信息增益
# ===========================================================================

class InformationGain:
    """信息增益: 决策树分裂准则。

    IG(X|A) = H(X) - H(X|A)

    Example:
        >>> # 特征 A 将数据分为两组
        >>> # 组 1: [0, 0, 1], 组 2: [1, 1, 1]
        >>> labels = [0, 0, 1, 1, 1, 1]
        >>> groups = [[0, 0, 1], [1, 1, 1]]
        >>> InformationGain.gain(labels, groups)
    """

    @staticmethod
    def gain(
        labels: Sequence,
        groups: list[Sequence],
        base: float = 2.0,
    ) -> float:
        """信息增益: H(原) - Σ (|组|/|总|) * H(组)。

        Args:
            labels: 原始标签序列
            groups: 分组后的标签列表
            base: 对数底

        Returns:
            信息增益
        """
        h_before = Entropy.shannon_from_data(labels, base)
        total = len(labels)
        if total == 0:
            return 0.0
        h_after = 0.0
        for group in groups:
            if len(group) == 0:
                continue
            weight = len(group) / total
            h_after += weight * Entropy.shannon_from_data(group, base)
        return h_before - h_after

    @staticmethod
    def gain_ratio(
        labels: Sequence,
        groups: list[Sequence],
        base: float = 2.0,
    ) -> float:
        """信息增益比 (C4.5 算法): GR = IG / SplitInfo。

        SplitInfo = -Σ (|组|/|总|) * log(|组|/|总|)
        修正信息增益对多值特征的偏好。
        """
        ig = InformationGain.gain(labels, groups, base)
        total = len(labels)
        if total == 0:
            return 0.0
        split_info = 0.0
        log_base = math.log(base)
        for group in groups:
            if len(group) == 0:
                continue
            ratio = len(group) / total
            split_info -= ratio * math.log(ratio) / log_base
        if split_info < 1e-15:
            return 0.0
        return ig / split_info

    @staticmethod
    def gini_index(labels: Sequence, base: float = 2.0) -> float:
        """Gini 不纯度 (CART 算法)。

        Gini = 1 - Σ p_i^2

        值域 [0, 1-1/k], 0 = 纯净。
        """
        counts = Counter(labels)
        total = sum(counts.values())
        if total == 0:
            return 0.0
        return 1.0 - sum((c / total) ** 2 for c in counts.values())


# ===========================================================================
# ChannelCapacity — 信道容量
# ===========================================================================

class ChannelCapacity:
    """信道容量: 信道能传输的最大信息率。

    C = max_{p(x)} I(X;Y)

    Example:
        >>> # 二元对称信道 (BSC), 翻转概率 0.1
        >>> # P(Y|X): P(0|0)=0.9, P(1|0)=0.1, P(0|1)=0.1, P(1|1)=0.9
        >>> channel = [[0.9, 0.1], [0.1, 0.9]]
        >>> ChannelCapacity.blahut_arimoto(channel)  # ≈ 0.531 bits
    """

    @staticmethod
    def blahut_arimoto(
        channel: list[list[float]],
        max_iter: int = 1000,
        tol: float = 1e-8,
        base: float = 2.0,
    ) -> float:
        """Blahut-Arimoto 算法: 迭代计算信道容量。

        Args:
            channel: 条件概率矩阵 P(Y|X), channel[x][y]
            max_iter: 最大迭代次数
            tol: 收敛容差
            base: 对数底

        Returns:
            信道容量 C
        """
        n_x = len(channel)
        if n_x == 0:
            return 0.0
        n_y = len(channel[0])
        # 初始均匀分布
        p_x = [1.0 / n_x] * n_x
        log_base = math.log(base)
        for _ in range(max_iter):
            # 计算 p(y) = Σ_x p(x) * p(y|x)
            p_y = [0.0] * n_y
            for x in range(n_x):
                for y in range(n_y):
                    p_y[y] += p_x[x] * channel[x][y]
            # 计算 I(X;Y)
            mi = 0.0
            for x in range(n_x):
                for y in range(n_y):
                    if channel[x][y] > 1e-15 and p_y[y] > 1e-15:
                        mi += p_x[x] * channel[x][y] * math.log(
                            channel[x][y] / p_y[y]
                        ) / log_base
            # 更新 p(x): p_new(x) ∝ p(x) * exp(Σ_y p(y|x) * log(p(y|x)/p(y)))
            p_new = [0.0] * n_x
            for x in range(n_x):
                exponent = 0.0
                for y in range(n_y):
                    if channel[x][y] > 1e-15 and p_y[y] > 1e-15:
                        exponent += channel[x][y] * math.log(
                            channel[x][y] / p_y[y]
                        ) / log_base
                p_new[x] = p_x[x] * (base ** exponent)
            # 归一化
            total = sum(p_new)
            if total < 1e-15:
                break
            p_new = [p / total for p in p_new]
            # 收敛检查
            diff = sum(abs(p_new[i] - p_x[i]) for i in range(n_x))
            p_x = p_new
            if diff < tol:
                break
        # 最终 I(X;Y)
        p_y = [0.0] * n_y
        for x in range(n_x):
            for y in range(n_y):
                p_y[y] += p_x[x] * channel[x][y]
        capacity = 0.0
        for x in range(n_x):
            for y in range(n_y):
                if channel[x][y] > 1e-15 and p_y[y] > 1e-15 and p_x[x] > 1e-15:
                    capacity += (
                        p_x[x] * channel[x][y]
                        * math.log(channel[x][y] / p_y[y]) / log_base
                    )
        return capacity


# ===========================================================================
# SourceCoding — 信源编码定理
# ===========================================================================

class SourceCoding:
    """香农信源编码定理: 平均码长下界 = 熵。

    Example:
        >>> # 码长验证: 平均码长 ≥ 熵
        >>> probs = [0.5, 0.25, 0.125, 0.125]
        >>> code_lengths = [1, 2, 3, 3]  # Huffman 码长
        >>> SourceCoding.avg_code_length(probs, code_lengths)  # 1.75
        >>> Entropy.shannon(probs)  # 1.75 (达到下界)
    """

    @staticmethod
    def avg_code_length(
        probs: Sequence[float],
        code_lengths: Sequence[int],
    ) -> float:
        """平均码长: L = Σ p(x) * l(x)。"""
        if len(probs) != len(code_lengths):
            raise ValueError("probs 和 code_lengths 长度不一致")
        return sum(p * l for p, l in zip(probs, code_lengths))

    @staticmethod
    def coding_efficiency(
        probs: Sequence[float],
        code_lengths: Sequence[int],
        base: float = 2.0,
    ) -> float:
        """编码效率: η = H(X) / L。

        η ≤ 1, 越接近 1 越好 (Huffman 编码 η ≥ 1 - 1/|X|)。
        """
        h = Entropy.shannon(probs, base)
        l = SourceCoding.avg_code_length(probs, code_lengths)
        if l < 1e-15:
            return 0.0
        return h / l

    @staticmethod
    def redundancy(
        probs: Sequence[float],
        code_lengths: Sequence[int],
        base: float = 2.0,
    ) -> float:
        """冗余度: R = L - H(X) ≥ 0。"""
        h = Entropy.shannon(probs, base)
        l = SourceCoding.avg_code_length(probs, code_lengths)
        return l - h

    @staticmethod
    def shannon_fano_code_lengths(
        probs: Sequence[float],
        base: float = 2.0,
    ) -> list[int]:
        """Shannon-Fano 码长: l(x) = ceil(log_base(1/p(x)))。"""
        log_base = math.log(base)
        lengths = []
        for p in probs:
            if p > 1e-15:
                l = math.ceil(-math.log(p) / log_base)
                lengths.append(max(1, l))
            else:
                lengths.append(1)
        return lengths
