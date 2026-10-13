from dataclasses import dataclass
from typing import List, Union, Optional

from app.models.transcriber_model import TranscriptSegment


@dataclass
class GPTSource:
    segment: Union[List[TranscriptSegment], List]
    title: str
    tags:str
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    style: Optional[str] = None
    extras: Optional[str] = None
    _format: Optional[list] = None
    video_img_urls:  Optional[list] = None
    checkpoint_key: Optional[str] = None
    # spec 008 ticket 02：OCR 辅助模式。开启后笔记里只出现「被 LLM 判定值得编入」
    # 的画面，`approved_shots` 是判定通过的清单（WorthDecision 列表），提示词据此
    # 生成 [[SHOT-n]] 对照表；关闭时两者都不参与，提示词与行为与改动前完全一致。
    ocr_assist: Optional[bool] = False
    approved_shots: Optional[list] = None
    # m04445 pivot：判定通过的每张图 OCR 出来的**全部**内容（文字/公式/表格/版面
    # 元素/md_results），按时间点分节渲染成参考块。它进提示词只做参考，不进正文；
    # 插图与否完全由 approved_shots 决定（q8_invariant：判定通过 ＝ 实际插图）。
    ocr_reference: Optional[str] = None

