from PIL import Image, ImageDraw, ImageFont
from pathlib import Path


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _wrap_text_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    
    if draw.textbbox((0, 0), text, font=font)[2] <= max_w:
        return [text]

    seps = ["_", "-", " "]
    tokens = [text]
    for sep in seps:
        if sep in text:
            parts = text.split(sep)
            rebuilt = []
            for i, t in enumerate(parts):
                rebuilt.append(t + (sep if i < len(parts) - 1 else ""))
            tokens = rebuilt
            break

    def fits(s: str) -> bool:
        return draw.textbbox((0, 0), s, font=font)[2] <= max_w

    lines: list[str] = []
    cur = ""

    for tok in tokens:
        if cur == "":
            cur = tok
            continue
        cand = cur + tok
        if fits(cand):
            cur = cand
        else:
            lines.append(cur.rstrip())
            cur = tok

    if cur:
        lines.append(cur.rstrip())

    # Hard split any line still too wide
    final_lines: list[str] = []
    for line in lines:
        if fits(line):
            final_lines.append(line)
            continue

        chunk = ""
        for ch in line:
            if chunk == "":
                chunk = ch
                continue
            cand = chunk + ch
            if fits(cand):
                chunk = cand
            else:
                final_lines.append(chunk)
                chunk = ch
        if chunk:
            final_lines.append(chunk)

    return final_lines


def burn_watermark(image_path: str, *, uut_serial: str, dt_text: str, logo_path: str | None = None) -> None:
    path = Path(image_path)
    img = Image.open(path)

    has_alpha = (img.mode in ("RGBA", "LA")) or ("transparency" in getattr(img, "info", {}))
    base = img.convert("RGBA" if has_alpha else "RGB")
    w, h = base.size

    font_size = _clamp(int(w * 0.026), 28, 56)
    pad = _clamp(int(w * 0.010), 10, 20)
    border_w = _clamp(int(w * 0.0025), 2, 5)
    line_gap = _clamp(int(pad * 0.45), 4, 12)

    font_path = Path(__file__).parent.parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
    font = ImageFont.truetype(str(font_path), font_size)

    line_sn = f"Serial Number : {uut_serial}"
    line_dt = f"Date : {dt_text}"

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Cap banner width so it doesn't cover the whole image
    max_banner_w = int(w * 0.72)

    # Decide logo block width (square), based on font height
    # Make it stable even when text wraps.
    sample_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    logo_w = logo_h = 0
    logo_img = None
    logo_gap = 4

    if logo_path:
        logo_img = Image.open(logo_path).convert("RGBA")

        # Size by height, BUT cap width hard
        target_h = _clamp(int(sample_h * 1.8), 48, 90)
        aspect = logo_img.width / logo_img.height
        target_w = int(target_h * aspect)

        max_logo_w = int(w * 0.16)   # hard cap: logo cannot eat too much width
        if target_w > max_logo_w:
            target_w = max_logo_w
            target_h = int(target_w / aspect)

        logo_img = logo_img.resize((target_w, target_h), Image.LANCZOS)
        logo_w, logo_h = logo_img.size
    else:
        logo_gap = 0

    # Available text width after logo block and padding
    text_max_w = max_banner_w - (pad * 2) - logo_w - logo_gap
    if text_max_w < 80:  # safety floor
        text_max_w = 80

    sn_lines = _wrap_text_to_width(draw, line_sn, font, text_max_w)
    dt_lines = _wrap_text_to_width(draw, line_dt, font, text_max_w)
    all_lines = sn_lines + dt_lines

    # Measure wrapped text block
    text_w = 0
    text_h = 0
    line_heights: list[int] = []
    for ln in all_lines:
        b = draw.textbbox((0, 0), ln, font=font)
        lw = b[2] - b[0]
        lh = b[3] - b[1]
        text_w = max(text_w, lw)
        text_h += lh
        line_heights.append(lh)
    if len(all_lines) > 1:
        text_h += line_gap * (len(all_lines) - 1)

    # Banner dimensions
    content_h = max(text_h, logo_h if logo_path else 0)
    banner_w = min(max_banner_w, (pad * 2) + logo_w + logo_gap + text_w)
    banner_h = (pad * 2) + content_h

    # Draw banner
    lime = (180, 255, 0, 255)
    draw.rectangle([0, 0, banner_w, banner_h], fill=lime)
    draw.rectangle([0, 0, banner_w, banner_h], outline=(0, 0, 0, 255), width=border_w)

    # Paste logo (centered vertically in banner)
    if logo_path:
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((logo_w, logo_h), Image.Resampling.LANCZOS)
            lx = pad
            ly = pad + (content_h - logo.size[1]) // 2
            overlay.paste(logo, (lx, ly), logo)
        except Exception:
            # If logo fails, keep watermark text anyway (don't break export)
            pass

    # Draw wrapped text (aligned to top, with padding)
    tx = pad + logo_w + logo_gap
    ty = pad
    for i, ln in enumerate(all_lines):
        draw.text((tx, ty), ln, fill=(0, 0, 0, 255), font=font)
        ty += line_heights[i]
        if i < len(all_lines) - 1:
            ty += line_gap

    # Composite and save
    if base.mode != "RGBA":
        base = base.convert("RGBA")
    combined = Image.alpha_composite(base, overlay)

    fmt = img.format
    save_kwargs = {}
    if fmt == "JPEG":
        combined = combined.convert("RGB")
        save_kwargs["quality"] = 95

    combined.save(path, format=fmt, **save_kwargs)