"""OCR 辅助模式的「判定契约」（spec 008 ticket 02）。

判定与插图是两件事
------------------
旧流程里模型的判定和插图请求是同一个动作：它写出 ``*Screenshot-[mm:ss]``，系统就无条件抽帧插入。
反转后必须先有一次**结构化判定**，只有 ``worth=true`` 的候选帧才会被抽原图、送 OCR、编入笔记。

为什么判定要单独一次调用
------------------------
判定要的是干净的 JSON（``time`` / ``worth`` / ``reason`` / ``caption``），笔记要的是 Markdown 正文，
两者塞进同一次回答会互相污染。所以这里沿用 ``UniversalGPT.plan_frame_timestamps`` 的形态
（独立提示词 + 独立调用 + 复用同一套解析容错），但**不复用 ``FRAME_PLAN_PROMPT``**：
那个提示词是「选帧给多模态模型看」，服务于 hybrid 采样的配额（``HYBRID_LLM_RATIO = 0.4``），
筛选标准与目的都不同，混用会改变既有的采样行为。

时间戳必须来自候选清单
----------------------
模型凭空给一个不在候选清单里的时间点是现实风险，而照它给的秒数去抽帧等于允许任意抽帧。
所以 :func:`parse_worth_judgement` 把每条判定按**秒级取整**对齐到候选清单
（抽帧本身就是秒级精度，见 ``VideoReader.format_time``），对不上的整条丢弃并计数。

「模型说没有」与「调用失败」必须分开
------------------------------------
解析出一个 list（哪怕是空 list）＝ 合法结果，代表模型认为没有值得编入的画面；
完全捞不到 list ＝ 失败，抛 :class:`WorthJudgementError`。
两者的区别很重要：一次网络抖动不能让整篇笔记悄悄变成没有插图的笔记（spec 008 §5.6b）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.gpt.utils import load_llm_json


def _env_int(name: str, default: int) -> int:
    """读整数环境变量，值非法时退回默认值（而不是在 import 阶段炸掉）。"""
    try:
        return int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    """把不可信的值转成 float；转不了就返回默认值。

    判定链路上所有数值都来自模型输出或环境变量，类型不可信，
    所以这里刻意不用裸 ``float()``。
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """把不可信的值转成 int；转不了就返回默认值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


#: 单篇笔记的插图上限（**历史常量，仅作兜底**）。
#:
#: spec 008 §5.6d 实测既有笔记单篇插图 2~173 张（``aa5a2774``=173、``273e7b06``=66、
#: ``62858ab8``=63），反转后如果判定过松会把整篇笔记淹没在图片里，
#: 所以除了提示词里限制条数，这里再加一道硬闸门。
#:
#: 2026-10-17 起真正生效的值来自「设置 → 通用 → 单篇插图上限」（见
#: :func:`max_note_images`）：常量只在读不到设置时兜底。
MAX_NOTE_IMAGES = _env_int("NOTE_MAX_IMAGES", 30)

#: 判定时喂给模型的候选帧上限（字幕行数与候选点数都要截断，避免超出上下文）。
#: 同上：运行时的值由 :func:`max_judge_candidates` 从环境变量/常量解析。
MAX_JUDGE_CANDIDATES = _env_int("OCR_MAX_JUDGE_CANDIDATES", 200)


def max_note_images() -> int:
    """当前生效的单篇插图上限（设置页 > 环境变量 > 常量）。"""
    from app.services import runtime_limits

    return runtime_limits.note_max_images()


def max_judge_candidates() -> int:
    """当前生效的候选帧上限。

    2026-10-17：改为读运行时配置（设置页「通用 → 截图与 OCR」），环境变量
    OCR_MAX_JUDGE_CANDIDATES 仍然优先。候选越多，判定提示词越长，和图片抢的是
    同一份请求预算，所以它和 llm_max_request_bytes 是同一个旋钮的两端。
    """
    fallback = max(1, _env_int("OCR_MAX_JUDGE_CANDIDATES", MAX_JUDGE_CANDIDATES))
    try:
        from app.services import runtime_limits
    except Exception:  # noqa: BLE001 - 读不到就按历史值走
        return fallback
    try:
        return int(runtime_limits.ocr_max_judge_candidates())
    except Exception:  # noqa: BLE001
        return fallback


WORTH_JUDGE_PROMPT = """你是一个笔记插图审核员。下面会给你一段视频的字幕，以及系统已经从视频里抽出来的候选画面时间点（可能还附带这些时间点对应的画面截图）。

你的任务：逐个判断候选时间点的画面是否**值得编入笔记**。

用户的核心诉求是「尽可能多地保留关键内容和题目」。因此判断基调是**宁多勿少**：
只要画面里可能有需要留档的信息，就判 true；拿不准时一律判 true，宁可多留一张图，
也不要漏掉一个题目、一条公式或一页板书。

判定为 true（编入笔记）的情况：
- 画面里有**题目 / 例题 / 习题 / 题干 / 选项 / 答案 / 解题步骤**——哪怕只是题目的一角，也判 true
- 画面里有化学式、数学公式、物理方程等**用文字重写会失真**的内容
- 画面里有立体几何图、函数图像、坐标图、电路图等**必须看图才能理解**的图形
- 画面里有表格、数据对比、代码片段等**逐字保留才有价值**的内容
- 画面里有板书、讲义、幻灯片、知识点提纲等**手写或排版的文字信息**
- 画面里有软件界面、操作步骤演示等**截图比文字描述更省事**的内容
- 画面里的文字字幕没有完整覆盖（字幕只说了大意，画面里还有细节）

判定为 false（不要编入）的情况——只有这几种：
- 说话人的脸、手势、室内环境、实物道具等纯装饰画面，且没有任何文字或图形
- 纯 logo、片头片尾、与内容无关的转场
- 画面全黑、全白、严重模糊到看不出任何信息
- 与前后文都完全无关的画面

注意：「字幕已经表达了画面里的信息」**不足以**判 false。只要画面里有题目、
公式、表格或板书，即使字幕也提到了，仍然判 true——字幕转写经常有错别字、
会漏掉符号和下标，图才是准的。

候选时间点（共 {TOTAL} 个，视频总长 {DURATION} 秒）：
{CANDIDATES}

输出要求：
- 只输出一个 JSON 对象，不要有任何解释文字，不要用 markdown 代码块
- 格式：{"frames":[{"time":123.4,"worth":true,"reason":"画面里有求根公式","caption":"求根公式推导"}]}
- `time` 必须**原样照抄**候选清单里的数字，不要自己计算或改写
- `worth` 是布尔值 true 或 false
- `reason` 一句话说明理由（中文，30 字以内）
- `caption` 只在 worth 为 true 时给，是这张图编入笔记后的图注（中文，20 字以内）
- 每个候选时间点都要给出一条判定，一个都不能漏
- 最多只能有 {MAX_ITEMS} 个 worth 为 true；如果值得编入的超过这个数，
  优先保留「题目 / 例题 / 公式 / 表格 / 板书」，去掉最像装饰画面的那些
"""


class WorthJudgementError(RuntimeError):
    """判定调用失败（网络/鉴权）或输出完全不可识别。

    与「模型明确判定没有值得编入的画面」严格区分：后者是合法结果，只是本次
    不插图。spec 008 §5.6b 原本要求前者也让任务失败，以免静默产出无插图笔记；
    spec 022 D6 起不再如此——任务级重试会重做下载/转写/总结，代价极高而结果
    大概率一样，所以解析失败与显式空清单都降级为「保留全部候选」，由调用方
    （universal_gpt / services.note）记录 degraded 原因，任务继续跑完。
    这里保留异常类型，是因为「完全没有可解析内容」仍要能被上层识别。
    """


@dataclass
class WorthDecision:
    """一条判定通过的候选帧。"""

    time: float
    reason: str = ""
    caption: str = ""

    def describe(self) -> str:
        return f"{format_mmss(self.time)} {self.caption or self.reason}".strip()


@dataclass
class JudgementOutcome:
    """一次判定的完整结果与统计。

    统计字段存在的意义是让 spec 008 ticket 02 §6 的恒等式
    （``候选帧 ⊇ 判定通过 ⊇ 实际插入 ＝ OCR 调用数 ＝ 截图数``）在日志里可核对。
    """

    approved: List[WorthDecision] = field(default_factory=list)
    total: int = 0
    worth_true: int = 0
    worth_false: int = 0
    rejected_invalid: int = 0
    rejected_out_of_candidates: int = 0
    rejected_duplicate: int = 0
    dropped_by_cap: int = 0
    # spec 022 D6：降级原因（empty_frames 显式空清单 / parse_failed 全部批次解析失败）。
    # 非空表示 approved 是「全部候选」的兜底结果，不是模型确认过的清单。
    degraded: Optional[str] = None

    def describe(self) -> str:
        suffix = f"，降级({self.degraded})" if self.degraded else ""
        return (
            f"候选判定 {self.total} 条：true={self.worth_true} false={self.worth_false}，"
            f"丢弃(字段非法)={self.rejected_invalid} "
            f"丢弃(不在候选清单)={self.rejected_out_of_candidates} "
            f"丢弃(重复)={self.rejected_duplicate} "
            f"超出上限={self.dropped_by_cap}，"
            f"最终通过={len(self.approved)}{suffix}"
        )


def format_mmss(seconds: Any) -> str:
    """把秒数格式化成可读时间。

    超过 99 分钟时分钟位会自然变成三位（``100:05``）——这正是**不能**沿用
    ``*Screenshot-[mm:ss]`` 标记的原因：``backend/app/utils/screenshot_marker.py``
    的正则是 ``\\d{2}:\\d{2}``，超过 99 分钟的画面根本无法表达（spec 008 §5.6e）。
    占位符 ``[[SHOT-n]]`` 没有这个限制。
    """
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        total = 0
    total = max(0, total)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _as_bool(value: Any) -> Optional[bool]:
    """把模型可能给出的各种真假写法归一成 bool；认不出来返回 None。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1", "y", "需要", "是"):
            return True
        if lowered in ("false", "no", "0", "n", "不需要", "否"):
            return False
    return None


def _as_seconds(value: Any) -> Optional[float]:
    """把模型给出的时间值转成秒；认不出来返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _safe_float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # 允许 "01:23" / "1:02:03" 这种形态，模型偶尔会照抄成时间码
        if ":" in text:
            parts = text.split(":")
            try:
                numbers = [float(p) for p in parts]
            except ValueError:
                return None
            total = 0.0
            for number in numbers:
                total = total * 60 + number
            return total
        try:
            return float(text)
        except ValueError:
            return None
    return None


def build_candidate_index(candidates: Iterable[Any]) -> Dict[int, float]:
    """把候选时间点整理成 ``{整秒: 原始秒数}``。

    以整秒为键是因为抽帧本身就是秒级精度：``VideoReader`` 用
    ``round(float(raw_ts), 3)`` 去重、``format_time`` 把整秒写成 ``MM_SS``。
    对齐时只认整秒，模型写 ``123.4`` 与 ``123`` 会落到同一个候选点上。
    """
    index: Dict[int, float] = {}
    for raw in candidates or []:
        seconds = _as_seconds(raw)
        if seconds is None or seconds < 0:
            continue
        key = _safe_int(round(_safe_float(seconds)))
        index.setdefault(key, seconds)
    return index


def build_candidates_text(candidates: Sequence[Any]) -> str:
    """渲染候选清单，作为提示词里模型必须照抄的对照表。"""
    lines = []
    for raw in list(candidates or [])[:max_judge_candidates()]:
        seconds = _as_seconds(raw)
        if seconds is None:
            continue
        lines.append(f"- {seconds} （{format_mmss(seconds)}）")
    return "\n".join(lines) if lines else "- （没有候选画面）"


def build_judge_system_prompt(
    candidates: Sequence[Any], duration: float = 0.0, max_items: int | None = None
) -> str:
    """拼出判定用的 system prompt。

    用 ``replace`` 而不是 ``format``：模板里有 JSON 示例的花括号。
    """
    usable = [c for c in (candidates or []) if _as_seconds(c) is not None]
    return (
        WORTH_JUDGE_PROMPT.replace("{TOTAL}", str(len(usable)))
        .replace("{DURATION}", str(_safe_int(duration)))
        .replace("{CANDIDATES}", build_candidates_text(usable))
        .replace("{MAX_ITEMS}", str(max(1, _safe_int(max_items if max_items is not None else max_note_images(), 1))))
    )


def render_shot_table(approved: Sequence[WorthDecision]) -> str:
    """渲染「编号占位符 → 时间点」对照表，供笔记提示词使用。

    编号是插入的唯一凭据：模型只能用表里的 ``[[SHOT-n]]``，
    于是「插入了未判定的帧」在结构上不可能发生。
    """
    lines = []
    for index, decision in enumerate(approved, 1):
        caption = decision.caption or decision.reason or "画面要点"
        lines.append(f"- `[[SHOT-{index}]]` → {format_mmss(decision.time)}（{caption}）")
    return "\n".join(lines)


def extract_judgement_items(text: str) -> List[Any]:
    """从一段判定响应里取出条目列表，**不抛异常**。

    这是判定层分块（spec 008 ticket 02 §7）的配套函数：判定请求按字节预算拆成
    多批之后，每批各自返回一段文本，需要先取出条目、汇集起来，最后在完整候选
    清单上只调一次 :func:`parse_worth_judgement`。

    与 :func:`parse_worth_judgement` 的分工是本函数**宽容**、后者**严格**：
    单批解析不出来时这里返回空清单，让那一批静默作废而不是毁掉整轮判定；
    严格性集中在最后一次解析上——如果所有批次都没取出条目，调用方会抛
    ``WorthJudgementError``，任务照常失败（spec 008 §5.6b）。

    :param text: 模型返回的原始文本
    :return: 条目列表；解析不出来时返回空清单
    """
    try:
        data = load_llm_json(text)
    except Exception:
        return []
    if data is None:
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("frames", "results", "items", "judgements", "judgments", "data", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        if "time" in data or "timestamp" in data or "start" in data:
            # 模型只给了一条判定、且直接给了对象本身
            return [data]
    return []


def _degraded_outcome(
    candidates: Iterable[Any],
    reason: str,
    max_images: int | None = None,
) -> JudgementOutcome:
    """判定降级：把全部候选帧当作「值得编入」（spec 022 D6）。

    去重、排序、上限截断都走与正常路径相同的口径，只是 worth 全部视为 true，
    并在 reason 里写明这是降级兜底，免得用户以为模型真的确认过这些画面。
    """
    outcome = JudgementOutcome(degraded=reason)
    times: List[float] = []
    seen: set = set()
    for candidate in candidates or []:
        seconds = _as_seconds(candidate)
        if seconds is None:
            continue
        key = _safe_int(round(seconds))
        if key in seen:
            continue
        seen.add(key)
        times.append(float(seconds))
    times.sort()
    outcome.total = len(times)
    limit = max(
        0, _safe_int(max_images if max_images is not None else max_note_images())
    )
    decisions = [
        WorthDecision(time=t, reason="画面判定降级：保留全部候选") for t in times
    ]
    if len(decisions) > limit:
        outcome.dropped_by_cap = len(decisions) - limit
        decisions = decisions[:limit]
    outcome.approved = decisions
    outcome.worth_true = len(decisions)
    return outcome


def parse_worth_judgement(
    text: str,
    candidates: Iterable[Any],
    max_images: int | None = None,
) -> JudgementOutcome:
    """解析判定结果并把它对齐到候选清单。

    :param text: 模型返回的原始文本
    :param candidates: 候选时间点（秒），即 ``VideoReader.candidate_timestamps``
    :param max_images: 通过判定的帧数上限
    :raises WorthJudgementError: 文本完全不是 JSON / 找不到帧列表字段时

    spec 022 D6：显式空清单（frames 为空数组）不再视为「不插图」，而是降级为
    「保留全部候选」——空清单与「模型什么都没说清楚」在输出上无法区分，而
    一篇文章因为一次空回复丢掉全部插图，比多留几张图更糟。
    """
    data = load_llm_json(text)
    if data is None:
        raise WorthJudgementError("判定结果不是合法 JSON，无法解析")

    items: Optional[List[Any]] = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("frames", "results", "items", "judgements", "judgments", "data", "list"):
            value = data.get(key)
            if isinstance(value, list):
                items = value
                break
        if items is None and ("time" in data or "timestamp" in data or "start" in data):
            # 模型只给了一条判定、且直接给了对象本身
            items = [data]
    if items is None:
        raise WorthJudgementError("判定结果里找不到帧列表（既不是数组，也没有 frames 字段）")
    if not items:
        # spec 022 D6：显式空清单降级为保留全部候选。
        return _degraded_outcome(candidates, "empty_frames", max_images)

    index = build_candidate_index(candidates)
    outcome = JudgementOutcome()
    seen: set = set()

    for item in items:
        if not isinstance(item, dict):
            outcome.rejected_invalid += 1
            continue
        outcome.total += 1

        seconds = _as_seconds(item.get("time", item.get("timestamp", item.get("start"))))
        worth = _as_bool(item.get("worth", item.get("needed", item.get("keep"))))
        if seconds is None or worth is None:
            outcome.rejected_invalid += 1
            continue

        if not worth:
            outcome.worth_false += 1
            continue
        outcome.worth_true += 1

        key = _safe_int(round(_safe_float(seconds)))
        if key not in index:
            # 模型自己编了一个候选清单里没有的时间点——丢弃，绝不为它抽帧
            outcome.rejected_out_of_candidates += 1
            continue
        if key in seen:
            outcome.rejected_duplicate += 1
            continue
        seen.add(key)

        outcome.approved.append(
            WorthDecision(
                time=index[key],
                reason=str(item.get("reason") or "").strip(),
                caption=str(item.get("caption") or "").strip(),
            )
        )

    outcome.approved.sort(key=lambda decision: decision.time)

    limit = max(0, _safe_int(max_images if max_images is not None else max_note_images()))
    if len(outcome.approved) > limit:
        outcome.dropped_by_cap = len(outcome.approved) - limit
        outcome.approved = outcome.approved[:limit]

    return outcome


# ---------------------------------------------------------------------------
# OCR 结果分流（m02915：q_ocr_signal_scope = 扩到所有非 image 类）
# ---------------------------------------------------------------------------

#: glm-ocr 托管 API 的 ``label`` 枚举。见 ``tickets/01-api-verification.md`` §8。
#:
#: 枚举是封闭的 4 种：SDK 自托管层有 10 种细粒度 label，但经
#: ``pipeline.result_formatter.label_visualization_mapping`` 归并后才会暴露给直连 API。
OCR_LABEL_IMAGE = "image"
OCR_LABEL_FORMULA = "formula"
OCR_LABEL_TABLE = "table"
OCR_LABEL_TEXT = "text"

#: 引用块的标题：按 label 分出「公式/表格」与「普通文字」两档，便于阅读时区分。
_QUOTE_HEADINGS: Dict[str, str] = {
    OCR_LABEL_FORMULA: "公式",
    OCR_LABEL_TABLE: "表格",
}


def _block_label(block: Any) -> str:
    """取一个 ``layout_details`` 元素的 label，归一成小写字符串。"""
    if isinstance(block, dict):
        raw = block.get("label")
    else:
        raw = getattr(block, "label", None)
    return str(raw or "").strip().lower()


def _block_page(block: Any) -> int:
    """取 ``layout_details`` 元素所属页号；取不到按 0。"""
    if isinstance(block, dict):
        return _safe_int(block.get("page", block.get("page_index", 0)))
    return _safe_int(getattr(block, "page", 0))


def _block_content(block: Any) -> str:
    """取 ``layout_details`` 元素的正文。

    注意判定写的是 **值是否为空**，不是键是否存在：``label == "image"`` 的
    元素带 ``content`` 键但值恒为 ``null``，用 ``"content" in block`` 会把每
    张插图都误判成「读出了内容」。
    """
    if isinstance(block, dict):
        raw = block.get("content")
    else:
        raw = getattr(block, "content", None)
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    return str(raw).strip()


@dataclass
class OcrReading:
    """一次识别的分流结果（spec 008 ticket 02 §4）。"""

    has_content: bool = False                      # 读出了可编入笔记的内容？
    labels: List[str] = field(default_factory=list)  # 全部元素 label（去重、保序）
    parts: List[str] = field(default_factory=list)   # 非 image 类有正文的部分
    part_labels: List[str] = field(default_factory=list)  # 与 parts 一一对应的 label
    content_chars: int = 0                           # 正文总字符数

    @property
    def label_text(self) -> str:
        return ",".join(self.labels) if self.labels else "(无元素)"

    @property
    def distinct_part_labels(self) -> List[str]:
        """有正文的那几段各是什么 label（去重、保序）。

        标题只该看这几段：``layout_details`` 里几乎每张图都带一个
        ``label == "image"`` 的插图元素，把它算进 ``labels`` 会让「只有一种
        label」永远不成立，公式标题也就永远退化成「内容」。
        """
        seen: List[str] = []
        for label in self.part_labels:
            if label and label not in seen:
                seen.append(label)
        return seen


def classify_ocr_result(result: Any) -> OcrReading:
    """把一次 OCR 结果分流成「读出内容」或「读不出内容」。

    分流规则（m02915 ``q_ocr_signal_scope`` 拍板）：

    * 遍历 ``layout_details`` 全部元素，**除 ``label == "image"`` 外，
      任何 label 只要有非空 content 就算读出了内容**；
    * 只要读出了内容，这张图就**不插图**，读出的内容作为引用块回填到占位符；
    * 一个元素都没读出内容 → **插图**（画面本身承载了信息，只能靠看图）。

    为什么不是「只看 formula/table」：``label == "image"`` 恒 ``content: null``
    （ticket 01 §8，A 级），所以 formula/table 与插图互斥成立；但反过来有洞——
    幻灯片整页、代码截图会被识别成 ``label == "text"`` 并带回大段文字，
    只查 formula/table 会让这类图仍然被当插图插进笔记，用户要的「文字内容进正文」
    就落空了。

    引用块一律**原文搬运**：不猜 ``formula`` 的 content 是 LaTeX 还是纯文本
    （ticket 01 §7 残余风险第 6 条），也不替用户加 ``$$`` 数学标记。
    """
    blocks = getattr(result, "blocks", None) or []
    reading = OcrReading()

    for block in blocks:
        label = _block_label(block)
        if label and label not in reading.labels:
            reading.labels.append(label)
        if label == OCR_LABEL_IMAGE:
            continue
        content = _block_content(block)
        if not content:
            continue
        reading.parts.append(content)
        reading.part_labels.append(label)
        reading.content_chars += len(content)

    reading.has_content = bool(reading.parts)
    return reading


def _quote_heading(reading: OcrReading, element_index: int, part_count: int) -> str:
    """给一段引用内容挑标题。

    看的是**有正文的那几段的 label**（``distinct_part_labels``），不是全部元素的
    label：``layout_details`` 里几乎每张图都带一个 ``label == "image"`` 的插图
    元素，若把它算进来，「只有一种 label」在真实数据上永远不成立，公式标题也就
    永远退化成「内容」。

    单 label 时用 ``_QUOTE_HEADINGS`` 里的中文名（公式 / 表格）；``text`` 这种
    没有专属名字的、或者一幅图里混了多种 label 时退化成 ``内容``。
    序号只在多段时出现。
    """
    part_labels = reading.distinct_part_labels
    if len(part_labels) == 1 and part_count == 1:
        named = _QUOTE_HEADINGS.get(part_labels[0])
        if named:
            return named
    if len(part_labels) == 1:
        named = _QUOTE_HEADINGS.get(part_labels[0])
        if named and part_count > 1:
            # 多段同一种 label（例如整页都是公式）时也要带序号，否则每段标题都一样
            return f"{named} {element_index}"
    return f"内容 {element_index}" if part_count > 1 else "内容"


def build_ocr_quote(reading: OcrReading) -> str:
    """把分流结果渲染成回填用的 Markdown 引用块（不插图）。

    每一段都带 label 标题（用户 m03045 拍板）：读者要能一眼看出这段文字是 OCR
    从图上抄回来的，而不是模型自己写的正文。单段时标题不带序号，多段时才编号。
    """
    if not reading.has_content:
        return ""

    part_count = len(reading.parts)
    lines: List[str] = []
    for element_index, part in enumerate(reading.parts, 1):
        heading = _quote_heading(reading, element_index, part_count)
        lines.append(f"> **{heading}**")
        lines.extend(_quote_lines(part))
        lines.append(">")
    while lines and lines[-1] == ">":
        lines.pop()
    return chr(10).join(lines)


def build_ocr_reference(shots: List[Any], readings: Optional[Dict] = None) -> str:
    """把判定通过的每张图的 OCR 结果汇总成「参考内容」块（m04445）。

    送进去的是**全部输出**（q1_ocr_payload=A）：非 image 类元素的 content、所有
    元素的 label 与 bbox、以及 ``md_results`` 原文。三者口径不同、互为补充：

      - ``content``：图上抄回来的正文，公式是 LaTeX，可被模型直接引用；
      - ``label`` + ``bbox``：告诉模型「这张图里哪块是插图、哪块是公式」，
        没有它模型只会看到一串孤立的文字，不知道版面结构；
      - ``md_results``：上游自己排过版的 markdown，兜底那些 blocks 里没体现的内容。

    为什么按时间点分节而不是拼成一坨（q2_inject_shape=A）：模型要能把参考内容
    对应回正文里的 ``[[SHOT-n]]``，时间点就是唯一的锚。分节之后它可以自然地写出
    「在 03:21 的板书里……」这样的句子。

    ``readings`` 是「时间点 → OcrResult」的映射，按 ``shot.time`` 取。取不到
    （OCR 关了、或这一张 OCR 失败）时仍要出一节——只写「无」而不是整节删掉：
    模型要知道「这张图值得编入笔记、但没抄出文字」，否则它会以为那张图不存在，
    从而漏掉本该配图的段落。

    :param shots: 判定通过的清单（WorthDecision），顺序即 ``[[SHOT-n]]`` 编号
    :param readings: 时间点 → OcrResult；缺失时按「无结果」渲染
    """
    readings = readings or {}
    sections: List[str] = []
    for index, shot in enumerate(shots or [], 1):
        at = format_mmss(float(getattr(shot, "time", 0.0) or 0.0))
        lines: List[str] = [f"### [[SHOT-{index}]] @ {at}"]

        reason = str(getattr(shot, "reason", "") or "").strip()
        caption = str(getattr(shot, "caption", "") or "").strip()
        if reason:
            lines.append(f"- 判定理由：{reason}")
        if caption:
            lines.append(f"- 说明：{caption}")

        reading = readings.get(float(getattr(shot, "time", 0.0) or 0.0))
        lines.extend(_reference_body(reading))
        sections.append(chr(10).join(lines))

    return chr(10).join(sections)


def _collect_parts(reading: Any) -> tuple:
    """从一次 OCR 结果里取出「有正文的段落」及其 label。

    为什么要在这里现算：`_run_ocr_stage` 存进缓存的是 **OcrResult**（q1 要它的
    blocks 与 raw.md_results），而 ``parts`` / ``part_labels`` 只存在于
    **OcrReading**。只读 `reading.parts` 会恒为空，参考块会静默退化成
    「图上没有可提取的文字」——测试就是这么抓出来的。

    判据与 :func:`classify_ocr_result` 保持一致：**跳过 ``label == "image"``**
    （它恒 ``content: null``，是插图元素而非正文），其余 label 只要有非空
    content 就算一段。两处口径必须一致，否则「判定读出了内容」与「参考块里写的
    东西」会对不上。

    :return: ``(parts, part_labels)``，两个等长列表
    """
    parts = [str(p) for p in (getattr(reading, "parts", None) or []) if str(p).strip()]
    if parts:
        # OcrReading 路径：自带 parts，直接用
        labels = [str(x or "") for x in (getattr(reading, "part_labels", None) or [])]
        return parts, labels

    collected: List[str] = []
    collected_labels: List[str] = []
    for block in getattr(reading, "blocks", None) or []:
        label = str(getattr(block, "label", "") or "")
        if label == "image":
            continue
        content = getattr(block, "content", None)
        if content is None:
            continue
        text = str(content).strip()
        if not text:
            continue
        collected.append(text)
        collected_labels.append(label)
    return collected, collected_labels


def _reference_body(reading: Any) -> List[str]:
    """渲染单张图的 OCR 明细；``reading`` 缺失或没内容时返回「无」的说明。"""
    if reading is None:
        return ["- OCR：未返回结果（该图仍会插入笔记）"]

    raw = getattr(reading, "raw", None) or {}
    blocks = getattr(reading, "blocks", None) or []
    markdown = str(
        raw.get("md_results") or (reading.markdown if hasattr(reading, "markdown") else "") or ""
    ).strip()

    parts, part_labels = _collect_parts(reading)
    if not parts and not markdown:
        return ["- OCR：图上没有可提取的文字（该图仍会插入笔记）"]

    lines: List[str] = []
    for idx, part in enumerate(parts, 1):
        label = part_labels[idx - 1] if idx - 1 < len(part_labels) else ""
        head = f"  第 {idx} 段" + (f"（{label}）" if label else "")
        lines.append(f"- 内容{head}：")
        lines.extend(f"    {ln}" for ln in part.splitlines() if ln.strip())

    geometry: List[str] = []
    for block in blocks:
        label = str(getattr(block, "label", "") or "")
        bbox = getattr(block, "bbox", None)
        if not label and not bbox:
            continue
        if bbox:
            geometry.append(f"    {label or '(无标签)'} bbox={list(bbox)}")
        else:
            geometry.append(f"    {label or '(无标签)'} bbox=(未知)")
    if geometry:
        lines.append("- 版面元素：")
        lines.extend(geometry)

    if markdown:
        lines.append("- md_results 原文：")
        lines.extend(f"    {ln}" for ln in markdown.splitlines() if ln.strip())

    return lines


def _quote_lines(text: str) -> List[str]:
    """把一段文字逐行渲染成 Markdown 引用行。"""
    rendered = [f"> {line}" for line in (text or "").splitlines() if line.strip()]
    return rendered
