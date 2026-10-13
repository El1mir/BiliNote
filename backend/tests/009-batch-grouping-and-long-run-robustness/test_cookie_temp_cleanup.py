"""spec 009 ticket 05：BilibiliDownloader 的 Cookie 临时文件生命周期。

为什么这么测：

* 被修复的 bug 不是「文件没删」，而是「文件在**构造期**就写出来了」。单例
  （``app/services/constant.py`` 里的 ``BilibiliDownloader``）跟着进程活多久，
  这个含 live SESSDATA 的 ``*.txt`` 就在 %TEMP% 里躺多久，而全仓没有删除点。
  所以本文件既测「用完即删」，也单独测「构造期不再落盘」—— 后者才是真正的
  回归点。
* ``BilibiliDownloader()`` 的 ``__init__`` 会走 ``CookieConfigManager`` 读
  ``config/downloader.json``。这里不依赖那份真实配置：先构造实例，再用
  ``monkeypatch`` 覆写 ``_cookie``。之所以能这么做，是因为构造期已经不碰
  Cookie 了（这正是被修的行为），所以构造时读到的值无关紧要。
* 删除失败的告警路径不能靠「等它自然失败」来测：把 ``os.remove`` 换成抛
  ``OSError`` 才能稳定覆盖。
"""

import os
from typing import Optional
from unittest import mock

from app.downloaders import bilibili_downloader as dl_module
from app.downloaders.bilibili_downloader import BilibiliDownloader

FAKE_COOKIE = "SESSDATA=fake; bili_jct=abc"


def _downloader(monkeypatch, cookie: Optional[str] = FAKE_COOKIE):
    """造一个下载器并把 ``_cookie`` 钉成假串，避免依赖真实配置。"""
    downloader = BilibiliDownloader()
    monkeypatch.setattr(downloader, "_cookie", cookie, raising=False)
    return downloader


def test_cookie_file_is_created_then_removed(monkeypatch):
    downloader = _downloader(monkeypatch)

    with downloader._cookie_file() as path:
        # `_cookie` 非空时必定返回路径；断言同时让类型检查器窄化掉 Optional。
        assert isinstance(path, str)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        # Netscape 头 + 真实 cookie 键都要在，否则 yt-dlp 读不了。
        assert "# Netscape HTTP Cookie File" in content
        assert "SESSDATA" in content
        assert ".bilibili.com" in content
        created = path

    # 退出 with 之后必须已经删掉 —— 这是整个修复的核心。
    assert not os.path.exists(created)


def test_cookie_file_is_removed_on_exception(monkeypatch):
    """异常路径同样要删。

    yt-dlp 的失败路径（网络异常、格式选择失败、任务被取消）都从这里经过，
    只有 ``finally`` 语义才能保证不泄漏；「下载完再删」的实现会在这里漏文件。
    """
    downloader = _downloader(monkeypatch)
    created: Optional[str] = None

    try:
        with downloader._cookie_file() as path:
            assert isinstance(path, str)
            created = path
            assert os.path.exists(path)
            raise RuntimeError("模拟 yt-dlp 中途失败")
    except RuntimeError:
        pass
    else:  # pragma: no cover - 异常必须原样冒泡，不能被上下文管理器吞掉
        raise AssertionError("_cookie_file 吞掉了块内的异常")

    assert created is not None
    assert not os.path.exists(created)


def test_no_cookie_yields_none_and_writes_nothing(monkeypatch):
    """未配置 Cookie 时产出 None，且不创建任何临时文件。

    yt-dlp 的 ``cookiefile=None`` 表示「不带 cookie」，所以这里必须是 None
    而不是空字符串路径。
    """
    downloader = _downloader(monkeypatch, cookie=None)

    with mock.patch.object(dl_module.tempfile, "NamedTemporaryFile") as named_tmp:
        with downloader._cookie_file() as path:
            assert path is None
        named_tmp.assert_not_called()


def test_remove_cookie_file_tolerates_none_and_missing_path(tmp_path):
    """``None`` 与不存在的路径都算「已经清理干净」，不能抛。"""
    BilibiliDownloader._remove_cookie_file(None)
    BilibiliDownloader._remove_cookie_file(str(tmp_path / "never-existed.txt"))


def test_remove_cookie_file_warns_but_does_not_raise(monkeypatch, tmp_path):
    """删除失败只告警不抛 —— 清理失败不该把整个笔记任务带崩。"""
    target = tmp_path / "locked.txt"
    target.write_text("SESSDATA=fake", encoding="utf-8")

    def boom(path):
        raise OSError("文件被占用")

    monkeypatch.setattr(dl_module.os, "remove", boom)
    with mock.patch.object(dl_module.logger, "warning") as warning:
        # 不抛异常即为通过（失败时这里会直接冒泡让测试红）。
        BilibiliDownloader._remove_cookie_file(str(target))
    assert warning.called


def test_constructor_does_not_write_any_cookie_file(monkeypatch):
    """构造期不再落盘 —— 这是 ticket 05 真正修掉的那个泄漏。

    为什么用「记录 NamedTemporaryFile 调用」而不是「断言某个路径不存在」：
    构造期写出的文件名是随机生成的，测试无从预先知道该断言哪个路径；只有盯住
    写入这个动作本身，才能可靠地证明「构造时没有产生文件」。

    注意 ``_write_netscape_cookie_file`` 也走 ``NamedTemporaryFile``，所以这里
    断言的是「构造期间调用次数为 0」；构造完成后再手动调一次作为对照，证明
    这个探针确实能捕捉到写入动作（否则一个坏掉的 mock 会让测试假绿）。
    """
    downloader = BilibiliDownloader()
    monkeypatch.setattr(downloader, "_cookie", FAKE_COOKIE, raising=False)

    calls = []
    real_named_tmp = dl_module.tempfile.NamedTemporaryFile

    def spy(*args, **kwargs):
        calls.append(args)
        return real_named_tmp(*args, **kwargs)

    # 先构造实例、再装探针，探针捕捉的是「构造之后」的动作；
    # 构造期是否写过盘由下面第二次构造来验证。
    monkeypatch.setattr(dl_module.tempfile, "NamedTemporaryFile", spy)
    fresh = BilibiliDownloader()
    monkeypatch.setattr(fresh, "_cookie", FAKE_COOKIE, raising=False)
    assert calls == [], f"构造期不应写 Cookie 文件，却调用了 {len(calls)} 次"

    # 对照：显式生成时探针必须能记录到，否则上面的断言毫无意义。
    path = fresh._write_netscape_cookie_file()
    assert isinstance(path, str)
    try:
        assert len(calls) == 1
    finally:
        BilibiliDownloader._remove_cookie_file(path)
    assert not os.path.exists(path)
