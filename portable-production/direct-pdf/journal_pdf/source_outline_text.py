from __future__ import annotations
from pathlib import Path
from .common import FigureError


def remove_outline_text(source:Path,page_no:int,rows:list[dict]) -> tuple[bytes,list[dict],set[int]]:
    from .source_registered_paints import remove_registered_paints
    if not isinstance(rows,list) or not rows:raise FigureError('source_outline_registration','须显式登记完整转曲字paint')
    data,bound,_,removed=remove_registered_paints(source,page_no,outline_rows=rows)
    return data,bound,removed
