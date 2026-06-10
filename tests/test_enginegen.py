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
