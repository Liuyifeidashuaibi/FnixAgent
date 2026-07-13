"""
字符串算法 (String Algorithms)
================================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  KMP               - Knuth-Morris-Pratt 子串匹配, O(n+m)
  BoyerMoore        - Boyer-Moore 子串匹配, 最优 O(n/m)
  AhoCorasick       - Aho-Corasick 多模式匹配, O(n + m + z)
  Levenshtein       - 编辑距离 (Levenshtein), O(n*m)
  DamerauLevenshtein - 编辑距离 (含相邻交换), O(n*m)
  LCS               - 最长公共子序列, O(n*m)
  LCSstr            - 最长公共子串, O(n*m)
  SorensenDice      - Sørensen-Dice 相似度
  JaroWinkler       - Jaro-Winkler 相似度
"""
from __future__ import annotations

from collections import deque
from typing import Sequence


# ===========================================================================
# KMP — Knuth-Morris-Pratt 子串匹配
# ===========================================================================

class KMP:
    """KMP 子串搜索, 预处理模式串的前缀函数 (partial match table)。

    原理:
      - 构建前缀函数 π[i] = pattern[:i] 的最长真前缀同时也是后缀的长度
      - 匹配失败时, 利用 π 跳过已知匹配部分, 避免回溯主串指针

    复杂度:
      - 预处理: O(m)
      - 搜索:   O(n)
      - 空间:   O(m)

    Example:
        >>> KMP.search("hello world", "world")  # [6]
        >>> KMP.search("aaaa", "aa")             # [0, 1, 2]
    """

    @staticmethod
    def _prefix_function(pattern: str) -> list[int]:
        """构建前缀函数 π。"""
        m = len(pattern)
        pi = [0] * m
        k = 0  # 当前最长匹配前缀长度
        for q in range(1, m):
            while k > 0 and pattern[k] != pattern[q]:
                k = pi[k - 1]
            if pattern[k] == pattern[q]:
                k += 1
            pi[q] = k
        return pi

    @staticmethod
    def search(text: str, pattern: str) -> list[int]:
        """返回 pattern 在 text 中所有匹配的起始位置 (空模式返回空列表)。"""
        if not pattern:
            return []
        n, m = len(text), len(pattern)
        if m > n:
            return []
        pi = KMP._prefix_function(pattern)
        result = []
        q = 0  # 已匹配字符数
        for i in range(n):
            while q > 0 and pattern[q] != text[i]:
                q = pi[q - 1]
            if pattern[q] == text[i]:
                q += 1
            if q == m:
                result.append(i - m + 1)
                q = pi[q - 1]
        return result

    @staticmethod
    def contains(text: str, pattern: str) -> bool:
        """判断 pattern 是否在 text 中出现。"""
        if not pattern:
            return False
        pi = KMP._prefix_function(pattern)
        q = 0
        for ch in text:
            while q > 0 and pattern[q] != ch:
                q = pi[q - 1]
            if pattern[q] == ch:
                q += 1
            if q == len(pattern):
                return True
        return False


# ===========================================================================
# Boyer-Moore — 子串匹配 (Horspool 简化版)
# ===========================================================================

class BoyerMoore:
    """Boyer-Moore-Horspool 子串搜索, 从右向左匹配, 跳过大段文本。

    原理:
      - 坏字符规则: 不匹配时, 根据该字符在模式串中的最后出现位置跳过
      - Horspool 简化: 只用坏字符规则, 每次用主串对齐窗口最右字符计算跳距

    复杂度:
      - 平均: O(n/m)  (m = 模式长度)
      - 最坏: O(n*m)
      - 空间: O(|Σ|)  (字符集大小)

    Example:
        >>> BoyerMoore.search("hello world", "world")  # [6]
    """

    @staticmethod
    def _bad_char_table(pattern: str) -> dict[str, int]:
        """坏字符跳转表: 字符 → 最后出现位置到末尾的距离。"""
        m = len(pattern)
        table: dict[str, int] = {}
        for i in range(m - 1):
            table[pattern[i]] = m - 1 - i
        return table

    @staticmethod
    def search(text: str, pattern: str) -> list[int]:
        if not pattern:
            return []
        n, m = len(text), len(pattern)
        if m > n:
            return []
        bc = BoyerMoore._bad_char_table(pattern)
        result = []
        i = 0
        while i <= n - m:
            # 从右向左比较
            j = m - 1
            while j >= 0 and pattern[j] == text[i + j]:
                j -= 1
            if j < 0:
                result.append(i)
                i += 1  # 找到后前进 1
            else:
                # 坏字符跳转
                shift = bc.get(text[i + m - 1], m)  # 用窗口最右字符
                i += max(1, shift)
        return result

    @staticmethod
    def contains(text: str, pattern: str) -> bool:
        if not pattern:
            return False
        n, m = len(text), len(pattern)
        if m > n:
            return False
        bc = BoyerMoore._bad_char_table(pattern)
        i = 0
        while i <= n - m:
            j = m - 1
            while j >= 0 and pattern[j] == text[i + j]:
                j -= 1
            if j < 0:
                return True
            shift = bc.get(text[i + m - 1], m)
            i += max(1, shift)
        return False


# ===========================================================================
# Aho-Corasick — 多模式匹配
# ===========================================================================

class AhoCorasick:
    """Aho-Corasick 自动机: 一次扫描匹配多个模式串。

    原理:
      1. 构建 Trie (goto 函数)
      2. 构建失败链接 (failure link, 类似 KMP 的 π)
      3. 构建输出链接 (output link, 记录所有匹配模式)

    复杂度:
      - 构建: O(m)  (m = 所有模式串长度之和)
      - 搜索: O(n + z)  (n = 主串长度, z = 匹配数)

    Example:
        >>> ac = AhoCorasick(["he", "she", "his", "hers"])
        >>> ac.search("ushers")  # {"she": [2], "he": [2], "hers": [3]}
    """

    class _Node:
        __slots__ = ("children", "fail", "output", "depth")
        def __init__(self, depth: int = 0):
            self.children: dict[str, AhoCorasick._Node] = {}
            self.fail: AhoCorasick._Node | None = None
            self.output: list[str] = []  # 当前节点匹配的完整模式串
            self.depth = depth

    def __init__(self, patterns: Sequence[str] | None = None):
        self._root = self._Node()
        self._patterns: list[str] = []
        self._built = False
        if patterns:
            for p in patterns:
                self.add_pattern(p)
            self._build()

    def add_pattern(self, pattern: str) -> None:
        """添加模式串 (需重新 build)。"""
        if not pattern:
            return
        self._patterns.append(pattern)
        self._built = False

    def _build(self) -> None:
        """构建失败链接和输出链接 (BFS)。"""
        root = self._root
        # 插入 Trie
        for pattern in self._patterns:
            node = root
            for ch in pattern:
                if ch not in node.children:
                    node.children[ch] = self._Node(node.depth + 1)
                node = node.children[ch]
            node.output.append(pattern)
        # BFS 构建 fail
        queue: deque[self._Node] = deque()
        for child in root.children.values():
            child.fail = root
            queue.append(child)
        while queue:
            node = queue.popleft()
            for ch, child in node.children.items():
                queue.append(child)
                # 沿 fail 链找
                f = node.fail
                while f is not None and ch not in f.children:
                    f = f.fail
                child.fail = (f.children[ch] if f else root)
                # 合并 output
                if child.fail:
                    child.output.extend(child.fail.output)
        self._built = True

    def search(self, text: str) -> dict[str, list[int]]:
        """搜索所有模式的匹配位置。

        Returns:
            {pattern: [start_positions]}

        Example:
            >>> ac = AhoCorasick(["a", "ab", "bc"])
            >>> ac.search("abc")  # {"a": [0], "ab": [0], "bc": [1]}
        """
        if not self._built:
            self._build()
        result: dict[str, list[int]] = {p: [] for p in self._patterns}
        node = self._root
        for i, ch in enumerate(text):
            while node is not self._root and ch not in node.children:
                node = node.fail  # type: ignore[assignment]
            if ch in node.children:
                node = node.children[ch]
            for pattern in node.output:
                result[pattern].append(i - len(pattern) + 1)
        return result

    def find_first(self, text: str) -> tuple[str, int] | None:
        """返回第一个匹配的 (模式串, 起始位置), 或 None。"""
        if not self._built:
            self._build()
        node = self._root
        for i, ch in enumerate(text):
            while node is not self._root and ch not in node.children:
                node = node.fail  # type: ignore[assignment]
            if ch in node.children:
                node = node.children[ch]
            if node.output:
                return (node.output[0], i - len(node.output[0]) + 1)
        return None


# ===========================================================================
# EditDistance — 编辑距离 (Levenshtein / Damerau-Levenshtein)
# ===========================================================================

class EditDistance:
    """编辑距离算法集。

    Example:
        >>> EditDistance.levenshtein("kitten", "sitting")  # 3
        >>> EditDistance.damerau_levenshtein("ca", "ac")   # 1 (交换)
    """

    @staticmethod
    def levenshtein(s1: str, s2: str) -> int:
        """Levenshtein 编辑距离 (插入/删除/替换, 各代价 1)。

        复杂度: O(n*m), 空间优化为 O(min(n,m))。
        """
        if s1 == s2:
            return 0
        if not s1:
            return len(s2)
        if not s2:
            return len(s1)
        # 确保 s1 是较短者
        if len(s1) > len(s2):
            s1, s2 = s2, s1
        n, m = len(s1), len(s2)
        prev = list(range(m + 1))  # 上一行
        curr = [0] * (m + 1)
        for i in range(1, n + 1):
            curr[0] = i
            for j in range(1, m + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                curr[j] = min(
                    prev[j] + 1,       # 删除 s1[i-1]
                    curr[j - 1] + 1,   # 插入 s2[j-1]
                    prev[j - 1] + cost # 替换
                )
            prev, curr = curr, prev
        return prev[m]

    @staticmethod
    def damerau_levenshtein(s1: str, s2: str) -> int:
        """Damerau-Levenshtein 编辑距离 (含相邻字符交换)。

        额外操作: 相邻字符交换 (代价 1)。
        复杂度: O(n*m)。
        """
        if s1 == s2:
            return 0
        if not s1:
            return len(s2)
        if not s2:
            return len(s1)
        n, m = len(s1), len(s2)
        # 完整矩阵 (需要 i-2 行, 无法 O(min) 空间优化)
        d = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n + 1):
            d[i][0] = i
        for j in range(m + 1):
            d[0][j] = j
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                d[i][j] = min(
                    d[i - 1][j] + 1,
                    d[i][j - 1] + 1,
                    d[i - 1][j - 1] + cost
                )
                # 相邻交换
                if i > 1 and j > 1 and s1[i - 1] == s2[j - 2] and s1[i - 2] == s2[j - 1]:
                    d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)
        return d[n][m]


# ===========================================================================
# LCS — 最长公共子序列
# ===========================================================================

class LCS:
    """最长公共子序列 (Longest Common Subsequence)。

    复杂度:
      - 长度: O(n*m), 空间优化 O(min(n,m))
      - 回溯: O(n*m) 空间 O(n*m)

    Example:
        >>> LCS.length("abcde", "ace")  # 3
        >>> LCS.sequence("abcde", "ace")  # "ace"
    """

    @staticmethod
    def length(s1: str, s2: str) -> int:
        """返回 LCS 长度 (空间优化 DP)。"""
        if not s1 or not s2:
            return 0
        if len(s1) > len(s2):
            s1, s2 = s2, s1
        n, m = len(s1), len(s2)
        prev = [0] * (m + 1)
        curr = [0] * (m + 1)
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if s1[i - 1] == s2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, prev
        return prev[m]

    @staticmethod
    def sequence(s1: str, s2: str) -> str:
        """返回一个 LCS (回溯完整矩阵)。"""
        if not s1 or not s2:
            return ""
        n, m = len(s1), len(s2)
        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        # 回溯
        i, j = n, m
        result = []
        while i > 0 and j > 0:
            if s1[i - 1] == s2[j - 1]:
                result.append(s1[i - 1])
                i -= 1
                j -= 1
            elif dp[i - 1][j] >= dp[i][j - 1]:
                i -= 1
            else:
                j -= 1
        result.reverse()
        return "".join(result)

    @staticmethod
    def all_sequences(s1: str, s2: str) -> list[str]:
        """返回所有 LCS (指数级, 仅用于小串)。"""
        if not s1 or not s2:
            return [""]
        n, m = len(s1), len(s2)
        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        # 回溯所有路径
        result: set[str] = set()
        def backtrack(i: int, j: int, current: list[str]) -> None:
            if i == 0 or j == 0:
                result.add("".join(reversed(current)))
                return
            if s1[i - 1] == s2[j - 1]:
                current.append(s1[i - 1])
                backtrack(i - 1, j - 1, current)
                current.pop()
            else:
                if dp[i - 1][j] == dp[i][j]:
                    backtrack(i - 1, j, current)
                if dp[i][j - 1] == dp[i][j]:
                    backtrack(i, j - 1, current)
        backtrack(n, m, [])
        return sorted(result)


# ===========================================================================
# LCSstr — 最长公共子串
# ===========================================================================

class LCSstr:
    """最长公共子串 (Longest Common Substring)。

    与 LCS 的区别: 子串必须连续, 子序列可以不连续。

    复杂度:
      - O(n*m) 时间, O(min(n,m)) 空间

    Example:
        >>> LCSstr.find("abcde", "bcdf")  # "bcd"
    """

    @staticmethod
    def find(s1: str, s2: str) -> str:
        """返回最长公共子串。"""
        if not s1 or not s2:
            return ""
        if len(s1) > len(s2):
            s1, s2 = s2, s1
        n, m = len(s1), len(s2)
        prev = [0] * (m + 1)
        max_len = 0
        max_end = 0  # s1 中的结束位置
        for i in range(1, n + 1):
            curr = [0] * (m + 1)
            for j in range(1, m + 1):
                if s1[i - 1] == s2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                    if curr[j] > max_len:
                        max_len = curr[j]
                        max_end = i
            prev = curr
        return s1[max_end - max_len : max_end]

    @staticmethod
    def length(s1: str, s2: str) -> int:
        if not s1 or not s2:
            return 0
        if len(s1) > len(s2):
            s1, s2 = s2, s1
        n, m = len(s1), len(s2)
        prev = [0] * (m + 1)
        max_len = 0
        for i in range(1, n + 1):
            curr = [0] * (m + 1)
            for j in range(1, m + 1):
                if s1[i - 1] == s2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                    max_len = max(max_len, curr[j])
            prev = curr
        return max_len


# ===========================================================================
# StringSimilarity — 字符串相似度
# ===========================================================================

class StringSimilarity:
    """字符串相似度算法集。

    Example:
        >>> StringSimilarity.sorensen_dice("night", "nacht")  # 0.25
        >>> StringSimilarity.jaro_winkler("martha", "marhta")  # 0.961...
    """

    @staticmethod
    def sorensen_dice(s1: str, s2: str, ngram: int = 2) -> float:
        """Sørensen-Dice 系数 (基于 bigram 重叠)。

        similarity = 2 * |bigrams(s1) ∩ bigrams(s2)| / (|bigrams(s1)| + |bigrams(s2)|)
        """
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        def ngrams(s: str) -> set[str]:
            return {s[i:i + ngram] for i in range(len(s) - ngram + 1)}
        a = ngrams(s1)
        b = ngrams(s2)
        if not a or not b:
            return 0.0
        intersection = len(a & b)
        return 2 * intersection / (len(a) + len(b))

    @staticmethod
    def jaro(s1: str, s2: str) -> float:
        """Jaro 相似度。

        原理:
          - 匹配窗口 = max(|s1|, |s2|)/2 - 1
          - 统计窗口内匹配字符数 m 和转置数 t
          - similarity = (m/|s1| + m/|s2| + (m-t)/m) / 3
        """
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        len1, len2 = len(s1), len(s2)
        # 匹配窗口
        window = max(len1, len2) // 2 - 1
        if window < 0:
            window = 0
        # 匹配标记
        matched1 = [False] * len1
        matched2 = [False] * len2
        m = 0
        for i in range(len1):
            start = max(0, i - window)
            end = min(len2, i + window + 1)
            for j in range(start, end):
                if not matched2[j] and s1[i] == s2[j]:
                    matched1[i] = True
                    matched2[j] = True
                    m += 1
                    break
        if m == 0:
            return 0.0
        # 转置数
        t = 0
        k = 0
        for i in range(len1):
            if not matched1[i]:
                continue
            while not matched2[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
        t //= 2
        return (m / len1 + m / len2 + (m - t) / m) / 3.0

    @staticmethod
    def jaro_winkler(s1: str, s2: str, scaling: float = 0.1) -> float:
        """Jaro-Winkler 相似度 (前缀加权)。

        Jaro-Winkler = Jaro + prefix_len * scaling * (1 - Jaro)
        """
        jaro = StringSimilarity.jaro(s1, s2)
        if jaro < 0.7:
            return jaro
        # 公共前缀长度 (最多 4)
        prefix = 0
        for c1, c2 in zip(s1, s2):
            if c1 == c2:
                prefix += 1
            else:
                break
            if prefix >= 4:
                break
        return jaro + prefix * scaling * (1 - jaro)