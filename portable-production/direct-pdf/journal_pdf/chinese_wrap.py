"""Use the operating system ICU word boundaries for CJK labels."""
from __future__ import annotations
import ctypes
import functools
import re
from collections.abc import Callable

from .common import FigureError


@functools.lru_cache(maxsize=1024)
def _words(text):
    try:
        lib=ctypes.CDLL('icu.dll')
        lib.ubrk_open.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.POINTER(ctypes.c_uint16),ctypes.c_int32,ctypes.POINTER(ctypes.c_int32)]
        lib.ubrk_open.restype=ctypes.c_void_p
        for name in ('ubrk_first','ubrk_next'):
            getattr(lib,name).argtypes=[ctypes.c_void_p];getattr(lib,name).restype=ctypes.c_int32
        lib.ubrk_close.argtypes=[ctypes.c_void_p]
        raw=text.encode('utf-16-le');chars=(ctypes.c_uint16*(len(raw)//2)).from_buffer_copy(raw);err=ctypes.c_int32(0)
        iterator=lib.ubrk_open(1,b'zh_CN',chars,len(chars),ctypes.byref(err))
        if not iterator or err.value>0:raise FigureError('chinese_segmentation_unavailable','系统中文分词不可用')
        try:
            start=lib.ubrk_first(iterator);parts=[]
            while (end:=lib.ubrk_next(iterator))!=-1:
                parts.append(raw[start*2:end*2].decode('utf-16-le'));start=end
        finally:lib.ubrk_close(iterator)
        if ''.join(parts)!=text:raise FigureError('chinese_segmentation_invalid','中文分词未保留原文')
        return tuple(parts)
    except OSError as error:
        raise FigureError('chinese_segmentation_unavailable','系统中文分词不可用，请提供明确换行') from error


def _pieces(text: str, max_chars: float) -> list[str]:
    pieces=[]
    for chunk in re.findall(r'[\u3400-\u9fff]+|[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*|[^\u3400-\u9fffA-Za-z0-9]',text):
        if re.fullmatch(r'[\u3400-\u9fff]+',chunk):
            suffix=next((v for v in ('电路','芯片','模块') if chunk.endswith(v) and len(chunk)>len(v)),None)
            words=list(_words(chunk[:-len(suffix)]))+[suffix] if suffix else list(_words(chunk))
        else:words=[chunk]
        for word in words:
            if word in {'电路','芯片','模块'} and pieces and len(pieces[-1]+word)<=max_chars:
                pieces[-1]+=word
            else:pieces.append(word)
    return pieces


def wrap_chinese(text, max_chars):
    """Break at word boundaries without changing source text."""
    pieces = _pieces(text, max_chars)
    lines=[];line=''
    for piece in pieces:
        if line and len(line)+len(piece)>max_chars:lines.append(line);line=''
        line+=piece
    if line:lines.append(line)
    return '\n'.join(lines)


def wrap_measured(text: str, width_pt: float, measure: Callable[[str], float]) -> str:
    """Use existing ICU word boundaries and actual ink widths; never split a token."""
    lines: list[str] = []
    for paragraph in text.split('\n'):
        line = ''
        for token in _pieces(paragraph, float('inf')):
            if token.isspace():
                line += token
                continue
            if measure(token) > width_pt + 1e-6:
                raise FigureError('label_word_too_wide', '完整词组超过限宽，请调整布局',
                                  token=token, width_pt=width_pt, token_width_pt=measure(token))
            if line and measure(line + token) > width_pt + 1e-6:
                lines.append(line)
                line = ''
            line += token
        lines.append(line)
    return '\n'.join(lines)
