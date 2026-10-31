"""按供应商限流：并发量 + 每分钟最大请求数（spec 007）。

为什么需要这一层
----------------
判定层与总结层都会把一个任务拆成多个分块请求，多个笔记任务还可以并行跑。
不设限的话同一家供应商会在一瞬间收到几十个请求，直接触发 429 或网关侧封禁；
而 429 虽然可重试，但重试退避会让整条流程变得极慢且不可预期。

设计要点
--------
* **按供应商聚合，而不是按 GPT 实例**：每次生成笔记都会新建一个
  ``UniversalGPT``，如果信号量挂在实例上，等于没限制。这里用模块级字典按
  ``provider_key`` 共享一个 :class:`_ProviderLimiter`。
* **并发与速率各管一半**：信号量保证「同时在途的请求数不超过并发量」；
  匀速限流器保证「每分钟发出的请求数不超过 max_rpm」。两者取交集——
  拿到信号量之后仍要过限流器，否则并发量为 8 时一秒就能打完一分钟的额度。
* **配置变更要生效**：用户在设置页改完并发/RPM 之后，下一次调用必须用新值。
  所以 :func:`acquire` 每次都按传入的并发/RPM 检查并重建限流器（只在数值
  变化时才重建，避免每次调用都新建锁）。
* **绝不抛异常**：限流是本地的可选项，配置读不到就用默认值（并发 4，
  RPM 600——即「不限制」，保持升级前行为），不能因为限流把生成搞挂。
* **429 是「等」而不是「放弃」**（spec 012）：撞上 429 后开一个全局冷却窗口，
  所有供应商请求一起停到窗口结束，而不是各自秒级重试后判失败。详见文件末尾
  的「429 冷却窗口」一节。

调用方约定：``with provider_slot(key, concurrency=..., max_rpm=...)``。
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

#: 默认并发：与升级前行为一致（不额外限制，只挡住失控的瞬时并发）。
DEFAULT_PROVIDER_CONCURRENCY = 4

#: 默认 RPM：给一个足够大的数，等于「不限速」，避免升级后突然变慢。
DEFAULT_PROVIDER_MAX_RPM = 600

#: 并发上限，防止手改配置写出荒谬值。
PROVIDER_CONCURRENCY_MAX = 64


class _RateLimiter:
    """线程安全的匀速限流器，按每分钟请求数计算最小间隔。"""

    def __init__(self, max_per_minute: float):
        # 兜底再解析一次：这个类可能被测试或别处直接构造，不能假定调用方
        # 已经归一化过（float(None) 会直接抛 TypeError）。
        try:
            parsed = float(max_per_minute)
        except (TypeError, ValueError):
            parsed = float(DEFAULT_PROVIDER_MAX_RPM)
        self.max_per_minute = max(0.1, parsed)
        self.interval = 60.0 / self.max_per_minute
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                sleep_for = self._next_allowed - now
            else:
                sleep_for = 0.0
            # 先预约下一个时间点再释放锁，保证并发线程各自拿到不同的槽位
            self._next_allowed = max(now, self._next_allowed) + self.interval
        if sleep_for > 0:
            time.sleep(sleep_for)


class _ProviderLimiter:
    """一家供应商的并发信号量 + 速率限制。"""

    def __init__(self, concurrency: int, max_rpm: float):
        self.concurrency = concurrency
        self.max_rpm = max_rpm
        self._semaphore = threading.BoundedSemaphore(concurrency)
        self._rate = _RateLimiter(max_rpm)

    def reconfigure(self, concurrency: int, max_rpm: float) -> bool:
        """数值变了就重建。返回是否真的变了。"""
        if self.concurrency == concurrency and self.max_rpm == max_rpm:
            return False
        self.concurrency = concurrency
        self.max_rpm = max_rpm
        self._semaphore = threading.BoundedSemaphore(concurrency)
        self._rate = _RateLimiter(max_rpm)
        return True

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._semaphore:
            self._rate.wait()
            yield


_LIMITERS: Dict[str, _ProviderLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def _normalize_concurrency(value) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PROVIDER_CONCURRENCY
    if parsed <= 0:
        return DEFAULT_PROVIDER_CONCURRENCY
    return min(parsed, PROVIDER_CONCURRENCY_MAX)


def _normalize_rpm(value) -> float:
    # ``DEFAULT_PROVIDER_MAX_RPM`` 是模块级 int 常量（不是用户输入），
    # 直接用字面量兜底，避免在 fallback 路径上再调一次可能抛错的 float()。
    fallback = DEFAULT_PROVIDER_MAX_RPM * 1.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    if parsed <= 0:
        return fallback
    return parsed


def get_limiter(provider_key: str, concurrency=None, max_rpm=None) -> _ProviderLimiter:
    """取（必要时创建）某供应商的限流器。

    只在调用方**显式给出**某个额度时才改写它：``concurrency=None`` 或
    ``max_rpm=None`` 表示「这一项我不关心」，沿用该限流器已有的值（没有则用默认值）。

    为什么不能一律用默认值兜底：一个调用点只传了 concurrency、另一个只传了
    max_rpm 时，后者会把前者刚设好的并发量悄悄重置回 4。这不是假想——
    本模块自检里 ``get_limiter(key)`` 就把刚建好的「并发 2」改回了「并发 4」。
    """
    key = str(provider_key or "default")

    with _LIMITERS_LOCK:
        limiter = _LIMITERS.get(key)
        if limiter is None:
            limiter = _ProviderLimiter(
                _normalize_concurrency(concurrency),
                _normalize_rpm(max_rpm),
            )
            _LIMITERS[key] = limiter
            logger.info(
                "供应商限流：%s 并发=%d 每分钟=%s 请求",
                key,
                limiter.concurrency,
                f"{limiter.max_rpm:g}",
            )
            return limiter

        # 已经有该供应商的限流器：只改写显式传入的那一项。
        wanted_concurrency = (
            _normalize_concurrency(concurrency)
            if concurrency is not None
            else limiter.concurrency
        )
        wanted_rpm = _normalize_rpm(max_rpm) if max_rpm is not None else limiter.max_rpm
        if limiter.reconfigure(wanted_concurrency, wanted_rpm):
            logger.info(
                "供应商限流已更新：%s 并发=%d 每分钟=%s 请求",
                key,
                wanted_concurrency,
                f"{wanted_rpm:g}",
            )
        return limiter


@contextmanager
def provider_slot(
    provider_key: str,
    concurrency: Optional[int] = None,
    max_rpm: Optional[float] = None,
) -> Iterator[None]:
    """在拿到该供应商的一个并发槽位、并等过速率限制后进入。

    用法::

        with provider_slot("openai:abc", concurrency=4, max_rpm=60):
            response = client.chat.completions.create(...)
    """
    limiter = get_limiter(provider_key, concurrency=concurrency, max_rpm=max_rpm)
    # 429 冷却窗口是**全局共享**的：任何一条任务撞上 429，所有供应商请求一起停到
    # 窗口结束。放在取信号量**之前**，免得一边等冷却一边白占着并发槽位。
    wait_for_rate_limit()
    with limiter.slot():
        yield


@contextmanager
def _null_slot() -> Iterator[None]:
    """不限流的空槽位。

    用于 ``provider_key`` 为空（未配置供应商）的调用点：让
    ``with slot:`` 这条语句永远成立，不必在每个调用点写 if/else 两套代码。
    """
    yield


def reset_limiters() -> None:
    """清空限流器状态。给测试用，避免用例之间互相影响。"""
    with _LIMITERS_LOCK:
        _LIMITERS.clear()
    # 冷却窗口也是模块级共享状态，测试之间必须一起清掉，否则上一个用例留下的
    # 窗口会让下一个用例的 provider_slot 直接睡过去。
    _RATE_LIMIT_COOLDOWN.clear()


# ---------------------------------------------------------------------------
# 429 冷却窗口（spec 012）
#
# 为什么需要：供应商配额耗尽时返回 429，而升级前的逻辑只在秒级退避后就判失败 ——
# 121 条任务在配额耗尽时全数阵亡，其中 109 条甚至没被真正尝试过（熔断器把它们
# 直接标成了 FAILED）。配额恢复需要的是「等」，不是「放弃」。
#
# 设计要点：
# * **全局共享一个窗口，不是每条任务各自计时**。121 条任务各自睡 5 分钟会同时
#   醒来、同时开打，把「退避」变成「惊群」；共享窗口则所有任务等同一个时钟，
#   到点由最早醒来的那个去试探。
# * **不判失败、不计熔断**。等待期间遇到的 429 是「还没轮到」，不是「这条不行」。
# * **等满上限就交还队列**（``RATE_LIMIT_PARKED`` 哨兵），把 worker 线程让出来，
#   由恢复循环在冷却结束后重新派发 —— 而不是让 5 个 worker 各抱一条任务睡一小时，
#   把后面一百多条堵死。
# ---------------------------------------------------------------------------

#: 撞上 429 后的冷却时长（秒）。这期间所有供应商请求一起等。
RATE_LIMIT_COOLDOWN_SECONDS = float(os.getenv("RATE_LIMIT_COOLDOWN_SECONDS", "300"))

#: 单条任务为 429 连续等待的上限（秒）。超过就交还队列，不再占用 worker。
RATE_LIMIT_MAX_WAIT_SECONDS = float(os.getenv("RATE_LIMIT_MAX_WAIT_SECONDS", "3600"))

#: 恢复循环的轮询间隔（秒）。停放的任务每隔这么久探测一次配额是否恢复。
RATE_LIMIT_RESUME_INTERVAL_SECONDS = float(
    os.getenv("RATE_LIMIT_RESUME_INTERVAL_SECONDS", "300")
)


class _RateLimitCooldown:
    """进程级 429 冷却窗口。

    线程安全：``hit``/``clear``/``wait`` 都会从多个 worker 线程并发调用。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blocked_until = 0.0
        self._first_hit_at = 0.0

    def hit(self, cooldown_seconds: float, max_wait_seconds: float) -> bool:
        """记一次 429；返回「连续等待是否已达上限」。

        上限从**第一次** 429 起算，而不是从最后一次 —— 否则持续 429 会让窗口
        无限后推，「最大等待一小时」永远到不了。
        """
        now = time.monotonic()
        with self._lock:
            if self._first_hit_at <= 0.0:
                self._first_hit_at = now
            cooldown = max(0.0, cooldown_seconds)
            if cooldown > 0:
                self._blocked_until = max(self._blocked_until, now + cooldown)
            if max_wait_seconds > 0 and now - self._first_hit_at >= max_wait_seconds:
                return True
            return False

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._blocked_until - time.monotonic())

    def waited(self) -> float:
        with self._lock:
            if self._first_hit_at <= 0.0:
                return 0.0
            return max(0.0, time.monotonic() - self._first_hit_at)

    def clear(self) -> None:
        with self._lock:
            self._blocked_until = 0.0
            self._first_hit_at = 0.0

    def wait(self, chunk_seconds: float = 1.0) -> float:
        """睡到冷却窗口结束，返回实际等待秒数。

        分片睡而不是一次 ``time.sleep(300)``：窗口会被后来的 429 推后，一次睡到底
        会睡过头；分片也让 :meth:`clear` 能立刻生效（测试里把冷却设成 0 秒时不必
        真的等）。
        """
        waited = 0.0
        step = max(0.05, chunk_seconds)
        while True:
            remaining = self.remaining()
            if remaining <= 0:
                return waited
            nap = min(remaining, step)
            time.sleep(nap)
            waited += nap


_RATE_LIMIT_COOLDOWN = _RateLimitCooldown()


def note_rate_limit_hit(
    cooldown_seconds: Optional[float] = None,
    max_wait_seconds: Optional[float] = None,
) -> bool:
    """记一次 429，返回「连续等待是否已达上限」。

    返回 True 时调用方应当**交还队列**（把任务放回 PENDING 并登记到停放区），
    而不是继续占着 worker 线程等 —— 配额恢复可能需要远不止一小时。
    """
    # 未显式传参时读运行时配置（设置 → 通用），常量只是兜底。
    # 延迟 import：runtime_limits 会反向读 DB，放在函数体里避免导入期建库。
    if cooldown_seconds is None or max_wait_seconds is None:
        try:
            from app.services import runtime_limits

            if cooldown_seconds is None:
                cooldown_seconds = runtime_limits.llm_rate_limit_cooldown_seconds()
            if max_wait_seconds is None:
                max_wait_seconds = runtime_limits.llm_rate_limit_max_wait_seconds()
        except Exception:  # noqa: BLE001 - 读不到配置就用常量，绝不因此中断
            if cooldown_seconds is None:
                cooldown_seconds = RATE_LIMIT_COOLDOWN_SECONDS
            if max_wait_seconds is None:
                max_wait_seconds = RATE_LIMIT_MAX_WAIT_SECONDS
    return _RATE_LIMIT_COOLDOWN.hit(cooldown_seconds, max_wait_seconds)


def rate_limit_remaining() -> float:
    """当前冷却窗口还剩多少秒；0 表示没在冷却。"""
    return _RATE_LIMIT_COOLDOWN.remaining()


def rate_limit_waited_seconds() -> float:
    """本轮连续等待已经持续多少秒（自第一次 429 起算）。"""
    return _RATE_LIMIT_COOLDOWN.waited()


def wait_for_rate_limit(chunk_seconds: float = 1.0) -> float:
    """等到冷却窗口结束；返回实际等待秒数。没在冷却时立即返回 0。"""
    return _RATE_LIMIT_COOLDOWN.wait(chunk_seconds)


def clear_rate_limit() -> None:
    """清空冷却窗口。任何一次成功调用都应当调它。"""
    _RATE_LIMIT_COOLDOWN.clear()


def reset_rate_limit() -> None:
    """清空冷却窗口。给测试用，语义同 :func:`reset_limiters`。"""
    _RATE_LIMIT_COOLDOWN.clear()


#: 429 判定用的文案标记。转写层会把异常翻成人话 ``RuntimeError``（``status_code``
#: 之类的属性在那一层就丢了），所以不能只看属性。
_RATE_LIMIT_TEXT_MARKERS = (
    "error code: 429",
    "http 429",
    "rate limit",
    "ratelimit",
    "too many requests",
    # OpenAI 的经典 429 文案是「You exceeded your current quota」，
    # 所以只认「quota」这个词根 —— 具体措辞各家不一样，认整句必漏。
    "quota",
    "请求过于频繁",
    "配额",
)


def is_rate_limit_error(exc: BaseException) -> bool:
    """判断异常是不是供应商限流（429）。

    三条线索，按可靠性从高到低：``rate_limited`` 属性（转写层自己打的显式标记）、
    ``status_code == 429``（openai SDK 的 ``RateLimitError`` 带）、错误文案。
    最后一条不能省 —— 本项目多处把底层异常翻成 ``RuntimeError``，属性全丢。
    """
    if getattr(exc, "rate_limited", False) is True:
        return True
    if getattr(exc, "status_code", None) == 429:
        return True
    raw = str(exc).lower()
    return any(marker in raw for marker in _RATE_LIMIT_TEXT_MARKERS)
