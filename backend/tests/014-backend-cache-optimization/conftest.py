"""ticket 014 系列的公共测试基建。

**这是本仓库第一份 conftest.py**（此前没有 conftest / pytest.ini / pyproject.toml，
fixture 全用 pytest 内建）。新增目的只有一个：内存注册表是**跨用例的全局状态**，
同一进程里跑多个用例会互相污染，必须由基建保证隔离，而不是靠每个用例作者记得清。

约定：本 spec 的所有用例都复用这里，不要在别处另起一套。

口径提醒（写在这里，省得每个用例重复）：``app/`` 下有 Cython 编译产物，C 实现绕过
``builtins.open``，因此 **``open`` 计数偏低，``stat`` 计数才是可信口径**。任何
「是否读了盘」的断言一律以 ``stat`` 为准。
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _clean_task_status_cache():
    """每个用例前后都清空任务状态注册表。

    autouse + 前后双清：前清是为了不受上一个用例残留影响，后清是为了不让本用例
    的写入泄漏给下一个。两条都要——只清前面的话，最后一个用例的状态会留给任何
    在它之后直接调用的代码。
    """
    from app.services import task_status_cache

    task_status_cache.clear()
    try:
        yield
    finally:
        task_status_cache.clear()


@pytest.fixture(autouse=True)
def _clean_cache_env(monkeypatch):
    """隔离 ``BILINOTE_CACHE``，避免上一个用例设的开关泄漏到下一个。

    ``task_status_cache.disabled()`` 是**每次读环境变量**的（见其 docstring 的
    取舍说明），所以这里必须真的把环境变量删掉，只重置模块状态是不够的。
    """
    monkeypatch.delenv("BILINOTE_CACHE", raising=False)
    yield


@pytest.fixture(autouse=True)
def _clean_models_status_cache():
    """隔离 ``routers/config.py`` 的模型目录扫描缓存（ticket 05）。

    与任务状态注册表同理：这是跨用例的进程内全局状态，必须由基建保证隔离。
    """
    from app.routers import config

    config._invalidate_models_status_cache()
    try:
        yield
    finally:
        config._invalidate_models_status_cache()


@pytest.fixture(autouse=True)
def _clean_model_download_state():
    """隔离 ``model_download_state`` 的进程内下载状态。

    该模块没有 ``clear()``，直接快照/复原它的两个模块级 dict —— 那是它唯一的可变
    状态（见 ``backend/app/transcriber/model_download_state.py`` 的 ``_status`` /
    ``_errors``）。
    """
    from app.transcriber import model_download_state as dl_state

    saved_status = dict(dl_state._status)
    saved_errors = dict(dl_state._errors)
    dl_state._status.clear()
    dl_state._errors.clear()
    try:
        yield
    finally:
        dl_state._status.clear()
        dl_state._errors.clear()
        dl_state._status.update(saved_status)
        dl_state._errors.update(saved_errors)


@pytest.fixture
def cache_off(monkeypatch):
    """把内存快路径关掉，用于对比测量与「开关真的生效」的断言。"""
    monkeypatch.setenv("BILINOTE_CACHE", "off")
    return "off"


@pytest.fixture
def counter():
    """包装一个函数，统计它被调用的次数。

    用于断言「命中快路径时不再 stat 文件」：

        counter = counter_of(os.stat)
        count = counter(lambda: _read_task_status(tid))
        assert count.calls == 0
    """
    import functools

    class Counter:
        def __init__(self):
            self.calls = 0

        def of(self, fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                self.calls += 1
                return fn(*args, **kwargs)

            return wrapper

        def reset(self):
            self.calls = 0

    return Counter()


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    """临时结果目录（``NOTE_OUTPUT_DIR`` 的替身）。

    两个模块各持一份常量、类型还不一样，必须**分别**打补丁：
    ``routers/note.py`` 的 ``NOTE_OUTPUT_DIR`` 是 **str**（配合 ``os.path.join``），
    ``services/note.py`` 的是 **Path**（配合 ``/`` 与 ``.mkdir``）。
    """
    from app.routers import note as note_module
    from app.services import note as note_service

    directory = tmp_path / "note_results"
    directory.mkdir()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(directory))
    monkeypatch.setattr(note_service, "NOTE_OUTPUT_DIR", directory)
    return directory


@pytest.fixture
def env_without_cache():
    """确保 ``BILINOTE_CACHE`` 不在环境里（兼容不经 monkeypatch 的用例）。"""
    saved = os.environ.pop("BILINOTE_CACHE", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["BILINOTE_CACHE"] = saved
