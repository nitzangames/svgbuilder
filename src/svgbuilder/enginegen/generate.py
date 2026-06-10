"""Claude vision calls that author and refine an engine sprite SVG."""

DEFAULT_MODEL = "claude-opus-4-8"


def _image_block(b64_data, media_type):
    return {"type": "image", "source": {
        "type": "base64", "media_type": media_type, "data": b64_data}}


def _exemplar_text(exemplars):
    return "\n\n".join(f"<!-- EXAMPLE: {name} -->\n{svg}" for name, svg in exemplars)


def make_generator(model=DEFAULT_MODEL, client=None):
    """Return (generate, revise) callables backed by the Anthropic vision API.

    generate(photo_b64, photo_media, exemplars, conventions) -> reply text
    revise(photo_b64, photo_media, render_b64, current_svg, conventions) -> reply text
    Both return the model's raw text reply (run extract_svg on it). A default
    Anthropic client is created lazily if none is supplied.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    def _ask(content, conventions):
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=conventions,
            messages=[{"role": "user", "content": content}],
        )
        return next(b.text for b in response.content if b.type == "text")

    def generate(photo_b64, photo_media, exemplars, conventions):
        return _ask([
            {"type": "text", "text": "House-style example sprites to match:"},
            {"type": "text", "text": _exemplar_text(exemplars)},
            {"type": "text", "text":
                "Draw THIS locomotive in the same house style, resembling it "
                "(livery colors, wheel arrangement, standout features). "
                "Output only the SVG."},
            _image_block(photo_b64, photo_media),
        ], conventions)

    def revise(photo_b64, photo_media, render_b64, current_svg, conventions):
        return _ask([
            {"type": "text", "text": "SOURCE photo of the locomotive:"},
            _image_block(photo_b64, photo_media),
            {"type": "text", "text": "CURRENT rendered sprite from your SVG:"},
            _image_block(render_b64, "image/png"),
            {"type": "text", "text": "Current SVG:\n" + current_svg},
            {"type": "text", "text":
                "Improve the SVG so it better resembles the source and follows all "
                "conventions (facing right; #2c2c2a wheel circles of radius >= 6 "
                "along the lower frame; correct wheel count; house palette). If it "
                "is already good, return it unchanged. Output only the SVG."},
        ], conventions)

    return generate, revise
