from app.services.task_read_model import TaskReadModel, to_task_view  # type: ignore[reportMissingImports]


def test_task_view_normalizes_legacy_status_and_actions():
    view = to_task_view("task-1", {"status": "SUCCESS", "progress": 101}, 2)
    assert view.status == "succeeded"
    # spec 005 ticket 08：终态不再折叠成 finalizing —— 折叠之后前端拿不到
    # 「最后走完的是哪一步」，12 个阶段会全部显示待处理。
    assert view.phase == "success"
    assert view.progress == 100
    assert view.actions["openNote"] is True
    assert view.actions["cancel"] is False


def test_terminal_phase_keeps_the_recorded_stage():
    """SUCCESS / FAILED 保留后端写下的真实阶段，而不是折叠成终态名。"""
    done = to_task_view("task-3", {"status": "SUCCESS", "stage": "saving"}, 1)
    assert done.phase == "saving"
    failed = to_task_view("task-4", {"status": "FAILED", "stage": "transcribing"}, 1)
    assert failed.phase == "transcribing"
    legacy_done = to_task_view("task-5", {"status": "SUCCESS", "stage": "completed"}, 1)
    assert legacy_done.phase == "finalizing"
    legacy_failed = to_task_view("task-6", {"status": "FAILED"}, 1)
    assert legacy_failed.phase == "failed"


def test_task_view_detail_is_a_mapping():
    """后端写 dict 详情（切片数 / 帧数 / 网格数），读模型必须原样透传。"""
    view = to_task_view(
        "task-7",
        {"status": "RUNNING", "detail": {"current": 3, "total": 10, "unit": "frames"}},
        1,
    )
    assert view.detail == {"current": 3, "total": 10, "unit": "frames"}
    assert to_task_view("task-8", {"status": "RUNNING"}, 1).detail is None


def test_task_view_failed_has_safe_error_shape():
    view = to_task_view(
        "task-2",
        {
            "status": "FAILED",
            "error_code": "provider_error",
            "message_key": "errors.provider",
        },
        1,
    )
    assert view.error == {
        "code": "provider_error",
        "messageKey": "errors.provider",
        "retryable": True,
    }
    assert "stack" not in view.as_dict()


def test_snapshot_revisions_change_only_when_source_changes():
    values = {"a": {"status": "RUNNING", "progress": 10}}
    model = TaskReadModel()
    reader = lambda task_id: values.get(task_id)

    first = model.snapshot(["a"], reader)
    same = model.snapshot(["a"], reader)
    values["a"] = {"status": "RUNNING", "progress": 20}
    changed = model.snapshot(["a"], reader)

    assert first["snapshotRevision"] == same["snapshotRevision"]
    assert changed["snapshotRevision"] > same["snapshotRevision"]
    assert changed["tasks"][0]["revision"] > same["tasks"][0]["revision"]

def test_task_group_events_handler_is_async():
    """The SSE handler must stay async.

    A sync generator is iterated inside Starlette's bounded worker pool, so every open
    stream parks a thread for the full 300s window. Two idle tabs were enough to starve
    that pool and make every other sync route (task list, note groups) hang while this
    one still looked healthy. Asserting the shape here keeps a later refactor from
    quietly turning it back into a thread hog.
    """
    import inspect

    from app.routers import note as note_router  # type: ignore[reportMissingImports]

    handler = note_router.get_task_groups_events
    assert inspect.iscoroutinefunction(handler)


def test_task_group_events_streams_a_first_snapshot_without_blocking():
    import asyncio

    from app.routers import note as note_router  # type: ignore[reportMissingImports]

    class _Request:
        def __init__(self):
            self.calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    async def read_first_chunk():
        response = await note_router.get_task_groups_events(_Request(), task_ids=[], since=0)
        stream = response.body_iterator
        return await stream.__anext__()

    chunk = asyncio.run(read_first_chunk())
    assert chunk.startswith("id: ")
    assert "snapshotRevision" in chunk
