"""Grayscale gate shared by PDF audit and raster delivery.

The existing editorial profile allows a channel delta of 2 at 300 dpi
(pixels stricter than that must be zero). That threshold stays; it is an
open question whether the owner wants it tightened to zero.
"""
from .load import load_rules


def channel_delta_image(image):
    from PIL import ImageChops
    rgb = image.convert('RGB')
    red, green, blue = rgb.split()
    return ImageChops.lighter(
        ImageChops.difference(red, green),
        ImageChops.lighter(ImageChops.difference(red, blue), ImageChops.difference(green, blue)),
    )


def excess_color_pixels(image, max_delta=None) -> int:
    if max_delta is None:
        max_delta = int(load_rules()['normative']['grayscale_channel_delta_max'])
    if image.mode == 'L':
        return 0
    histogram = channel_delta_image(image).histogram()
    return sum(histogram[int(max_delta) + 1:])


def assert_grayscale_image(image, max_delta=None):
    count = excess_color_pixels(image, max_delta)
    if count:
        raise ValueError(f'color_output:{count}')
    return count
