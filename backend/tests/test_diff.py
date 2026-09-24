from app.models import SyncAction, Track
from app.services.sync_plan import plan_sync


def _t(name: str, sha: str) -> Track:
    return Track(path=f"/music/{name}", filename=name, title=name,
                 size=10, sha256=sha)


def test_push_new_and_skip_identical():
    local = [_t("a.mp3", "AAA"), _t("b.mp3", "BBB")]
    remote = {"a.mp3": "AAA"}
    prev = plan_sync(local, remote, "org.videolan.vlc-ios")
    assert [i.filename for i in prev.to_push] == ["b.mp3"]
    assert [i.filename for i in prev.to_skip] == ["a.mp3"]
    assert prev.to_delete == []


def test_changed_and_mirror_delete():
    local = [_t("a.mp3", "NEW")]
    remote = {"a.mp3": "OLD", "gone.mp3": "ZZZ"}
    prev = plan_sync(local, remote, "org.videolan.vlc-ios", mirror_delete=True)
    assert prev.to_push[0].reason == "changed"
    assert [i.filename for i in prev.to_delete] == ["gone.mp3"]
    prev2 = plan_sync(local, remote, "org.videolan.vlc-ios", mirror_delete=False)
    assert prev2.to_delete == []
