"""
∞ Genetic Evolver — 遗传帕累托进化层 (遗传优化 + SIPDO 启发)

设计思路:
  - 遗传优化 (ICLR 2026 Oral): Genetic-Pareto Prompt Evolution
    比主流RL高6%, 数据量仅1/35, 多目标同时优化
  - SIPDO (ICLR 2026): Self-Improving Prompt Design Optimization
    Prompt Learning 闭环自进化, 不断生成新问题新机制
  - 训练框架 RL 训练集成

核心算法:
  1. 编码: 将 Prompt/Skill 编码为基因序列 (每段独立可变异)
  2. 初始化种群: 从基线 Prompt 变异生成 N 个后代
  3. 评估: 在基准任务上运行, 收集多维度指标
  4. 帕累托排序: 非支配排序, 保留帕累托前沿
  5. 选择: 锦标赛选择, 倾向帕累托前沿个体
  6. 交叉: 随机交换两个父代的 Prompt 模块
  7. 变异: 随机替换/插入/删除 Prompt 模块
  8. 精英保留: 保留最优个体直接进入下一代
  9. 收敛检测: 帕累托前沿不再移动时停止

架构:
  ┌─────────────────────────────────────────────────────────────┐
  │                  Genetic Evolver                            │
  ├─────────────────────────────────────────────────────────────┤
  │  Gene Encoder    │  Population    │  Pareto Frontier        │
  │  (基因编码器)     │  (种群管理)    │  (帕累托前沿)           │
  ├─────────────────────────────────────────────────────────────┤
  │  Tournament      │  Crossover     │  Mutation               │
  │  Selector        │  Operator      │  Operator               │
  │  (锦标赛选择)     │  (交叉算子)    │  (变异算子)             │
  ├─────────────────────────────────────────────────────────────┤
  │  Fitness Evaluator    │  Convergence Detector               │
  │  (适应度评估器)        │  (收敛检测器)                        │
  └─────────────────────────────────────────────────────────────┘
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# 基因编码模型
# ============================================================


class GeneType(str, Enum):
    """基因类型"""

    SYSTEM_PROMPT = "system_prompt"  # 系统提示词模块
    TASK_PROMPT = "task_prompt"  # 任务提示词模块
    TOOL_INSTRUCTION = "tool_instruction"  # 工具使用指令
    FEW_SHOT_EXAMPLE = "few_shot"  # Few-shot 示例
    CHAIN_OF_THOUGHT = "chain_of_thought"  # 思维链引导
    OUTPUT_FORMAT = "output_format"  # 输出格式约束
    CONSTRAINT = "constraint"  # 约束条件
    SKILL_STEP = "skill_step"  # 技能步骤


@dataclass
class Gene:
    """
    基因 — Prompt 中的一个可进化模块

    每个 Gene 是可以独立变异的基本单元
    """

    gene_id: str
    gene_type: GeneType
    content: str  # 基因内容 (Prompt 文本)
    weight: float = 1.0  # 权重 (0-1, 越高越重要)
    parent_gene_ids: list[str] = field(default_factory=list)  # 来源基因 (追踪进化)
    mutation_history: list[str] = field(default_factory=list)  # 变异历史
    performance_score: float = 0.0  # 该基因的性能贡献
    generation: int = 0  # 所属代数


@dataclass
class Chromosome:
    """
    染色体 — 一个完整的 Prompt/Skill 个体

    由多个 Gene 组成, 代表一个可执行的完整 Prompt
    """

    chromosome_id: str
    gene_type: str  # 染色体类型 (对应 Loop category)
    genes: list[Gene] = field(default_factory=list)
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)
    # 多维度适应度
    fitness: dict[str, float] = field(
        default_factory=lambda: {
            "quality": 0.0,  # 输出质量
            "efficiency": 0.0,  # 执行效率 (token 消耗)
            "robustness": 0.0,  # 鲁棒性 (错误恢复)
            "safety": 0.0,  # 安全性
            "novelty": 0.0,  # 新颖性 (避免收敛到局部最优)
        }
    )
    pareto_rank: int = 0  # 帕累托前沿层级
    crowding_distance: float = 0.0  # 拥挤距离
    total_score: float = 0.0  # 综合评分
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ============================================================
# 帕累托前沿引擎
# ============================================================


class ParetoFrontier:
    """
    帕累托前沿 — 多目标非支配排序

    在 quality x efficiency x robustness x safety 四个维度上
    同时优化, 找出所有非支配解
    """

    def __init__(self):
        self._frontiers: list[list[Chromosome]] = []  # 多层前沿
        self._all_solutions: list[Chromosome] = []

    def compute_pareto_ranks(self, population: list[Chromosome]) -> list[list[Chromosome]]:
        """
        计算帕累托前沿层级 (非支配排序)

        算法: NSGA-II 的 fast non-dominated sort
        """
        n = len(population)
        dominated_count = [0] * n
        dominates = [[] for _ in range(n)]

        # 计算支配关系
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if self._dominates(population[i], population[j]):
                    dominates[i].append(j)
                elif self._dominates(population[j], population[i]):
                    dominated_count[i] += 1

        # 分层
        fronts = []
        current_front = [i for i in range(n) if dominated_count[i] == 0]

        while current_front:
            fronts.append([population[i] for i in current_front])
            next_front = []
            for i in current_front:
                for j in dominates[i]:
                    dominated_count[j] -= 1
                    if dominated_count[j] == 0:
                        next_front.append(j)
            current_front = next_front

        # 标记 rank
        for rank, front in enumerate(fronts):
            for chromo in front:
                chromo.pareto_rank = rank

        self._frontiers = fronts
        self._all_solutions = population
        return fronts

    def _dominates(self, a: Chromosome, b: Chromosome) -> bool:
        """
        判断 a 是否支配 b

        a 支配 b 意味着: a 在所有维度上 >= b, 且至少一个维度上 > b
        """
        fitness_keys = ["quality", "efficiency", "robustness", "safety"]
        at_least_one_better = False

        for key in fitness_keys:
            if a.fitness[key] < b.fitness[key]:
                return False
            if a.fitness[key] > b.fitness[key]:
                at_least_one_better = True

        return at_least_one_better

    def compute_crowding_distance(self, front: list[Chromosome]):
        """计算拥挤距离 (保持多样性)"""
        if len(front) <= 2:
            for c in front:
                c.crowding_distance = float("inf")
            return

        for c in front:
            c.crowding_distance = 0.0

        fitness_keys = ["quality", "efficiency", "robustness", "safety"]

        for key in fitness_keys:
            sorted_front = sorted(front, key=lambda c: c.fitness[key])
            f_min = sorted_front[0].fitness[key]
            f_max = sorted_front[-1].fitness[key]

            if f_max == f_min:
                continue

            sorted_front[0].crowding_distance = float("inf")
            sorted_front[-1].crowding_distance = float("inf")

            for i in range(1, len(sorted_front) - 1):
                sorted_front[i].crowding_distance += (
                    sorted_front[i + 1].fitness[key] - sorted_front[i - 1].fitness[key]
                ) / (f_max - f_min)

    def get_pareto_frontier(self) -> list[Chromosome]:
        """获取帕累托前沿 (第一层)"""
        if self._frontiers:
            return self._frontiers[0]
        return []

    def is_converged(self, threshold: float = 0.01, window: int = 3) -> bool:
        """检测帕累托前沿是否收敛"""
        if len(self._frontiers) < window:
            return False

        # 检查最近 window 代的前沿变化
        recent_fronts = self._frontiers[-window:]
        if len(recent_fronts) != window:
            return False

        # 计算前沿中心的移动距离
        centers = []
        for front in recent_fronts:
            if not front:
                return True
            avg_quality = sum(c.fitness["quality"] for c in front) / len(front)
            avg_efficiency = sum(c.fitness["efficiency"] for c in front) / len(front)
            centers.append((avg_quality, avg_efficiency))

        max_move = 0
        for i in range(1, len(centers)):
            move = math.sqrt(
                (centers[i][0] - centers[i - 1][0]) ** 2 + (centers[i][1] - centers[i - 1][1]) ** 2
            )
            max_move = max(max_move, move)

        return max_move < threshold


# ============================================================
# 遗传算子
# ============================================================


class GeneticOperators:
    """遗传算子集合 — 选择、交叉、变异"""

    # 变异模板 (用于 Prompt 优化)
    MUTATION_TEMPLATES = {
        "add_detail": "请更详细地描述: {content}",
        "add_example": "{content}\n\n示例: {example}",
        "simplify": "简化表达: {content}",
        "restructure": "重新组织: {content}",
        "add_constraint": "{content}\n\n约束条件: {constraint}",
        "focus_quality": "优先考虑输出质量: {content}",
        "focus_speed": "优先考虑执行效率: {content}",
        "add_chain_of_thought": "请逐步思考:\n{content}\n\n步骤1: 分析问题\n步骤2: 制定方案\n步骤3: 执行",
    }

    @staticmethod
    def tournament_select(
        population: list[Chromosome],
        tournament_size: int = 3,
    ) -> Chromosome:
        """
        锦标赛选择

        随机选 tournament_size 个个体, 返回帕累托最优的
        """
        candidates = random.sample(population, min(tournament_size, len(population)))

        # 选择帕累托 rank 最低的, 相同则选拥挤距离最大的
        best = min(candidates, key=lambda c: (c.pareto_rank, -c.crowding_distance))
        return best

    @staticmethod
    def crossover(
        parent_a: Chromosome,
        parent_b: Chromosome,
        crossover_rate: float = 0.7,
    ) -> tuple[Chromosome, Chromosome]:
        """
        单点交叉 — 交换两个父代的基因模块

        遗传优化 风格: 模块级交叉, 不是字符级
        """
        if random.random() > crossover_rate or len(parent_a.genes) < 2 or len(parent_b.genes) < 2:
            return copy.deepcopy(parent_a), copy.deepcopy(parent_b)

        child_a = copy.deepcopy(parent_a)
        child_b = copy.deepcopy(parent_b)

        # 随机选择交叉点
        cross_point_a = random.randint(1, len(parent_a.genes) - 1)
        cross_point_b = random.randint(1, len(parent_b.genes) - 1)

        # 交换基因片段
        child_a.genes = parent_a.genes[:cross_point_a] + parent_b.genes[cross_point_b:]
        child_b.genes = parent_b.genes[:cross_point_b] + parent_a.genes[cross_point_a:]

        # 更新元数据
        for child, pa, pb in [(child_a, parent_a, parent_b), (child_b, parent_b, parent_a)]:
            child.chromosome_id = (
                f"{pa.chromosome_id}_x_{pb.chromosome_id}_{random.randint(1000, 9999)}"
            )
            child.parent_ids = [pa.chromosome_id, pb.chromosome_id]
            child.generation = max(pa.generation, pb.generation) + 1

        return child_a, child_b

    @staticmethod
    def mutate(
        chromosome: Chromosome,
        mutation_rate: float = 0.3,
        mutation_strength: float = 0.5,
    ) -> Chromosome:
        """
        变异 — 随机修改基因

        支持多种变异操作:
          - 基因内容修改 (替换/插入/删除/LLM重写)
          - 基因权重调整
          - 基因类型变更
        """
        mutated = copy.deepcopy(chromosome)
        mutated.generation += 1

        for gene in mutated.genes:
            if random.random() > mutation_rate:
                continue

            mutation_type = random.choice(["content", "weight", "type", "split", "merge"])

            if mutation_type == "content":
                # 随机选择变异模板
                template = random.choice(list(GeneticOperators.MUTATION_TEMPLATES.values()))
                gene.content = template.format(content=gene.content)
                gene.mutation_history.append(f"content_{mutation_type}")

            elif mutation_type == "weight":
                # 小幅调整权重
                delta = random.uniform(-mutation_strength, mutation_strength)
                gene.weight = max(0.1, min(1.0, gene.weight + delta))
                gene.mutation_history.append(f"weight_{delta:.2f}")

            elif mutation_type == "type":
                # 变更基因类型
                new_type = random.choice(list(GeneType))
                gene.gene_type = new_type
                gene.mutation_history.append(f"type_{new_type.value}")

            elif mutation_type == "split":
                # 分裂为两个基因 (增加粒度)
                if len(gene.content) > 100:
                    mid = len(gene.content) // 2
                    new_gene = Gene(
                        gene_id=f"{gene.gene_id}_split",
                        gene_type=gene.gene_type,
                        content=gene.content[mid:],
                        weight=gene.weight * 0.5,
                        parent_gene_ids=[gene.gene_id],
                        generation=mutated.generation,
                    )
                    gene.content = gene.content[:mid]
                    gene.weight *= 0.5
                    gene.mutation_history.append("split")
                    mutated.genes.append(new_gene)

            elif mutation_type == "merge":
                # 合并相邻基因 (减少粒度)
                idx = mutated.genes.index(gene)
                if idx < len(mutated.genes) - 1:
                    next_gene = mutated.genes[idx + 1]
                    gene.content = gene.content + "\n\n" + next_gene.content
                    gene.weight = (gene.weight + next_gene.weight) / 2
                    gene.mutation_history.append("merge")
                    mutated.genes.remove(next_gene)

        # 重新生成 ID
        mutated.chromosome_id = f"{chromosome.chromosome_id}_m{random.randint(1000, 9999)}"
        mutated.parent_ids = [chromosome.chromosome_id]
        return mutated

    @staticmethod
    def elitism(
        population: list[Chromosome],
        elite_count: int = 2,
    ) -> list[Chromosome]:
        """精英保留 — 保留最优秀的个体直接进入下一代"""
        sorted_pop = sorted(
            population,
            key=lambda c: (c.pareto_rank, -c.crowding_distance),
        )
        return [copy.deepcopy(c) for c in sorted_pop[:elite_count]]


# ============================================================
# 遗传进化引擎
# ============================================================


@dataclass
class EvolutionConfig:
    """进化配置"""

    population_size: int = 20
    max_generations: int = 50
    crossover_rate: float = 0.7
    mutation_rate: float = 0.3
    mutation_strength: float = 0.5
    elite_count: int = 2
    convergence_threshold: float = 0.01
    convergence_window: int = 3
    early_stop_no_improvement: int = 10


@dataclass
class EvolutionResult:
    """进化结果"""

    best_chromosome: Chromosome
    pareto_frontier: list[Chromosome]
    all_generations: list[list[Chromosome]]
    total_generations: int
    converged: bool
    convergence_generation: int
    fitness_history: list[dict]
    started_at: str
    completed_at: str
    duration_ms: float
    # 扩展字段
    success: bool = True
    chromosome: Chromosome | None = None
    estimated_token_saving: int = 0
    error_message: str = ""


class GeneticEvolver:
    """
    遗传进化引擎 — 遗传优化 + SIPDO 启发

    端到端的 Prompt/Skill 进化流程:
      1. 编码 → 2. 初始化种群 → 3. 评估 → 4. 帕累托排序
      → 5. 选择 → 6. 交叉 → 7. 变异 → 8. 精英保留 → 9. 收敛检测
    """

    def __init__(
        self,
        config: EvolutionConfig | None = None,
        state_dir: str = "data/evolution_state",
    ):
        self.config = config or EvolutionConfig()
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.pareto = ParetoFrontier()
        self.operators = GeneticOperators()
        self._generation_count: int = 0
        self._best_ever: Chromosome | None = None
        self._fitness_history: list[dict] = []

    def encode(self, content: str, gene_type: str) -> Chromosome:
        """
        将原始 Prompt/Skill 编码为染色体

        智能分割: 按段落/标题/分隔符切分为多个 Gene
        """
        import re

        chromo_id = hashlib.md5(content.encode()).hexdigest()[:16]
        chromosome = Chromosome(
            chromosome_id=chromo_id,
            gene_type=gene_type,
        )

        # 按段落分割
        paragraphs = re.split(r"\n\n+", content)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        for i, para in enumerate(paragraphs):
            # 识别基因类型
            gtype = GeneType.SYSTEM_PROMPT
            if "示例" in para or "example" in para.lower():
                gtype = GeneType.FEW_SHOT_EXAMPLE
            elif "步骤" in para or "step" in para.lower():
                gtype = GeneType.CHAIN_OF_THOUGHT
            elif "格式" in para or "format" in para.lower():
                gtype = GeneType.OUTPUT_FORMAT
            elif "约束" in para or "constraint" in para.lower():
                gtype = GeneType.CONSTRAINT

            gene = Gene(
                gene_id=f"{chromo_id}_g{i}",
                gene_type=gtype,
                content=para,
                weight=1.0 / len(paragraphs),
            )
            chromosome.genes.append(gene)

        return chromosome

    def decode(self, chromosome: Chromosome) -> str:
        """将染色体解码为可执行的 Prompt 文本"""
        parts = []
        for gene in chromosome.genes:
            parts.append(gene.content)
        return "\n\n".join(parts)

    async def evolve(
        self,
        initial_content: str,
        gene_type: str,
        fitness_fn,
        max_generations: int | None = None,
    ) -> EvolutionResult:
        """
        执行遗传进化

        Args:
            initial_content: 初始 Prompt/Skill 文本
            gene_type: 进化类型 (对应 Loop category)
            fitness_fn: 适应度函数 async (chromosome) -> dict[str, float]
            max_generations: 最大代数 (覆盖 config)
        """
        import time

        max_gen = max_generations or self.config.max_generations
        started_at = datetime.now(UTC)
        start_time = time.time()

        # 1. 编码并初始化种群
        base_chromosome = self.encode(initial_content, gene_type)
        population = self._initialize_population(base_chromosome)
        all_generations = [population]

        no_improvement_count = 0

        logger.info(f"开始进化: {gene_type}, 种群大小: {self.config.population_size}")

        for generation in range(max_gen):
            self._generation_count = generation + 1

            # 2. 评估适应度
            for chromo in population:
                try:
                    chromo.fitness = await fitness_fn(chromo)
                except Exception as e:
                    logger.error(f"适应度评估失败 {chromo.chromosome_id}: {e}")
                    chromo.fitness = dict.fromkeys(chromo.fitness, 0.0)

            # 3. 帕累托排序
            self.pareto.compute_pareto_ranks(population)
            for front in self.pareto._frontiers:
                self.pareto.compute_crowding_distance(front)

            # 4. 记录最佳个体
            best = self._get_best(population)
            best_score = best.total_score
            avg_fitness = {
                k: sum(c.fitness[k] for c in population) / len(population) for k in best.fitness
            }

            self._fitness_history.append(
                {
                    "generation": generation,
                    "best_score": best_score,
                    "avg_fitness": avg_fitness,
                    "pareto_front_size": len(self.pareto.get_pareto_frontier()),
                }
            )

            if self._best_ever is None or best_score > self._best_ever.total_score:
                self._best_ever = best
                no_improvement_count = 0
            else:
                no_improvement_count += 1

            logger.info(
                f"Gen {generation}: best={best_score:.4f}, "
                f"pareto_front={len(self.pareto.get_pareto_frontier())}, "
                f"avg_quality={avg_fitness.get('quality', 0):.4f}"
            )

            # 5. 收敛检测
            if self.pareto.is_converged(
                self.config.convergence_threshold,
                self.config.convergence_window,
            ):
                logger.info(f"帕累托前沿收敛于第 {generation} 代")
                return EvolutionResult(
                    best_chromosome=self._best_ever or best,
                    pareto_frontier=self.pareto.get_pareto_frontier(),
                    all_generations=all_generations,
                    total_generations=generation + 1,
                    converged=True,
                    convergence_generation=generation,
                    fitness_history=self._fitness_history,
                    started_at=started_at.isoformat(),
                    completed_at=datetime.now(UTC).isoformat(),
                    duration_ms=(time.time() - start_time) * 1000,
                )

            # 6. 早停
            if no_improvement_count >= self.config.early_stop_no_improvement:
                logger.info(f"早停: {no_improvement_count} 代无改进")
                break

            # 7. 生成下一代
            next_population = self._generate_next_generation(population)
            all_generations.append(next_population)
            population = next_population

        return EvolutionResult(
            best_chromosome=self._best_ever or best,
            pareto_frontier=self.pareto.get_pareto_frontier(),
            all_generations=all_generations,
            total_generations=self._generation_count,
            converged=False,
            convergence_generation=-1,
            fitness_history=self._fitness_history,
            started_at=started_at.isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _initialize_population(self, base: Chromosome) -> list[Chromosome]:
        """初始化种群 — 从基线变异生成"""
        population = [base]

        for i in range(self.config.population_size - 1):
            variant = self.operators.mutate(
                base,
                mutation_rate=self.config.mutation_rate * 3,  # 初始高变异率
                mutation_strength=self.config.mutation_strength * 2,
            )
            variant.chromosome_id = f"{base.chromosome_id}_v{i}"
            variant.generation = 0
            population.append(variant)

        return population

    def _generate_next_generation(self, population: list[Chromosome]) -> list[Chromosome]:
        """生成下一代种群"""
        next_gen = []

        # 精英保留
        next_gen.extend(self.operators.elitism(population, self.config.elite_count))

        # 生成后代
        while len(next_gen) < self.config.population_size:
            # 选择
            parent_a = self.operators.tournament_select(population)
            parent_b = self.operators.tournament_select(population)

            # 交叉
            child_a, child_b = self.operators.crossover(
                parent_a, parent_b, self.config.crossover_rate
            )

            # 变异
            child_a = self.operators.mutate(
                child_a, self.config.mutation_rate, self.config.mutation_strength
            )
            child_b = self.operators.mutate(
                child_b, self.config.mutation_rate, self.config.mutation_strength
            )

            next_gen.append(child_a)
            if len(next_gen) < self.config.population_size:
                next_gen.append(child_b)

        return next_gen[: self.config.population_size]

    def _get_best(self, population: list[Chromosome]) -> Chromosome:
        """获取综合最优个体"""
        for chromo in population:
            chromo.total_score = (
                chromo.fitness.get("quality", 0) * 0.4
                + chromo.fitness.get("efficiency", 0) * 0.3
                + chromo.fitness.get("robustness", 0) * 0.2
                + chromo.fitness.get("safety", 0) * 0.1
            )

        return max(population, key=lambda c: c.total_score)

    def save_state(self):
        """保存进化状态"""
        state = {
            "generation_count": self._generation_count,
            "fitness_history": self._fitness_history,
            "best_ever_id": self._best_ever.chromosome_id if self._best_ever else None,
        }
        state_file = self.state_dir / "evolution_state.json"
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_state(self) -> dict:
        """加载进化状态"""
        state_file = self.state_dir / "evolution_state.json"
        if state_file.exists():
            return json.loads(state_file.read_text(encoding="utf-8"))
        return {}


# ============================================================
# 轨迹驱动的进化 (SCOPE 启发)
# ============================================================


class TrajectoryDrivenEvolution:
    """
    轨迹驱动进化 — 从执行轨迹中学习

    设计思路:
      - SCOPE: 从执行轨迹中合成指南, 自动演化
      - 遗传优化: 轨迹反馈驱动进化方向

    工作流程:
      1. 收集执行轨迹 (成功/失败)
      2. 分析轨迹中的模式
      3. 生成进化方向建议
      4. 反馈给 GeneticEvolver
    """

    def __init__(self, evolver: GeneticEvolver):
        self.evolver = evolver
        self._trajectories: list[dict] = []
        self._patterns: dict[str, int] = {}  # 模式 -> 出现次数

    def record_trajectory(self, chromosome_id: str, success: bool, metrics: dict, error: str = ""):
        """记录一条执行轨迹"""
        self._trajectories.append(
            {
                "chromosome_id": chromosome_id,
                "success": success,
                "metrics": metrics,
                "error": error,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # 提取模式
        if error:
            pattern = self._extract_error_pattern(error)
            self._patterns[pattern] = self._patterns.get(pattern, 0) + 1

    def _extract_error_pattern(self, error: str) -> str:
        """从错误中提取模式"""
        if "timeout" in error.lower():
            return "timeout"
        if "token" in error.lower() or "context" in error.lower():
            return "context_overflow"
        if "hallucination" in error.lower() or "incorrect" in error.lower():
            return "incorrect_output"
        if "format" in error.lower() or "parse" in error.lower():
            return "format_error"
        return "unknown"

    def get_evolution_direction(self) -> dict:
        """根据轨迹分析建议进化方向"""
        if not self._trajectories:
            return {}

        recent = self._trajectories[-50:]
        success_rate = sum(1 for t in recent if t["success"]) / len(recent)

        direction = {
            "success_rate": success_rate,
            "top_error_patterns": sorted(self._patterns.items(), key=lambda x: x[1], reverse=True)[
                :3
            ],
            "suggestion": "",
        }

        if success_rate < 0.5:
            direction["suggestion"] = "大幅变异: 当前策略有效性低, 需要探索新方向"
        elif success_rate < 0.8:
            direction["suggestion"] = "精细调整: 在现有策略基础上微调"
        else:
            direction["suggestion"] = "保持收敛: 当前策略已接近最优, 降低变异率"

        return direction

    def get_mutation_pressure(self) -> float:
        """根据成功率动态调整变异压力"""
        direction = self.get_evolution_direction()
        success_rate = direction.get("success_rate", 0.5)

        # 成功率低 → 高变异压力 (探索)
        # 成功率高 → 低变异压力 (利用)
        pressure = 1.0 - success_rate
        return max(0.1, min(1.0, pressure))

    async def evolve_from_insight(self, insight) -> EvolutionResult:
        """
        从洞察中提取的改进方向触发进化

        Args:
            insight: ExtractedInsight 对象 (含 upgrade_priority, suggested_action 等)

        Returns:
            EvolutionResult 进化结果
        """
        import time
        from datetime import datetime

        started_at = datetime.now(UTC)
        start_ts = time.time()

        # 将洞察编码为染色体进行进化
        initial_content = (
            f"{insight.title}\n\n{insight.description}\n\n建议行动: {insight.suggested_action}"
        )
        chromosome = self.evolver.encode(initial_content, insight.insight_type.value)

        # 使用轨迹驱动的变异压力
        pressure = self.get_mutation_pressure()

        # 执行一次定向变异 (不是完整进化循环)
        mutated = self.evolver.operators.mutate(
            chromosome,
            mutation_rate=max(0.3, pressure),
            mutation_strength=max(0.5, pressure),
        )

        # 估算 token 节省 (启发式)
        token_saving = 0
        if "token" in insight.suggested_action.lower() or "效率" in insight.suggested_action:
            token_saving = 200

        return EvolutionResult(
            best_chromosome=mutated,
            pareto_frontier=[mutated],
            all_generations=[[chromosome, mutated]],
            total_generations=1,
            converged=False,
            convergence_generation=-1,
            fitness_history=[],
            started_at=started_at.isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_ms=(time.time() - start_ts) * 1000,
            success=True,
            chromosome=mutated,
            estimated_token_saving=token_saving,
        )
