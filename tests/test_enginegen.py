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
