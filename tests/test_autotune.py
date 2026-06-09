from svgbuilder.autotune import render_svg

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
    '<rect width="20" height="10" fill="rgb(200,30,30)"/></svg>'
)


def test_render_svg_returns_rgb_image_of_requested_size():
    img = render_svg(_SVG, (20, 10))
    assert img.size == (20, 10)
    assert img.mode == "RGB"
    # the rect is solid red; center pixel should be reddish
    r, g, b = img.getpixel((10, 5))
    assert r > 150 and g < 100 and b < 100


def test_render_svg_resizes_to_requested_size():
    img = render_svg(_SVG, (40, 20))
    assert img.size == (40, 20)
