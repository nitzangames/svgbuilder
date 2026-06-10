import pytest
from svgbuilder.enginegen.util import b64, media_type_for


def test_b64_roundtrips_ascii():
    assert b64(b"PNG") == "UE5H"


def test_media_type_for_known_extensions():
    assert media_type_for("/a/x.jpg") == "image/jpeg"
    assert media_type_for("/a/x.jpeg") == "image/jpeg"
    assert media_type_for("/a/x.PNG") == "image/png"
    assert media_type_for("/a/x.webp") == "image/webp"


def test_media_type_for_unsupported_raises():
    with pytest.raises(ValueError):
        media_type_for("/a/x.gif")


from svgbuilder.enginegen.extract_svg import extract_svg


def test_extract_svg_from_code_fence():
    reply = "Here you go:\n```svg\n<svg viewBox=\"0 0 1 1\"><rect/></svg>\n```\nDone."
    assert extract_svg(reply) == '<svg viewBox="0 0 1 1"><rect/></svg>'


def test_extract_svg_from_raw_text():
    reply = '<svg viewBox="0 0 2 2"><circle/></svg>'
    assert extract_svg(reply) == reply


def test_extract_svg_is_case_insensitive_and_multiline():
    reply = "junk\n<SVG\n viewBox=\"0 0 3 3\">\n<g></g>\n</SVG> trailing"
    out = extract_svg(reply)
    assert out.startswith("<SVG") and out.endswith("</SVG>")


def test_extract_svg_missing_raises():
    with pytest.raises(ValueError):
        extract_svg("no svg here")


from svgbuilder.enginegen.validate import validate

_GOOD = (
    '<svg viewBox="0 0 200 100">'
    '<circle cx="60" cy="88" r="15" fill="#2c2c2a"/>'
    '<circle cx="120" cy="88" r="15" fill="#2c2c2a"/>'
    '<rect x="0" y="40" width="200" height="40" fill="#1f6b54"/>'
    '</svg>'
)


def test_validate_good_sprite():
    r = validate(_GOOD)
    assert r["has_viewbox"] is True
    assert r["wheel_count"] == 2
    assert r["ok"] is True


def test_validate_flags_missing_wheels():
    svg = '<svg viewBox="0 0 10 10"><rect width="10" height="10" fill="#1f6b54"/></svg>'
    r = validate(svg)
    assert r["wheel_count"] == 0
    assert r["ok"] is False


def test_validate_flags_missing_viewbox():
    svg = _GOOD.replace('viewBox="0 0 200 100"', "")
    r = validate(svg)
    assert r["has_viewbox"] is False
    assert r["ok"] is False


def test_validate_ignores_small_or_wrongcolor_circles():
    svg = (
        '<svg viewBox="0 0 200 100">'
        '<circle cx="60" cy="88" r="2" fill="#2c2c2a"/>'      # too small (hub)
        '<circle cx="120" cy="88" r="15" fill="#d9a834"/>'    # wrong colour
        '</svg>'
    )
    assert validate(svg)["wheel_count"] == 0


from svgbuilder.enginegen.render import render_png_bytes


def test_render_png_bytes_returns_png():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><rect width="20" height="10" fill="red"/></svg>'
    data = render_png_bytes(svg)
    assert isinstance(data, (bytes, bytearray))
    assert bytes(data[:4]) == b"\x89PNG"


from svgbuilder.enginegen.exemplars import load_exemplars, load_conventions


def test_load_exemplars_returns_named_svgs():
    ex = load_exemplars()
    assert len(ex) == 3
    names = [n for n, _ in ex]
    assert "classic-american-4-4-0.svg" in names
    for _name, svg in ex:
        assert "<svg" in svg


def test_load_exemplars_includes_extra_refs(tmp_path):
    ref = tmp_path / "mine.svg"
    ref.write_text('<svg viewBox="0 0 1 1"></svg>')
    ex = load_exemplars(extra_paths=[str(ref)])
    assert ("mine.svg", '<svg viewBox="0 0 1 1"></svg>') in ex
    assert len(ex) == 4


def test_load_conventions_nonempty():
    assert "WHEELS" in load_conventions()


from svgbuilder.enginegen.generate import make_generator


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, text, capture):
        self._text, self._capture = text, capture

    def create(self, **kwargs):
        self._capture.append(kwargs)
        return _Resp(self._text)


class _FakeClient:
    def __init__(self, text, capture):
        self.messages = _FakeMessages(text, capture)


def test_generate_sends_photo_and_returns_text():
    cap = []
    fake = _FakeClient("<svg/>", cap)
    generate, _revise = make_generator(model="claude-opus-4-8", client=fake)
    out = generate("BASE64PHOTO", "image/jpeg",
                   [("ex.svg", "<svg/>")], "CONVENTIONS")
    assert out == "<svg/>"
    content = cap[0]["messages"][0]["content"]
    images = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
    assert len(images) == 1
    assert images[0]["source"]["media_type"] == "image/jpeg"
    assert cap[0]["model"] == "claude-opus-4-8"
    assert cap[0]["system"] == "CONVENTIONS"


def test_revise_sends_photo_and_render():
    cap = []
    fake = _FakeClient("<svg2/>", cap)
    _generate, revise = make_generator(model="claude-opus-4-8", client=fake)
    out = revise("PHOTO64", "image/png", "RENDER64", "<svg/>", "CONVENTIONS")
    assert out == "<svg2/>"
    content = cap[0]["messages"][0]["content"]
    images = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
    assert len(images) == 2  # source photo + current render


from svgbuilder.enginegen.loop import generate_engine

_SPRITE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
    '<circle cx="60" cy="88" r="15" fill="#2c2c2a"/>'
    '<circle cx="120" cy="88" r="15" fill="#2c2c2a"/>'
    '</svg>'
)


def _photo(tmp_path):
    p = tmp_path / "loco.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)  # bytes are never decoded (fakes)
    return str(p)


def test_generate_engine_runs_and_validates(tmp_path):
    calls = {"gen": 0, "rev": 0}

    def generate(photo_b64, media, exemplars, conventions):
        calls["gen"] += 1
        return f"```svg\n{_SPRITE}\n```"

    def revise(photo_b64, media, render_b64, current_svg, conventions):
        calls["rev"] += 1
        return _SPRITE  # unchanged -> loop stops

    svg, report = generate_engine(
        _photo(tmp_path), generate=generate, revise=revise,
        render=lambda s: b"\x89PNG", exemplars=[], conventions="C", rounds=3,
    )
    assert "<circle" in svg
    assert report["wheel_count"] == 2 and report["ok"] is True
    assert calls["gen"] == 1
    assert calls["rev"] == 1  # stopped after the first revise returned unchanged


def test_generate_engine_respects_rounds(tmp_path):
    # revise always returns a *different* svg, so it should run rounds-1 times.
    variants = [_SPRITE.replace("200", "201"), _SPRITE.replace("200", "202"),
                _SPRITE.replace("200", "203")]

    def revise(photo_b64, media, render_b64, current_svg, conventions):
        return variants.pop(0)

    svg, report = generate_engine(
        _photo(tmp_path), generate=lambda *a: _SPRITE, revise=revise,
        render=lambda s: b"\x89PNG", exemplars=[], conventions="C", rounds=3,
    )
    # 1 generate + (rounds-1)=2 revises consumed two variants
    assert svg == _SPRITE.replace("200", "202")


def test_validate_handles_single_quoted_attributes():
    svg = (
        "<svg viewBox='0 0 200 100'>"
        "<circle cx='60' cy='88' r='15' fill='#2c2c2a'/>"
        "<circle cx='120' cy='88' r='15' fill='#2c2c2a'/>"
        "</svg>"
    )
    r = validate(svg)
    assert r["has_viewbox"] is True
    assert r["wheel_count"] == 2 and r["ok"] is True


def test_generate_raises_when_no_text_block():
    class _ThinkingOnly:
        content = [type("B", (), {"type": "thinking", "thinking": "..."})()]

    class _Msgs:
        def create(self, **kwargs):
            return _ThinkingOnly()

    class _Client:
        messages = _Msgs()

    generate, _revise = make_generator(client=_Client())
    with pytest.raises(ValueError):
        generate("P", "image/png", [], "C")


def test_generate_engine_stops_when_render_fails(tmp_path):
    def boom_render(svg):
        raise RuntimeError("render boom")

    calls = {"rev": 0}

    def revise(*a):
        calls["rev"] += 1
        return _SPRITE.replace("200", "201")

    svg, report = generate_engine(
        _photo(tmp_path), generate=lambda *a: _SPRITE, revise=revise,
        render=boom_render, exemplars=[], conventions="C", rounds=3,
    )
    assert svg == _SPRITE  # render failed on round 1 -> loop broke, baseline kept
    assert calls["rev"] == 0


from svgbuilder.enginegen import cli as engine_cli


def test_cli_missing_input_returns_2(tmp_path):
    assert engine_cli.main([str(tmp_path / "nope.png")]) == 2


def test_cli_end_to_end_with_fake_generator(tmp_path, monkeypatch):
    # Replace the real Anthropic-backed generator with fakes (no network).
    def fake_make_generator(model=None, client=None):
        def generate(photo_b64, media, exemplars, conventions):
            return _SPRITE
        def revise(photo_b64, media, render_b64, current_svg, conventions):
            return _SPRITE
        return generate, revise

    monkeypatch.setattr(engine_cli, "make_generator", fake_make_generator)

    src = tmp_path / "loco.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    out = tmp_path / "engine.svg"
    code = engine_cli.main([str(src), "-o", str(out), "--rounds", "2", "--quiet"])
    assert code == 0
    assert out.exists() and "<circle" in out.read_text()
    assert (tmp_path / "engine.preview.png").exists()


def test_cli_reports_setup_error_when_generator_unavailable(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("no api key")
    monkeypatch.setattr(engine_cli, "make_generator", boom)
    src = tmp_path / "loco.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    code = engine_cli.main([str(src), "--quiet"])
    assert code == 1
    assert "no api key" in capsys.readouterr().err
