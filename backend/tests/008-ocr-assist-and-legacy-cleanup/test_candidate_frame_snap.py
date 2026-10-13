"""回归：挑选层的时间点必须能落到真实候选帧上。

背景（生产日志实测）：挑选层只看字幕，返回 31.5 / 60.1 这类小数；interval 采样
抽出的候选帧却落在整秒上。旧实现用毫秒精确相等求交，模型挑中的点几乎全被丢弃：

    OCR 辅助挑选层：字幕分段=110 挑中=44
    挑选层命中候选帧 0/39、8/44、5/200、2/146

两次 LLM 调用（挑选 + 判定）因此白跑。这里把「吸附到最近候选帧」的语义钉死：
每个挑选点最多吸附到一个候选帧，且返回值一定是真实存在的候选帧。
"""
from app.services.note import _match_candidate_frames


def test_fractional_pick_snaps_to_the_nearest_whole_second_frame():
    """小数时间点必须吸附到最近的整秒候选帧，而不是被丢弃。"""
    candidates = [0.0, 3.0, 6.0, 9.0, 12.0]

    assert _match_candidate_frames([6.1], candidates) == [6.0]
    assert _match_candidate_frames([8.9], candidates) == [9.0]
    assert _match_candidate_frames([11.5], candidates) == [12.0]


def test_a_pick_far_from_every_frame_is_still_dropped():
    """容差之外不许硬塞：候选帧是整秒 0~12，挑到 300 秒就没有对应画面。"""
    candidates = [0.0, 3.0, 6.0, 9.0, 12.0]

    assert _match_candidate_frames([300.0], candidates) == []


def test_two_picks_near_the_same_frame_only_use_it_once():
    """一个候选帧只能被用一次，否则同一张图会被判两次。"""
    candidates = [0.0, 10.0, 20.0]

    assert _match_candidate_frames([9.6, 10.2], candidates) == [10.0]


def test_result_is_always_a_subset_of_the_candidates():
    """恒等式「候选帧 ⊇ 判定通过」必须成立：返回值只能是候选帧本身。"""
    candidates = [0.0, 3.0, 6.0, 9.0]
    matched = _match_candidate_frames([1.1, 2.9, 5.4, 8.8, 99.0], candidates)

    assert matched
    assert set(matched) <= set(candidates)
    assert matched == sorted(matched)


def test_the_real_p198_shape_now_survives():
    """失败任务 p198 的实际形态：3 秒间隔候选帧 + 模型给的 4 秒间隔挑选点。

    修复前这 5 个点里只有 60.0 / 72.0 能精确命中，其余 3 个被丢弃。
    """
    candidates = [float(t) for t in range(0, 78, 3)]
    picks = [60.0, 64.0, 68.0, 72.0, 76.0]

    matched = _match_candidate_frames(picks, candidates)

    assert matched == [60.0, 63.0, 69.0, 72.0, 75.0]


def test_empty_inputs_are_safe():
    assert _match_candidate_frames([], [1.0, 2.0]) == []
    assert _match_candidate_frames([1.0], []) == []
    assert _match_candidate_frames([], []) == []
    assert _match_candidate_frames([1.0], ["bad", None]) == []
