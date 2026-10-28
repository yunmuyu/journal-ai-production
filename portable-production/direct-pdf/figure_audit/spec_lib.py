"""Public facade for PDF inspection geometry."""
from .spec_core import MM, PT, UP, DOWN, AXIS_MIN_PT, Span, Seg, Axes, spans, font_sizes, body_size, text_width, wrap_count, segments, filled_rects, ink_bbox, has_bitmap, is_3d_hint
from .spec_axes import detect_frames, detect_axes
from .spec_features import category_labels, value_labels, legend_items
