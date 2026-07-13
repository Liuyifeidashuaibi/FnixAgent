"""
排序算法 (Sorting Algorithms)
===============================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  MergeSort       - 归并排序, 稳定 O(n log n)
  QuickSort       - 快速排序, 原地 O(n log n) 平均
  HeapSort        - 堆排序, 原地 O(n log n)
  CountingSort    - 计数排序, O(n+k) 整数专用
  RadixSort       - 基数排序, O(d*(n+k)) 非比较排序
  BucketSort      - 桶排序, O(n+k) 均匀分布
  TimSortLite     - Timsort 简化版 (归并+插入混合)
  IntroSort       - 内省排序 (快排+堆排, 限制递归深度)
  PartialSort     - 部分排序 (Top-K, O(n + k log n))
  SortUtils       - 排序工具 (逆序对计数/第K大/去重排序)
"""
from __future__ import annotations

import heapq
from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


# ===========================================================================
# MergeSort — 归并排序
# ===========================================================================

class MergeSort:
    """归并排序: 稳定排序, 保证 O(n log n), 需 O(n) 额外空间。

    特点:
      - 稳定: 相等元素相对顺序不变
      - 最坏 O(n log n): 无快排的最坏退化问题
      - 适合链表/外部排序

    Example:
        >>> MergeSort.sort([3, 1, 4, 1, 5, 9, 2, 6])
        [1, 1, 2, 3, 4, 5, 6, 9]
    """

    @staticmethod
    def sort(
        arr: list[T],
        key: Callable[[T], object] | None = None,
        reverse: bool = False,
    ) -> list[T]:
        """返回排序后的新列表。"""
        if len(arr) <= 1:
            return list(arr)
        result = list(arr)
        MergeSort._merge_sort(result, 0, len(result), key)
        if reverse:
            result.reverse()
        return result

    @staticmethod
    def _merge_sort(
        arr: list[T], lo: int, hi: int, key: Callable | None
    ) -> None:
        if hi - lo <= 1:
            return
        mid = (lo + hi) // 2
        MergeSort._merge_sort(arr, lo, mid, key)
        MergeSort._merge_sort(arr, mid, hi, key)
        MergeSort._merge(arr, lo, mid, hi, key)

    @staticmethod
    def _merge(
        arr: list[T], lo: int, mid: int, hi: int, key: Callable | None
    ) -> None:
        left = arr[lo:mid]
        right = arr[mid:hi]
        i = j = 0
        k = lo
        while i < len(left) and j < len(right):
            lv = key(left[i]) if key else left[i]
            rv = key(right[j]) if key else right[j]
            if lv <= rv:
                arr[k] = left[i]
                i += 1
            else:
                arr[k] = right[j]
                j += 1
            k += 1
        while i < len(left):
            arr[k] = left[i]
            i += 1
            k += 1
        while j < len(right):
            arr[k] = right[j]
            j += 1
            k += 1


# ===========================================================================
# QuickSort — 快速排序
# ===========================================================================

class QuickSort:
    """快速排序: 原地排序, 平均 O(n log n), 最坏 O(n^2)。

    优化:
      - 三数取中选 pivot, 避免最坏情况
      - 小数组切换插入排序 (cutoff < 16)
      - 三路分区 (Dutch National Flag), 处理重复元素

    Example:
        >>> QuickSort.sort([3, 1, 4, 1, 5, 9, 2, 6])
        [1, 1, 2, 3, 4, 5, 6, 9]
    """

    _INSERTION_CUTOFF = 16

    @classmethod
    def sort(
        cls,
        arr: list[T],
        key: Callable[[T], object] | None = None,
        reverse: bool = False,
    ) -> list[T]:
        result = list(arr)
        cls._quick_sort(result, 0, len(result) - 1, key)
        if reverse:
            result.reverse()
        return result

    @classmethod
    def _quick_sort(
        cls, arr: list[T], lo: int, hi: int, key: Callable | None
    ) -> None:
        if hi - lo < cls._INSERTION_CUTOFF:
            cls._insertion_sort(arr, lo, hi, key)
            return
        if lo >= hi:
            return
        # 三数取中
        mid = (lo + hi) // 2
        cls._median_of_three(arr, lo, mid, hi, key)
        # 三路分区
        pivot = key(arr[mid]) if key else arr[mid]
        arr[mid], arr[hi - 1] = arr[hi - 1], arr[mid]
        lt, gt = lo, hi - 1
        i = lo
        while i <= gt:
            v = key(arr[i]) if key else arr[i]
            if v < pivot:
                arr[lt], arr[i] = arr[i], arr[lt]
                lt += 1
                i += 1
            elif v > pivot:
                arr[gt], arr[i] = arr[i], arr[gt]
                gt -= 1
            else:
                i += 1
        cls._quick_sort(arr, lo, lt - 1, key)
        cls._quick_sort(arr, gt + 1, hi, key)

    @classmethod
    def _median_of_three(
        cls, arr: list[T], a: int, b: int, c: int, key: Callable | None
    ) -> None:
        va = key(arr[a]) if key else arr[a]
        vb = key(arr[b]) if key else arr[b]
        vc = key(arr[c]) if key else arr[c]
        if va < vb < vc or vc < vb < va:
            arr[b], arr[c] = arr[c], arr[b]
        elif vb < va < vc or vc < va < vb:
            arr[a], arr[c] = arr[c], arr[a]

    @classmethod
    def _insertion_sort(
        cls, arr: list[T], lo: int, hi: int, key: Callable | None
    ) -> None:
        for i in range(lo + 1, hi + 1):
            temp = arr[i]
            j = i - 1
            tv = key(temp) if key else temp
            while j >= lo:
                jv = key(arr[j]) if key else arr[j]
                if jv > tv:
                    arr[j + 1] = arr[j]
                    j -= 1
                else:
                    break
            arr[j + 1] = temp


# ===========================================================================
# HeapSort — 堆排序
# ===========================================================================

class HeapSort:
    """堆排序: 原地排序, 保证 O(n log n), 不稳定。

    特点:
      - 最坏 O(n log n): 无快排退化问题
      - 原地: O(1) 额外空间
      - 缓存不友好 (跳跃式访问)

    Example:
        >>> HeapSort.sort([3, 1, 4, 1, 5, 9, 2, 6])
        [1, 1, 2, 3, 4, 5, 6, 9]
    """

    @staticmethod
    def sort(
        arr: list[T],
        key: Callable[[T], object] | None = None,
        reverse: bool = False,
    ) -> list[T]:
        result = list(arr)
        n = len(result)
        if n <= 1:
            return result
        # 建堆 (从最后一个非叶子节点开始)
        for i in range(n // 2 - 1, -1, -1):
            HeapSort._sift_down(result, i, n, key, reverse)
        # 逐个弹出 (max-heap → 升序, min-heap → 降序, 无需翻转)
        for i in range(n - 1, 0, -1):
            result[0], result[i] = result[i], result[0]
            HeapSort._sift_down(result, 0, i, key, reverse)
        return result

    @staticmethod
    def _sift_down(
        arr: list[T], i: int, n: int,
        key: Callable | None, reverse: bool
    ) -> None:
        while True:
            left = 2 * i + 1
            right = 2 * i + 2
            target = i
            for child in (left, right):
                if child >= n:
                    break
                cv = key(arr[child]) if key else arr[child]
                tv = key(arr[target]) if key else arr[target]
                if reverse:
                    if cv < tv:
                        target = child
                else:
                    if cv > tv:
                        target = child
            if target == i:
                break
            arr[i], arr[target] = arr[target], arr[i]
            i = target


# ===========================================================================
# CountingSort — 计数排序
# ===========================================================================

class CountingSort:
    """计数排序: 非比较排序, O(n+k), k 为值域范围。

    适用: 整数且值域不大 (k = O(n))。

    Example:
        >>> CountingSort.sort([3, 1, 4, 1, 5, 9, 2, 6])
        [1, 1, 2, 3, 4, 5, 6, 9]
    """

    @staticmethod
    def sort(arr: list[int], reverse: bool = False) -> list[int]:
        if not arr:
            return []
        mn, mx = min(arr), max(arr)
        range_size = mx - mn + 1
        count = [0] * range_size
        for x in arr:
            count[x - mn] += 1
        result: list[int] = []
        if reverse:
            for i in range(range_size - 1, -1, -1):
                result.extend([i + mn] * count[i])
        else:
            for i in range(range_size):
                result.extend([i + mn] * count[i])
        return result


# ===========================================================================
# RadixSort — 基数排序
# ===========================================================================

class RadixSort:
    """基数排序: LSD 低位优先, O(d*(n+k)), d 为位数。

    适用: 非负整数, 位数为常数时 O(n)。

    Example:
        >>> RadixSort.sort([170, 45, 75, 90, 802, 24, 2, 66])
        [2, 24, 45, 66, 75, 90, 170, 802]
    """

    @staticmethod
    def sort(arr: list[int], reverse: bool = False) -> list[int]:
        if not arr:
            return []
        if any(x < 0 for x in arr):
            raise ValueError("RadixSort 仅支持非负整数")
        mx = max(arr)
        result = list(arr)
        exp = 1
        while mx // exp > 0:
            result = RadixSort._counting_by_digit(result, exp)
            exp *= 10
        if reverse:
            result.reverse()
        return result

    @staticmethod
    def _counting_by_digit(arr: list[int], exp: int) -> list[int]:
        count = [0] * 10
        for x in arr:
            digit = (x // exp) % 10
            count[digit] += 1
        # 前缀和
        for i in range(1, 10):
            count[i] += count[i - 1]
        # 反向填充 (稳定)
        output = [0] * len(arr)
        for i in range(len(arr) - 1, -1, -1):
            digit = (arr[i] // exp) % 10
            count[digit] -= 1
            output[count[digit]] = arr[i]
        return output


# ===========================================================================
# BucketSort — 桶排序
# ===========================================================================

class BucketSort:
    """桶排序: 分桶后桶内排序, O(n+k) 均匀分布时。

    Example:
        >>> BucketSort.sort([0.78, 0.17, 0.39, 0.26, 0.72, 0.94, 0.21, 0.12])
        [0.12, 0.17, 0.21, 0.26, 0.39, 0.72, 0.78, 0.94]
    """

    @staticmethod
    def sort(arr: list[float], num_buckets: int = 10) -> list[float]:
        if not arr:
            return []
        mn, mx = min(arr), max(arr)
        if mx == mn:
            return list(arr)
        # 分桶
        buckets: list[list[float]] = [[] for _ in range(num_buckets)]
        scale = (num_buckets - 1) / (mx - mn)
        for x in arr:
            idx = int((x - mn) * scale)
            buckets[idx].append(x)
        # 桶内排序
        result: list[float] = []
        for bucket in buckets:
            bucket.sort()
            result.extend(bucket)
        return result


# ===========================================================================
# TimSortLite — Timsort 简化版
# ===========================================================================

class TimSortLite:
    """Timsort 简化版: 归并排序 + 自然序列检测 + 插入排序。

    原理 (Python 内置 sorted 的算法核心):
      1. 扫描自然有序的 run (升序/降序)
      2. 短 run 用插入排序补长到 minrun
      3. 用归并排序合并相邻 run, 维护栈不变量

    复杂度: 最优 O(n) (已排序), 最坏 O(n log n), 稳定。

    Example:
        >>> TimSortLite.sort([5, 1, 4, 2, 8, 3, 7, 6])
        [1, 2, 3, 4, 5, 6, 7, 8]
    """

    _MINRUN = 32

    @classmethod
    def sort(cls, arr: list[T]) -> list[T]:
        if len(arr) <= 1:
            return list(arr)
        result = list(arr)
        n = len(result)
        # 小数组直接插入排序
        if n < cls._MINRUN:
            cls._insertion_sort(result, 0, n)
            return result
        # 计算 minrun
        minrun = cls._compute_minrun(n)
        # 生成 runs
        runs: list[tuple[int, int]] = []  # (start, length)
        i = 0
        while i < n:
            run_end = cls._find_run(result, i, n)
            run_len = run_end - i
            if run_len < minrun:
                extend = min(minrun, n - i)
                cls._insertion_sort(result, i, i + extend)
                run_len = extend
            runs.append((i, run_len))
            i += run_len
            # 合并
            cls._merge_collapse(result, runs)
        # 最终合并
        cls._merge_force_collapse(result, runs)
        return result

    @staticmethod
    def _compute_minrun(n: int) -> int:
        r = 0
        while n >= 64:
            r |= n & 1
            n >>= 1
        return max(cls_MINRUN := 32, n + r)  # type: ignore

    @staticmethod
    def _find_run(arr: list[T], start: int, n: int) -> int:
        """找到自然有序 run 的结束位置。"""
        if start + 1 >= n:
            return n
        if arr[start] <= arr[start + 1]:  # 升序
            end = start + 2
            while end < n and arr[end - 1] <= arr[end]:
                end += 1
            return end
        else:  # 降序, 反转
            end = start + 2
            while end < n and arr[end - 1] > arr[end]:
                end += 1
            arr[start:end] = reversed(arr[start:end])
            return end

    @staticmethod
    def _insertion_sort(arr: list[T], lo: int, hi: int) -> None:
        for i in range(lo + 1, hi):
            temp = arr[i]
            j = i - 1
            while j >= lo and arr[j] > temp:
                arr[j + 1] = arr[j]
                j -= 1
            arr[j + 1] = temp

    @staticmethod
    def _merge(arr: list[T], start1: int, len1: int, start2: int, len2: int) -> None:
        left = arr[start1:start1 + len1]
        right = arr[start2:start2 + len2]
        i = j = 0
        k = start1
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                arr[k] = left[i]
                i += 1
            else:
                arr[k] = right[j]
                j += 1
            k += 1
        while i < len(left):
            arr[k] = left[i]
            i += 1
            k += 1
        while j < len(right):
            arr[k] = right[j]
            j += 1
            k += 1

    @classmethod
    def _merge_collapse(cls, arr: list[T], runs: list[tuple[int, int]]) -> None:
        while len(runs) >= 3:
            s1, l1 = runs[-3]
            s2, l2 = runs[-2]
            s3, l3 = runs[-1]
            if l1 <= l2 + l3 and l1 < l3:
                cls._merge(arr, s2, l2, s3, l3)
                runs[-2] = (s2, l2 + l3)
                runs.pop()
            elif l2 <= l3:
                cls._merge(arr, s1, l1, s2, l2)
                runs[-3] = (s1, l1 + l2)
                runs.pop(-2)
            else:
                break

    @classmethod
    def _merge_force_collapse(cls, arr: list[T], runs: list[tuple[int, int]]) -> None:
        while len(runs) >= 2:
            s1, l1 = runs[-2]
            s2, l2 = runs[-1]
            cls._merge(arr, s1, l1, s2, l2)
            runs[-2] = (s1, l1 + l2)
            runs.pop()


# ===========================================================================
# IntroSort — 内省排序
# ===========================================================================

class IntroSort:
    """内省排序: 快排 + 堆排, 递归深度超过 2log(n) 时切换堆排。

    特点: 保证 O(n log n) 最坏复杂度 + 快排的平均速度。
    这是 C++ std::sort 的核心算法。

    Example:
        >>> IntroSort.sort([3, 1, 4, 1, 5, 9, 2, 6])
        [1, 1, 2, 3, 4, 5, 6, 9]
    """

    @staticmethod
    def sort(arr: list[T]) -> list[T]:
        result = list(arr)
        if len(result) <= 1:
            return result
        max_depth = 2 * _log2(len(result)) + 1
        IntroSort._intro_sort(result, 0, len(result) - 1, max_depth)
        return result

    @staticmethod
    def _intro_sort(arr: list[T], lo: int, hi: int, depth: int) -> None:
        if hi - lo < 16:
            QuickSort._insertion_sort(arr, lo, hi, None)
            return
        if depth <= 0:
            # 切换堆排
            sub = arr[lo:hi + 1]
            sub = HeapSort.sort(sub)
            arr[lo:hi + 1] = sub
            return
        # 快排分区
        mid = (lo + hi) // 2
        arr[mid], arr[hi] = arr[hi], arr[mid]
        pivot = arr[hi]
        i = lo - 1
        for j in range(lo, hi):
            if arr[j] <= pivot:
                i += 1
                arr[i], arr[j] = arr[j], arr[i]
        arr[i + 1], arr[hi] = arr[hi], arr[i + 1]
        p = i + 1
        IntroSort._intro_sort(arr, lo, p - 1, depth - 1)
        IntroSort._intro_sort(arr, p + 1, hi, depth - 1)


def _log2(n: int) -> int:
    result = 0
    while n > 1:
        n >>= 1
        result += 1
    return result


# ===========================================================================
# PartialSort — 部分排序 (Top-K)
# ===========================================================================

class PartialSort:
    """部分排序: 只排序前 K 个元素, O(n + k log n)。

    比完整排序 O(n log n) 快, 适合 Top-K 场景。

    Example:
        >>> PartialSort.top_k([3, 1, 4, 1, 5, 9, 2, 6], 3)
        [9, 6, 5]
    """

    @staticmethod
    def top_k(arr: Sequence[T], k: int, reverse: bool = True) -> list[T]:
        """返回前 K 个最大 (reverse=True) 或最小 (reverse=False) 元素。"""
        if k <= 0 or not arr:
            return []
        if k >= len(arr):
            return sorted(arr, reverse=reverse)
        if reverse:
            return heapq.nlargest(k, arr)
        else:
            return heapq.nsmallest(k, arr)

    @staticmethod
    def partial_sort(arr: Sequence[T], k: int) -> list[T]:
        """前 k 个升序, 其余无序, O(n + k log n)。"""
        if k <= 0 or not arr:
            return []
        result = list(arr)
        if k >= len(result):
            result.sort()
            return result
        # 用最小堆选 k 个最小
        heap = result[:k]
        heapq.heapify(heap)
        for i in range(k, len(result)):
            if result[i] > heap[0]:
                heapq.heapreplace(heap, result[i])
        # 堆中是 k 个最小, 排序输出
        return sorted(heap)


# ===========================================================================
# SortUtils — 排序工具
# ===========================================================================

class SortUtils:
    """排序相关工具函数。

    Example:
        >>> SortUtils.count_inversions([2, 4, 1, 3, 5])
        3  # 逆序对: (2,1), (4,1), (4,3)
        >>> SortUtils.kth_largest([3, 1, 4, 1, 5, 9, 2, 6], 1)
        9
    """

    @staticmethod
    def count_inversions(arr: list[T]) -> int:
        """逆序对计数 (归并排序法), O(n log n)。"""
        if len(arr) <= 1:
            return 0
        temp = list(arr)
        return SortUtils._count_merge(temp, 0, len(temp))

    @staticmethod
    def _count_merge(arr: list[T], lo: int, hi: int) -> int:
        if hi - lo <= 1:
            return 0
        mid = (lo + hi) // 2
        count = SortUtils._count_merge(arr, lo, mid)
        count += SortUtils._count_merge(arr, mid, hi)
        left = arr[lo:mid]
        right = arr[mid:hi]
        i = j = 0
        k = lo
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                arr[k] = left[i]
                i += 1
            else:
                arr[k] = right[j]
                j += 1
                count += len(left) - i  # left[i:] 都与 right[j] 构成逆序
            k += 1
        while i < len(left):
            arr[k] = left[i]
            i += 1
            k += 1
        while j < len(right):
            arr[k] = right[j]
            j += 1
            k += 1
        return count

    @staticmethod
    def kth_largest(arr: list[T], k: int) -> T:
        """第 K 大元素 (快速选择), 平均 O(n)。"""
        if not arr or k < 1 or k > len(arr):
            raise ValueError(f"无效参数: len={len(arr)}, k={k}")
        result = list(arr)
        return SortUtils._quickselect(result, 0, len(result) - 1, len(arr) - k)

    @staticmethod
    def kth_smallest(arr: list[T], k: int) -> T:
        """第 K 小元素 (快速选择), 平均 O(n)。"""
        if not arr or k < 1 or k > len(arr):
            raise ValueError(f"无效参数: len={len(arr)}, k={k}")
        result = list(arr)
        return SortUtils._quickselect(result, 0, len(result) - 1, k - 1)

    @staticmethod
    def _quickselect(arr: list[T], lo: int, hi: int, k: int) -> T:
        while lo < hi:
            # Lomuto 分区
            pivot = arr[hi]
            i = lo - 1
            for j in range(lo, hi):
                if arr[j] <= pivot:
                    i += 1
                    arr[i], arr[j] = arr[j], arr[i]
            arr[i + 1], arr[hi] = arr[hi], arr[i + 1]
            p = i + 1
            if p == k:
                return arr[p]
            elif p < k:
                lo = p + 1
            else:
                hi = p - 1
        return arr[lo]

    @staticmethod
    def unique_sorted(arr: list[T]) -> list[T]:
        """去重并排序, O(n log n)。"""
        return sorted(set(arr))
