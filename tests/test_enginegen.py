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
