"""字段契约：请求模型、GPTSource、payload 白名单（spec 015 决策 4）。"""

import dataclasses

from app.models.gpt_model import GPTSource
from app.routers import note as note_module
from app.services import task_recovery, task_retry
from app.services.task_retry import PAYLOAD_KEYS
from app.services.task_recovery import _PAYLOAD_KEYS

#: VideoRequest 的 video_url 校验会跑真实平台识别，所以用一条合法的 B 站链接。
BILIBILI_URL = "https://www.bilibili.com/video/BV1xx411c7mD"


def test_video_request_exposes_scene_and_detail_without_style():
    fields = set(note_module.VideoRequest.model_fields)
    assert {"scene", "detail"} <= fields
    assert "style" not in fields


def test_batch_generate_request_exposes_scene_and_detail_without_style():
    fields = set(note_module.BatchGenerateRequest.model_fields)
    assert {"scene", "detail"} <= fields
    assert "style" not in fields


def test_gpt_source_exposes_scene_and_detail_without_style():
    names = {field.name for field in dataclasses.fields(GPTSource)}
    assert {"scene", "detail"} <= names
    assert "style" not in names


def test_payload_whitelists_carry_scene_and_detail():
    for keys in (PAYLOAD_KEYS, _PAYLOAD_KEYS):
        assert "scene" in keys
        assert "detail" in keys
        assert "style" not in keys


def test_payload_whitelists_are_the_same_contract():
    """task_retry 与 task_recovery 的白名单是同一份契约（两处注释都这么写）。"""
    assert set(PAYLOAD_KEYS) == set(_PAYLOAD_KEYS)


def test_payload_whitelist_matches_run_note_task_signature():
    """白名单里的每个键都必须是 run_note_task 能接受的参数名。

    这条防的是「改了字段名但漏改白名单」——那种漂移只在重试 / 重启恢复时才显形。
    """
    import inspect

    accepted = set(inspect.signature(note_module.run_note_task).parameters)
    assert set(PAYLOAD_KEYS) <= accepted


def test_build_task_kwargs_keys_match_the_whitelists():
    """`_build_task_kwargs` 的键去掉 task_id 必须正好等于两份白名单。

    这条防的是「改了字段名但漏改白名单」——正是 `_build_task_kwargs` 的 docstring
    点名的那种漂移（漏掉的表现是「重启后任务按默认参数重跑」）。
    """
    data = note_module.VideoRequest(
        video_url=BILIBILI_URL,
        platform="bilibili",
        quality=note_module.DownloadQuality.fast,
    )
    kwargs = note_module._build_task_kwargs("t-1", BILIBILI_URL, "bilibili", data, None)
    assert set(kwargs) - {"task_id"} == set(PAYLOAD_KEYS)
    assert set(kwargs) - {"task_id"} == set(_PAYLOAD_KEYS)
    assert kwargs["scene"] is None
    assert kwargs["detail"] is None


def test_retry_and_recovery_modules_still_export_their_entries():
    assert hasattr(task_retry, "retry_failed_tasks")
    assert hasattr(task_recovery, "start_recovery_thread")
