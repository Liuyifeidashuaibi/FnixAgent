"""
OfficeAgent 内核算法库 (Kernel Algorithm Library)
==================================================
纯 Python + 标准库实现的高性能算法内核,零外部依赖。

模块清单 (13 模块):
  collections    - 高性能数据结构 (BloomFilter / LRU / RingBuffer / SkipList / Trie / BitArray / DisjointSet)
  hashing        - 哈希与指纹 (SimHash / MinHash / LSH / RollingHash / ConsistentHash / CuckooHash)
  encoding       - 编解码与压缩 (VarInt / Delta / RLE / Hex / Base64 / BinaryIO / ZigZag)
  concurrency    - 并发原语 (TokenBucket / SlidingWindow / Semaphore / RWLock / Barrier / CancellationToken)
  stringalg      - 字符串算法 (KMP / Boyer-Moore / Aho-Corasick / Levenshtein / LCS / JaroWinkler)
  numerical      - 数值方法 (Newton / GradientDescent / Interpolation / Integration / RootFinding / MatrixOps)
  probabilistic  - 概率数据结构 (HyperLogLog / CountMinSketch / ReservoirSampling / CuckooFilter / HeavyKeeper)
  graph          - 图算法 (BFS / DFS / Dijkstra / A* / TopologicalSort / Kruskal / Prim / Tarjan / Floyd)
  sorting        - 排序算法 (MergeSort / QuickSort / HeapSort / RadixSort / CountingSort / IntroSort / PartialSort)
  compression    - 压缩算法 (Huffman / LZW / LZ77 / BitIO / RLE2 / CompressionStats)
  signal         - 信号处理 (FFT / DFT / Convolution / WindowFunctions / Correlation / SpectralAnalysis / Filters)
  optimization   - 元启发式优化 (SimulatedAnnealing / GeneticAlgorithm / ParticleSwarm / AntColony / TabuSearch)
  information    - 信息论 (Entropy / KLDivergence / CrossEntropy / MutualInformation / InformationGain / ChannelCapacity)

设计原则:
  - 零外部依赖: 仅依赖 Python stdlib (math / heapq / itertools / collections / threading / struct / cmath / random)
  - 类型安全: 完整的类型标注 (from __future__ import annotations)
  - 边界完备: 空输入 / 零除 / 溢出 / 并发安全 全部处理
  - 独立集成: 每个模块可单独拷贝到任何项目,无需修改
  - 性能优先: 算法复杂度标注,关键路径用原生数据结构
"""
from __future__ import annotations

__all__ = [
    "collections",
    "hashing",
    "encoding",
    "concurrency",
    "stringalg",
    "numerical",
    "probabilistic",
    "graph",
    "sorting",
    "compression",
    "signal",
    "optimization",
    "information",
]