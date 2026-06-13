"""파서 회귀 테스트 — 저장된 HTML 픽스처로 사이트 레이아웃 드리프트를 잡는다.

네트워크를 타지 않고 requests.get 을 픽스처로 몽키패치해 fetch() 전체 경로를 검증한다.
사이트 구조가 바뀌어 파서가 깨지면 이 테스트가 '조용한 폴백 전락' 대신 '큰 소리로 실패'한다.
"""

from pathlib import Path

from sources import allmetal, directscrap, nonferrous

FIX = Path(__file__).resolve().parent / "fixtures"


def load(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


class FakeResp:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status
        self.encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ---------------- 올메탈 ----------------
def test_allmetal_parses_cell_format(monkeypatch):
    list_html = load("allmetal_list.html")
    post_html = load("allmetal_post.html")
    monkeypatch.setattr(
        allmetal.requests, "get",
        lambda url, **kw: FakeResp(post_html if "wr_id=" in url else list_html),
    )
    res = allmetal.fetch()
    assert res["ok"] is True
    assert res["wr_id"] == 123  # 목록에서 가장 큰 wr_id
    assert res["post_date"] == "2026-06-11"
    p = res["prices"]
    assert p["copper-a"]["price"] == 17700
    assert p["copper-b"]["price"] == 16800
    assert p["stainless"]["price"] == 1600
    assert p["car-battery"]["price"] == 650
    assert len(p) >= 12  # 레이아웃 드리프트 가드 (예상 12+종)


def test_allmetal_tolerates_dash_and_colon(monkeypatch):
    list_html = load("allmetal_list.html")
    post_html = load("allmetal_post_dash.html")
    monkeypatch.setattr(
        allmetal.requests, "get",
        lambda url, **kw: FakeResp(post_html if "wr_id=" in url else list_html),
    )
    res = allmetal.fetch()
    assert res["ok"] is True
    assert res["prices"]["copper-a"]["price"] == 17700  # 'A동 - 17,700'
    assert res["prices"]["copper-b"]["price"] == 16800  # '상동 : 16,800'


def test_allmetal_fetch_failure_sets_error(monkeypatch):
    def boom(url, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(allmetal.requests, "get", boom)
    res = allmetal.fetch()
    assert res["ok"] is False
    assert res["error"]


# ---------------- 다이렉트스크랩 ----------------
def test_directscrap_parses(monkeypatch):
    nf = load("directscrap_nonferrous.html")
    ir = load("directscrap_iron.html")
    monkeypatch.setattr(
        directscrap.requests, "get",
        lambda url, **kw: FakeResp(ir if "scrapiron" in url else nf),
    )
    res = directscrap.fetch()
    assert res["ok"] is True
    p = res["prices"]
    assert p["copper-a"]["price"] == 17900
    assert p["copper-b"]["price"] == 17100
    assert p["brass"]["price"] == 10700
    assert p["stainless"]["price"] == 1600
    assert p["al-frame"]["price"] == 3500
    assert p["zinc"]["price"] == 2800
    assert p["iron-misc"]["price"] == 420
    assert p["iron-heavy"]["price"] == 340
    assert p["iron-light"]["price"] == 330
    assert res["data_date"] == "2026-06-13"


# ---------------- 한국비철금속협회 ----------------
def test_nonferrous_parses(monkeypatch):
    html = load("nonferrous.html")
    monkeypatch.setattr(nonferrous.requests, "get", lambda url, **kw: FakeResp(html))
    res = nonferrous.fetch()
    assert res["ok"] is True
    assert res["data_date"] == "2026-06-11"
    assert res["prices"]["copper"] == 13190.0
    assert set(res["prices"]) >= {"copper", "aluminum", "zinc", "lead", "nickel", "tin"}


def test_nonferrous_no_table_fails_cleanly(monkeypatch):
    monkeypatch.setattr(
        nonferrous.requests, "get",
        lambda url, **kw: FakeResp("<html><body>점검중</body></html>"),
    )
    res = nonferrous.fetch()
    assert res["ok"] is False
    assert res["error"]
