"""
元启发式优化 (Metaheuristic Optimization)
===========================================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  SimulatedAnnealing - 模拟退火 (金属退火启发, 全局最优)
  GeneticAlgorithm   - 遗传算法 (选择/交叉/变异)
  ParticleSwarm      - 粒子群优化 (群体智能)
  AntColony          - 蚁群算法 (旅行商 TSP)
  TabuSearch         - 禁忌搜索 (短期记忆避局部最优)
  HillClimbing       - 爬山法 (含随机重启)
"""
from __future__ import annotations

import math
import random
from typing import Callable, Sequence


# ===========================================================================
# SimulatedAnnealing — 模拟退火
# ===========================================================================

class SimulatedAnnealing:
    """模拟退火: 模拟金属退火过程, 以概率接受劣解跳出局部最优。

    原理:
      1. 初始温度 T 高, 以较大概率接受劣解
      2. 温度逐渐降低 (冷却调度), 接受劣解概率下降
      3. 最终趋于贪心 (只接受更优解)

    接受概率: P(ΔE) = exp(-ΔE / T), ΔE > 0 (劣解)

    复杂度: O(iterations * 评估成本)

    Example:
        >>> # 最小化 f(x) = x^2, 最优 x=0
        >>> f = lambda x: x ** 2
        >>> neighbor = lambda x: x + random.gauss(0, 1)
        >>> best, val = SimulatedAnnealing.optimize(
        ...     f, neighbor, x0=10.0, T0=100, T_min=0.01, alpha=0.95
        ... )
        >>> abs(best) < 1.0  # True
    """

    @staticmethod
    def optimize(
        objective: Callable[[float], float],
        neighbor: Callable[[float], float],
        x0: float,
        T0: float = 100.0,
        T_min: float = 0.01,
        alpha: float = 0.95,
        iterations_per_temp: int = 100,
        seed: int | None = None,
    ) -> tuple[float, float]:
        """模拟退火优化。

        Args:
            objective: 目标函数 f(x) → 最小化
            neighbor:  邻域函数, 从当前解生成新解
            x0: 初始解
            T0: 初始温度
            T_min: 最低温度 (停止条件)
            alpha: 冷却系数 (0 < alpha < 1)
            iterations_per_temp: 每个温度的迭代次数
            seed: 随机种子

        Returns:
            (最优解, 最优目标值)
        """
        rng = random.Random(seed)
        x = x0
        fx = objective(x)
        best_x, best_fx = x, fx
        T = T0
        while T > T_min:
            for _ in range(iterations_per_temp):
                x_new = neighbor(x)
                fx_new = objective(x_new)
                delta = fx_new - fx
                if delta < 0:
                    x, fx = x_new, fx_new
                    if fx < best_fx:
                        best_x, best_fx = x, fx
                else:
                    # 以概率 exp(-ΔE/T) 接受劣解
                    if rng.random() < math.exp(-delta / T):
                        x, fx = x_new, fx_new
            T *= alpha
        return best_x, best_fx

    @staticmethod
    def optimize_vector(
        objective: Callable[[list[float]], float],
        neighbor: Callable[[list[float]], list[float]],
        x0: list[float],
        T0: float = 100.0,
        T_min: float = 0.01,
        alpha: float = 0.95,
        iterations_per_temp: int = 100,
        seed: int | None = None,
    ) -> tuple[list[float], float]:
        """多维向量版模拟退火。"""
        rng = random.Random(seed)
        x = list(x0)
        fx = objective(x)
        best_x, best_fx = list(x), fx
        T = T0
        while T > T_min:
            for _ in range(iterations_per_temp):
                x_new = neighbor(list(x))
                fx_new = objective(x_new)
                delta = fx_new - fx
                if delta < 0:
                    x, fx = x_new, fx_new
                    if fx < best_fx:
                        best_x, best_fx = list(x), fx
                else:
                    if rng.random() < math.exp(-delta / T):
                        x, fx = x_new, fx_new
            T *= alpha
        return best_x, best_fx


# ===========================================================================
# GeneticAlgorithm — 遗传算法
# ===========================================================================

class GeneticAlgorithm:
    """遗传算法: 模拟自然选择和遗传机制。

    流程:
      1. 初始化种群
      2. 评估适应度
      3. 选择 (轮盘赌/锦标赛)
      4. 交叉 (单点/多点)
      5. 变异
      6. 精英保留

    Example:
        >>> # 最大化 f(x) = -x^2 + 10x (最优 x=5)
        >>> ga = GeneticAlgorithm(
        ...     fitness=lambda x: -(x-5)**2 + 25,
        ...     mutate=lambda x: x + random.gauss(0, 0.5),
        ...     crossover=lambda a, b: (a + b) / 2,
        ... )
        >>> best = ga.optimize(pop_size=50, n_gen=100, x_range=(0, 10))
        >>> abs(best - 5) < 1.0  # True
    """

    def __init__(
        self,
        fitness: Callable[[float], float],
        mutate: Callable[[float], float],
        crossover: Callable[[float, float], float],
        seed: int | None = None,
    ):
        self._fitness = fitness
        self._mutate = mutate
        self._crossover = crossover
        self._rng = random.Random(seed)

    def optimize(
        self,
        pop_size: int = 50,
        n_gen: int = 100,
        x_range: tuple[float, float] = (-10, 10),
        mutation_rate: float = 0.1,
        elite_ratio: float = 0.1,
    ) -> float:
        """运行遗传算法, 返回最优解。"""
        if pop_size < 2:
            raise ValueError("pop_size 必须 >= 2")
        lo, hi = x_range
        # 初始化种群
        population = [
            self._rng.uniform(lo, hi) for _ in range(pop_size)
        ]
        n_elite = max(1, int(pop_size * elite_ratio))
        best_x = population[0]
        best_fit = self._fitness(best_x)

        for _ in range(n_gen):
            # 评估
            scored = [(x, self._fitness(x)) for x in population]
            scored.sort(key=lambda t: t[1], reverse=True)
            # 更新全局最优
            if scored[0][1] > best_fit:
                best_x, best_fit = scored[0]
            # 精英保留
            new_pop = [x for x, _ in scored[:n_elite]]
            # 生成后代
            while len(new_pop) < pop_size:
                # 锦标赛选择
                p1 = self._tournament(scored, 3)
                p2 = self._tournament(scored, 3)
                child = self._crossover(p1, p2)
                if self._rng.random() < mutation_rate:
                    child = self._mutate(child)
                new_pop.append(child)
            population = new_pop

        # 最终评估
        scored = [(x, self._fitness(x)) for x in population]
        scored.sort(key=lambda t: t[1], reverse=True)
        if scored[0][1] > best_fit:
            best_x = scored[0][0]
        return best_x

    def _tournament(
        self,
        scored: list[tuple[float, float]],
        k: int,
    ) -> float:
        """锦标赛选择: 从 k 个随机个体中选最优。"""
        contestants = self._rng.sample(scored, min(k, len(scored)))
        return max(contestants, key=lambda t: t[1])[0]


# ===========================================================================
# ParticleSwarm — 粒子群优化
# ===========================================================================

class ParticleSwarm:
    """粒子群优化 (PSO): 群体智能, 模拟鸟群觅食。

    原理:
      每个粒子有位置 x 和速度 v, 更新规则:
        v(t+1) = w*v(t) + c1*r1*(p_best - x) + c2*r2*(g_best - x)
        x(t+1) = x(t) + v(t+1)
      其中:
        w  = 惯性权重 (探索 vs 开发)
        c1 = 个体学习因子 (向自身最优靠近)
        c2 = 社会学习因子 (向全局最优靠近)

    Example:
        >>> # 最小化 Sphere 函数 f(x) = Σ x_i^2, 最优 x=0
        >>> pso = ParticleSwarm(
        ...     objective=lambda x: sum(v**2 for v in x),
        ...     dim=5,
        ...     bounds=(-10, 10),
        ... )
        >>> best = pso.optimize(n_particles=30, n_iter=100)
        >>> sum(v**2 for v in best) < 1.0  # True
    """

    def __init__(
        self,
        objective: Callable[[list[float]], float],
        dim: int,
        bounds: tuple[float, float],
        seed: int | None = None,
    ):
        self._objective = objective
        self._dim = dim
        self._lo, self._hi = bounds
        self._rng = random.Random(seed)

    def optimize(
        self,
        n_particles: int = 30,
        n_iter: int = 100,
        w: float = 0.7,
        c1: float = 1.5,
        c2: float = 1.5,
    ) -> list[float]:
        """运行 PSO, 返回全局最优位置。"""
        # 初始化粒子
        positions = [
            [self._rng.uniform(self._lo, self._hi) for _ in range(self._dim)]
            for _ in range(n_particles)
        ]
        velocities = [
            [self._rng.uniform(-1, 1) for _ in range(self._dim)]
            for _ in range(n_particles)
        ]
        p_best = [list(p) for p in positions]
        p_best_val = [self._objective(p) for p in positions]
        g_best = min(range(n_particles), key=lambda i: p_best_val[i])
        g_best_pos = list(p_best[g_best])
        g_best_val = p_best_val[g_best]

        for _ in range(n_iter):
            for i in range(n_particles):
                for d in range(self._dim):
                    r1 = self._rng.random()
                    r2 = self._rng.random()
                    velocities[i][d] = (
                        w * velocities[i][d]
                        + c1 * r1 * (p_best[i][d] - positions[i][d])
                        + c2 * r2 * (g_best_pos[d] - positions[i][d])
                    )
                    positions[i][d] += velocities[i][d]
                    # 边界约束
                    positions[i][d] = max(self._lo, min(self._hi, positions[i][d]))
                # 评估
                val = self._objective(positions[i])
                if val < p_best_val[i]:
                    p_best[i] = list(positions[i])
                    p_best_val[i] = val
                    if val < g_best_val:
                        g_best_pos = list(positions[i])
                        g_best_val = val
        return g_best_pos


# ===========================================================================
# AntColony — 蚁群算法 (TSP)
# ===========================================================================

class AntColony:
    """蚁群算法: 模拟蚂蚁信息素, 解决旅行商问题 (TSP)。

    原理:
      1. 蚂蚁在路径上释放信息素
      2. 后续蚂蚁以概率选择路径 (信息素浓度 × 启发式)
      3. 短路径信息素累积更快 (正反馈)
      4. 信息素挥发 (避免早熟收敛)

    复杂度: O(n_ants * n_iter * n^2)

    Example:
        >>> # 4 城市距离矩阵
        >>> dist = [[0, 10, 15, 20], [10, 0, 35, 25],
        ...         [15, 35, 0, 30], [20, 25, 30, 0]]
        >>> ac = AntColony(dist, n_ants=10, n_iter=50)
        >>> path, length = ac.solve()
        >>> len(path)  # 4
    """

    def __init__(
        self,
        distances: list[list[float]],
        n_ants: int = 10,
        n_iter: int = 100,
        alpha: float = 1.0,    # 信息素权重
        beta: float = 2.0,     # 启发式权重
        rho: float = 0.5,      # 信息素挥发率
        Q: float = 100.0,      # 信息素总量
        seed: int | None = None,
    ):
        self._dist = distances
        self._n = len(distances)
        self._n_ants = n_ants
        self._n_iter = n_iter
        self._alpha = alpha
        self._beta = beta
        self._rho = rho
        self._Q = Q
        self._rng = random.Random(seed)
        # 启发式信息: η = 1/distance
        self._eta = [
            [0.0 if distances[i][j] == 0 else 1.0 / distances[i][j]
             for j in range(self._n)]
            for i in range(self._n)
        ]
        # 初始信息素
        self._pheromone = [[1.0] * self._n for _ in range(self._n)]

    def solve(self) -> tuple[list[int], float]:
        """求解 TSP, 返回 (最优路径, 总距离)。"""
        best_path: list[int] = []
        best_length = float("inf")
        for _ in range(self._n_iter):
            paths = []
            lengths = []
            for _ in range(self._n_ants):
                path, length = self._construct_path()
                paths.append(path)
                lengths.append(length)
                if length < best_length:
                    best_path = list(path)
                    best_length = length
            # 更新信息素
            self._update_pheromone(paths, lengths)
        return best_path, best_length

    def _construct_path(self) -> tuple[list[int], float]:
        """一只蚂蚁构建一条路径。"""
        start = self._rng.randint(0, self._n - 1)
        visited = {start}
        path = [start]
        total = 0.0
        current = start
        while len(visited) < self._n:
            # 计算转移概率
            probs = []
            candidates = []
            for j in range(self._n):
                if j in visited:
                    continue
                tau = self._pheromone[current][j] ** self._alpha
                eta = self._eta[current][j] ** self._beta
                probs.append(tau * eta)
                candidates.append(j)
            if not candidates:
                break
            total_prob = sum(probs)
            if total_prob < 1e-15:
                next_city = self._rng.choice(candidates)
            else:
                probs = [p / total_prob for p in probs]
                next_city = self._rng.choices(candidates, weights=probs)[0]
            total += self._dist[current][next_city]
            path.append(next_city)
            visited.add(next_city)
            current = next_city
        # 回到起点
        if len(path) == self._n:
            total += self._dist[current][path[0]]
            path.append(path[0])
        return path, total

    def _update_pheromone(
        self,
        paths: list[list[int]],
        lengths: list[float],
    ) -> None:
        """信息素更新: 挥发 + 沉积。"""
        # 挥发
        for i in range(self._n):
            for j in range(self._n):
                self._pheromone[i][j] *= (1 - self._rho)
        # 沉积
        for path, length in zip(paths, lengths):
            if length < 1e-15:
                continue
            delta = self._Q / length
            for k in range(len(path) - 1):
                i, j = path[k], path[k + 1]
                self._pheromone[i][j] += delta
                self._pheromone[j][i] += delta


# ===========================================================================
# TabuSearch — 禁忌搜索
# ===========================================================================

class TabuSearch:
    """禁忌搜索: 用短期记忆避免重复, 跳出局部最优。

    原理:
      1. 当前解的邻域中选最优 (即使比当前差)
      2. 将刚移动的解加入禁忌表 (短期内不可重访)
      3. 藐视准则: 若禁忌解优于全局最优, 仍可接受

    Example:
        >>> # 最小化 f(x) = x^2
        >>> f = lambda x: x ** 2
        >>> neighbors = lambda x: [x-1, x+1, x-2, x+2]
        >>> best, val = TabuSearch.optimize(f, neighbors, x0=10, max_iter=50, tabu_size=10)
    """

    @staticmethod
    def optimize(
        objective: Callable[[float], float],
        neighbor_fn: Callable[[float], list[float]],
        x0: float,
        max_iter: int = 100,
        tabu_size: int = 10,
        seed: int | None = None,
    ) -> tuple[float, float]:
        """禁忌搜索。

        Args:
            objective: 目标函数 (最小化)
            neighbor_fn: 返回邻域解列表
            x0: 初始解
            max_iter: 最大迭代次数
            tabu_size: 禁忌表大小
            seed: 随机种子

        Returns:
            (最优解, 最优值)
        """
        rng = random.Random(seed)
        x = x0
        fx = objective(x)
        best_x, best_fx = x, fx
        tabu: list[float] = []
        for _ in range(max_iter):
            neighbors = neighbor_fn(x)
            # 过滤禁忌解 (除非满足藐视准则)
            best_candidate = None
            best_candidate_val = float("inf")
            for n in neighbors:
                fn = objective(n)
                is_tabu = any(abs(n - t) < 1e-10 for t in tabu)
                if is_tabu and fn >= best_fx:
                    continue  # 禁忌且不满足藐视
                if fn < best_candidate_val:
                    best_candidate_val = fn
                    best_candidate = n
            if best_candidate is None:
                break
            x = best_candidate
            fx = best_candidate_val
            # 更新禁忌表
            tabu.append(x)
            if len(tabu) > tabu_size:
                tabu.pop(0)
            # 更新全局最优
            if fx < best_fx:
                best_x, best_fx = x, fx
        return best_x, best_fx


# ===========================================================================
# HillClimbing — 爬山法 (含随机重启)
# ===========================================================================

class HillClimbing:
    """爬山法: 贪心搜索, 含随机重启避免局部最优。

    Example:
        >>> f = lambda x: -(x - 3) ** 2  # 最优 x=3
        >>> neighbors = lambda x: [x + 0.1, x - 0.1, x + 0.01, x - 0.01]
        >>> best, val = HillClimbing.optimize(f, neighbors, x0=0.0)
    """

    @staticmethod
    def optimize(
        objective: Callable[[float], float],
        neighbor_fn: Callable[[float], list[float]],
        x0: float,
        max_iter: int = 1000,
        restarts: int = 5,
        seed: int | None = None,
    ) -> tuple[float, float]:
        """爬山法 + 随机重启。

        Args:
            objective: 目标函数 (最大化)
            neighbor_fn: 邻域函数
            x0: 初始解
            max_iter: 每次重启的最大迭代次数
            restarts: 随机重启次数
            seed: 随机种子

        Returns:
            (最优解, 最优值)
        """
        rng = random.Random(seed)
        best_x, best_fx = x0, objective(x0)
        for r in range(restarts + 1):
            if r == 0:
                current = x0
            else:
                # 随机重启
                current = x0 + rng.gauss(0, abs(x0) * 0.5 + 1)
            current_fx = objective(current)
            for _ in range(max_iter):
                neighbors = neighbor_fn(current)
                best_neighbor = max(neighbors, key=objective)
                fn = objective(best_neighbor)
                if fn > current_fx:
                    current = best_neighbor
                    current_fx = fn
                else:
                    break  # 局部最优
            if current_fx > best_fx:
                best_x, best_fx = current, current_fx
        return best_x, best_fx
