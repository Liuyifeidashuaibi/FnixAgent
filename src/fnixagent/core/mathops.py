"""
向量数学运算库 (mathops)。

纯 Python + 标准库实现的核心数值算法,零外部依赖(不依赖 numpy),
用于 Embedding 后处理、相似度计算、归一化、降维等。
所有函数对 list[float] / list[list[float]] 操作,保证内核可独立分发。

性能说明: 对 1024 维向量, 纯 Python 实现单次点积 < 50us 可接受;
超大批量场景交由 embedder 层用 numpy 批处理。
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# 向量类型: 任何浮点序列(list/tuple 等)
Vector = Sequence[float]
# 矩阵类型: 向量序列
Matrix = Sequence[Sequence[float]]

# 浮点零阈值, 用于除零保护(避免零向量除零)
_EPSILON = 1e-12


# ===========================================================================
# 输入校验工具
# ===========================================================================


def _check_nonempty(a: Sequence[float], name: str = "vector") -> None:
    """校验向量非空, 空向量抛 ValueError。"""
    if a is None or len(a) == 0:
        raise ValueError(f"{name} 不能为空")


def _check_same_dim(a: Sequence[float], b: Sequence[float]) -> None:
    """校验两向量维度一致, 不一致抛 ValueError(防御性编程, 避免静默截断)。"""
    if len(a) != len(b):
        raise ValueError(f"向量维度不一致: len(a)={len(a)} vs len(b)={len(b)}")


# ===========================================================================
# 基础向量运算
# ===========================================================================


def dot(a: Vector, b: Vector) -> float:
    """点积: sum(a_i * b_i)。

    Args:
        a: 向量 A
        b: 向量 B(必须与 A 同维)

    Returns:
        点积值

    Raises:
        ValueError: 任一向量为空或维度不一致
    """
    _check_nonempty(a, "a")
    _check_nonempty(b, "b")
    _check_same_dim(a, b)
    # 单趟累加, O(n)
    return sum(x * y for x, y in zip(a, b))


def norm(a: Vector) -> float:
    """L2 范数: sqrt(sum(a_i^2))。

    Args:
        a: 向量

    Returns:
        L2 范数(空向量返回 0.0)
    """
    if not a:
        return 0.0
    return math.sqrt(sum(x * x for x in a))


def cosine_similarity(a: Vector, b: Vector) -> float:
    """余弦相似度, 值域 [-1, 1]。

    算法: cos(a, b) = (a · b) / (||a|| * ||b||)
        - 点积 a·b 为 O(n)
        - 范数 ||a||、||b|| 各为 O(n)
        - 总复杂度 O(n)(优于先归一化再点积的两次遍历)
        - 零向量(任一)直接返回 0.0, 避免除零

    Args:
        a: 向量 A
        b: 向量 B

    Returns:
        相似度 [-1, 1]; 任一为零向量返回 0.0
    """
    _check_nonempty(a, "a")
    _check_nonempty(b, "b")
    _check_same_dim(a, b)
    # 计算两向量范数
    na = norm(a)
    nb = norm(b)
    # 除零保护: 任一为零向量则无法定义角度, 返回中性值 0.0
    if na < _EPSILON or nb < _EPSILON:
        return 0.0
    # 点积 / 范数乘积
    return dot(a, b) / (na * nb)


def euclidean_distance(a: Vector, b: Vector) -> float:
    """欧氏距离: sqrt(sum((a_i - b_i)^2))。"""
    _check_nonempty(a, "a")
    _check_nonempty(b, "b")
    _check_same_dim(a, b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def manhattan_distance(a: Vector, b: Vector) -> float:
    """曼哈顿距离: sum(|a_i - b_i|)。"""
    _check_nonempty(a, "a")
    _check_nonempty(b, "b")
    _check_same_dim(a, b)
    return sum(abs(x - y) for x, y in zip(a, b))


def l2_normalize(a: Vector) -> list[float]:
    """L2 归一化为单位向量: a / ||a||。

    算法:
        - 计算范数 ||a|| (O(n))
        - 若范数为零(零向量), 返回原向量的拷贝(避免除零)
        - 否则每个元素除以范数 (O(n))

    Args:
        a: 输入向量

    Returns:
        单位向量(list[float]); 零向量返回原值拷贝
    """
    _check_nonempty(a, "a")
    n = norm(a)
    # 除零保护: 零向量无法归一化, 返回原值
    if n < _EPSILON:
        return list(a)
    return [x / n for x in a]


def scalar_multiply(a: Vector, s: float) -> list[float]:
    """向量数乘, 返回新向量。"""
    _check_nonempty(a, "a")
    return [x * s for x in a]


def vector_add(a: Vector, b: Vector) -> list[float]:
    """向量逐元素相加。

    Raises:
        ValueError: 维度不一致
    """
    _check_nonempty(a, "a")
    _check_nonempty(b, "b")
    _check_same_dim(a, b)
    return [x + y for x, y in zip(a, b)]


def vector_subtract(a: Vector, b: Vector) -> list[float]:
    """向量逐元素相减。

    Raises:
        ValueError: 维度不一致
    """
    _check_nonempty(a, "a")
    _check_nonempty(b, "b")
    _check_same_dim(a, b)
    return [x - y for x, y in zip(a, b)]


# ===========================================================================
# 矩阵 / 批量运算
# ===========================================================================


def matmul(a: Matrix, b: Matrix) -> Matrix:
    """矩阵乘法 a(m×k) × b(k×n) = c(m×n)。"""
    if not a or not b:
        return []
    len(b[0])
    # 转置 b 加速列访问(将列访问转为行访问)
    b_t = list(zip(*b))
    return [[sum(x * y for x, y in zip(row_a, col_b)) for col_b in b_t] for row_a in a]


def batch_cosine_similarity(query: Vector, matrix: Matrix) -> list[float]:
    """query 对矩阵每一行的余弦相似度。

    优化:
        - 预计算 query 范数一次(O(n))
        - 预分配输出列表(避免 append 重复扩容)
        - 零向量行直接填 0.0, 跳过点积计算

    Args:
        query: 查询向量
        matrix: 矩阵(每行为一条向量, 维度须与 query 一致)

    Returns:
        长度等于 len(matrix) 的相似度列表
    """
    if not query:
        return [0.0] * len(matrix)
    q_norm = norm(query)
    # 查询向量为零 → 全部返回 0.0
    if q_norm < _EPSILON:
        return [0.0] * len(matrix)
    # 预分配结果列表, 避免动态扩容
    n = len(matrix)
    out: list[float] = [0.0] * n
    for i in range(n):
        row = matrix[i]
        if not row:
            out[i] = 0.0
            continue
        rn = norm(row)
        # 行向量为零 → 相似度 0.0, 跳过点积
        if rn < _EPSILON:
            out[i] = 0.0
        else:
            out[i] = dot(query, row) / (q_norm * rn)
    return out


# ===========================================================================
# 统计与归约
# ===========================================================================


def mean(a: Vector) -> float:
    """算术平均值。空集合返回 0.0。"""
    return sum(a) / len(a) if a else 0.0


def variance(a: Vector) -> float:
    """总体方差(除以 n)。空集合返回 0.0。"""
    if not a:
        return 0.0
    m = mean(a)
    return sum((x - m) ** 2 for x in a) / len(a)


def stddev(a: Vector) -> float:
    """总体标准差。"""
    return math.sqrt(variance(a))


def minmax_scale(a: Vector, lo: float = 0.0, hi: float = 1.0) -> list[float]:
    """Min-Max 归一化到 [lo, hi]。"""
    if not a:
        return []
    mn, mx = min(a), max(a)
    # 极差为零(常量序列) → 取区间中点, 避免除零
    if mx == mn:
        return [(lo + hi) / 2.0] * len(a)
    span = mx - mn
    return [lo + (x - mn) / span * (hi - lo) for x in a]


def zscore(a: Vector) -> list[float]:
    """Z-Score 标准化。"""
    if not a:
        return []
    m, s = mean(a), stddev(a)
    # 标准差为零(常量序列) → 全部置 0, 避免除零
    if s < _EPSILON:
        return [0.0] * len(a)
    return [(x - m) / s for x in a]


# ===========================================================================
# Top-K 检索 (部分排序, 高性能核心算法)
# ===========================================================================


def top_k_indices(scores: Sequence[float], k: int) -> list[int]:
    """返回得分最高的 k 个索引(按得分降序)。

    算法: 基于最小堆的部分排序
        - 维护大小为 k 的最小堆, 堆顶为当前 top-k 中最小者
        - 遍历 n 个元素, 每次比较/入堆 O(log k)
        - 总复杂度 O(n log k), 远优于完整排序 O(n log n)
        - 当 k << n 时性能优势显著(检索场景典型)

    边界处理:
        - k <= 0: 返回空列表
        - k > n: 等价于 k = n(返回全部索引降序)

    Args:
        scores: 得分序列
        k:       取前 k 个

    Returns:
        索引列表(按得分降序)
    """
    import heapq

    n = len(scores)
    # 边界: k 非正或序列空 → 直接返回空
    if k <= 0 or n == 0:
        return []
    # 边界: k 超过序列长度 → 截断到 n
    k = min(k, n)
    if k == 0:
        return []

    # 维护大小为 k 的最小堆, 堆顶是当前 top-k 中最小的
    # 堆存 (score, -index): 负 index 充当次序键, 保证同分时索引小者优先(稳定排序)
    heap: list[tuple[float, int]] = []
    for idx, sc in enumerate(scores):
        if len(heap) < k:
            # 堆未满, 直接入堆
            heapq.heappush(heap, (sc, -idx))
        elif sc > heap[0][0]:
            # 堆满且当前得分高于堆顶 → 替换堆顶
            heapq.heapreplace(heap, (sc, -idx))
    # nlargest 弹出 k 个最大, 然后还原 index(取负)
    result = [(-neg_idx) for _, neg_idx in heapq.nlargest(k, heap)]
    return result


def top_k_with_scores(scores: Sequence[float], k: int) -> list[tuple[int, float]]:
    """返回 (index, score) 降序列表。

    边界:
        - k <= 0: 返回空列表
        - k > n: 返回全部 n 项降序
    """
    idxs = top_k_indices(scores, k)
    return [(i, scores[i]) for i in idxs]


# ===========================================================================
# Softmax 与概率采样
# ===========================================================================


def softmax(a: Sequence[float], temperature: float = 1.0) -> list[float]:
    """数值稳定的 Softmax, temperature 越大越平滑。"""
    if not a:
        return []
    # temperature 加下界, 避免除零
    t = max(temperature, 1e-8)
    scaled = [x / t for x in a]
    # 减去最大值稳定数值, 防止 exp 上溢
    mx = max(scaled)
    exps = [math.exp(x - mx) for x in scaled]
    s = sum(exps)
    # 极端情况(全部 -inf) → 均匀分布
    if s < _EPSILON:
        return [1.0 / len(scaled)] * len(scaled)
    return [e / s for e in exps]


def argmax(a: Sequence[float]) -> int:
    """返回最大值索引。空序列返回 -1。"""
    if not a:
        return -1
    best_i, best_v = 0, a[0]
    for i in range(1, len(a)):
        if a[i] > best_v:
            best_i, best_v = i, a[i]
    return best_i


# ===========================================================================
# 距离/相似度矩阵构建 (供聚类/去重使用)
# ===========================================================================


def pairwise_cosine_matrix(vectors: Matrix) -> Matrix:
    """计算向量集合两两余弦相似度方阵。

    优化: 预计算所有范数一次, 避免在内层重复计算。
    """
    n = len(vectors)
    if n == 0:
        return []
    norms = [norm(v) for v in vectors]
    # 预分配 n×n 方阵
    mat: list[list[float]] = [[0.0] * n for _ in range(n)]
    # 对称矩阵: 只算上三角, 镜像填充下三角
    for i in range(n):
        for j in range(i + 1, n):
            # 任一为零向量 → 相似度 0.0(除零保护)
            if norms[i] < _EPSILON or norms[j] < _EPSILON:
                s = 0.0
            else:
                s = dot(vectors[i], vectors[j]) / (norms[i] * norms[j])
            mat[i][j] = s
            mat[j][i] = s
    return mat


# ===========================================================================
# 向量平均 (用于多路召回融合 / 句子聚合)
# ===========================================================================


def mean_pool(vectors: Sequence[Vector]) -> list[float]:
    """对一组等长向量取平均。

    Raises:
        ValueError: 向量维度不一致
    """
    if not vectors:
        return []
    dim = len(vectors[0])
    # 预分配累加器
    out = [0.0] * dim
    for v in vectors:
        # 维度一致性校验, 避免静默截断
        if len(v) != dim:
            raise ValueError(f"向量维度不一致: 期望 {dim}, 实际 {len(v)}")
        for i in range(dim):
            out[i] += v[i]
    n = len(vectors)
    return [x / n for x in out]


def weighted_mean_pool(vectors: Sequence[Vector], weights: Sequence[float]) -> list[float]:
    """加权平均池化。

    Raises:
        ValueError: 向量维度不一致, 或 weights 与 vectors 数量不匹配
    """
    if not vectors:
        return []
    if len(weights) != len(vectors):
        raise ValueError(f"weights 数量({len(weights)}) != vectors 数量({len(vectors)})")
    dim = len(vectors[0])
    total_w = sum(weights)
    # 权重全零 → 退化为均权平均
    if total_w < _EPSILON:
        return mean_pool(vectors)
    out = [0.0] * dim
    for v, w in zip(vectors, weights):
        if len(v) != dim:
            raise ValueError(f"向量维度不一致: 期望 {dim}, 实际 {len(v)}")
        for i in range(dim):
            out[i] += v[i] * w
    return [x / total_w for x in out]


# ===========================================================================
# 常用数学工具
# ===========================================================================


def clamp(x: float, lo: float, hi: float) -> float:
    """限制在区间 [lo, hi]。"""
    return lo if x < lo else (hi if x > hi else x)


def sigmoid(x: float) -> float:
    """Sigmoid 激活。数值稳定(分正负两支避免 exp 上溢)。"""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def is_close(a: float, b: float, rel_tol: float = 1e-9, abs_tol: float = 0.0) -> bool:
    """浮点近似相等判断。"""
    return abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)
