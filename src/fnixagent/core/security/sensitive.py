"""
敏感词检测 — DFA 确定性有限自动机。

算法原理:
  将敏感词库构建为 Trie 树(嵌套字典),每个节点是一个状态:
    {"跳": {"楼": {"_END_": True}}}
  检测时,对输入文本逐字符在 DFA 中做状态转移:
    - 匹配到下一字符 → 进入子节点
    - 到达终结状态(_END_) → 命中一个敏感词
    - 不匹配 → 回到根节点重新开始(或跳过干扰字符)
  复杂度 O(n × m),n=文本长度,m=最长敏感词长度,但实际接近 O(n)。

模糊匹配增强:
  敏感词中间穿插空白/标点也能命中(如 "敏 感 词" 匹配 "敏感词")。
  实现: 遇到非字母数字字符时跳过,不消耗 DFA 状态。
"""

from __future__ import annotations

import threading

_END = "\x00"  # 终结标记


class SensitiveDetector:
    """
    基于 DFA 的多模式敏感词检测器。

    用法:
        det = SensitiveDetector()
        det.add_words(["敏感词1", "敏感词2"])
        hits = det.detect("这里有敏感词1")
        masked = det.mask("这里有敏感词1")  # "这里有***"
    """

    def __init__(self) -> None:
        self._root: dict = {}
        self._lock = threading.Lock()
        self._word_count = 0

    # -- 构建 DFA ----------------------------------------------------------

    def add_words(self, words: list[str]) -> int:
        """批量添加敏感词,构建 DFA Trie。

        Args:
            words: 敏感词列表(空白词自动跳过)

        Returns:
            实际添加的词数
        """
        added = 0
        with self._lock:
            for word in words:
                word = word.strip()
                if not word:
                    continue
                node = self._root
                for ch in word:
                    if ch not in node:
                        node[ch] = {}
                    node = node[ch]
                node[_END] = True
                added += 1
                self._word_count += 1
        return added

    def add_word(self, word: str) -> None:
        """添加单个敏感词。

        Args:
            word: 敏感词(非空)
        """
        self.add_words([word])

    def load_default_words(self) -> int:
        """加载内置基础敏感词表(少量示例)。

        业务层可通过 add_words 扩充完整词库。

        Returns:
            添加的词数
        """
        default = [
            "赌博",
            "色情",
            "毒品",
            "诈骗",
            "暴力",
            "枪支",
            "弹药",
            "炸弹",
            "黑客",
            "攻击",
        ]
        return self.add_words(default)

    def clear(self) -> None:
        """清空词库。"""
        with self._lock:
            self._root = {}
            self._word_count = 0

    @property
    def word_count(self) -> int:
        """当前词库中敏感词总数。"""
        return self._word_count

    # -- 检测 --------------------------------------------------------------

    @staticmethod
    def _is_skip_char(ch: str) -> bool:
        """判断是否为可跳过的干扰字符(空白/标点/符号)。

        敏感词中间穿插这些字符仍可匹配(如 "敏 感 词" 匹配 "敏感词")。

        Args:
            ch: 单个字符

        Returns:
            True 表示可跳过(非字母数字)
        """
        if ch.isalnum():
            return False
        return True

    def detect(self, text: str) -> list[tuple[str, int, int]]:
        """检测文本中的敏感词。

        使用 DFA 状态机逐字符匹配,跳过干扰字符(空白/标点)。
        命中后记录最长匹配,并从命中末尾继续扫描。

        Args:
            text: 待检测文本

        Returns:
            [(word, start, end), ...],start/end 为原始文本索引
        """
        if not text or not self._root:
            return []
        results: list[tuple[str, int, int]] = []
        n = len(text)
        i = 0

        while i < n:
            node = self._root
            j = i
            last_hit_end = -1
            last_hit_word = ""

            # 从 i 开始尝试匹配(贪心最长匹配)
            while j < n:
                ch = text[j]
                # 跳过干扰字符(不消耗 DFA 状态)
                if self._is_skip_char(ch):
                    j += 1
                    continue
                if ch in node:
                    node = node[ch]
                    j += 1
                    # 检查是否到达终结状态(_END 标记)
                    if _END in node:
                        last_hit_end = j
                        last_hit_word = text[i:j]
                else:
                    break

            if last_hit_end > 0:
                # 命中:记录并跳到命中末尾继续扫描
                results.append((last_hit_word, i, last_hit_end))
                i = last_hit_end
            else:
                i += 1

        return results

    def contains(self, text: str) -> bool:
        """是否包含敏感词。

        Args:
            text: 待检测文本

        Returns:
            True 表示包含至少一个敏感词
        """
        return len(self.detect(text)) > 0

    def mask(self, text: str, mask_char: str = "*") -> str:
        """将敏感词替换为掩码字符。

        保留长度,如 "敏感词" → "***"。

        Args:
            text: 原始文本
            mask_char: 掩码字符(默认 "*")

        Returns:
            敏感词被替换为掩码后的文本
        """
        hits = self.detect(text)
        if not hits:
            return text
        result = list(text)
        for word, start, end in hits:
            for k in range(start, end):
                result[k] = mask_char
        return "".join(result)
