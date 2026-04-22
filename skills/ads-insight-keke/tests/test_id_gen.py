from ads_insight_keke.id_gen import normalize_url, gen_id


def test_normalize_strips_utm_and_fragment() -> None:
    a = "https://Example.com/Path/?utm_source=x&id=1#frag"
    b = "https://example.com/Path?id=1"
    assert normalize_url(a) == normalize_url(b)


def test_normalize_lowercases_host_only() -> None:
    assert normalize_url("https://EXAMPLE.com/Path") == "https://example.com/Path"


def test_normalize_strips_trailing_slash() -> None:
    assert normalize_url("https://x.com/a/") == normalize_url("https://x.com/a")


def test_id_is_16_hex() -> None:
    i = gen_id("https://x.com/a")
    assert len(i) == 16
    assert all(c in "0123456789abcdef" for c in i)


def test_id_is_idempotent() -> None:
    assert gen_id("https://X.com/a/?utm_x=1") == gen_id("https://x.com/a")
