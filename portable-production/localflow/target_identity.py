from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import TypedDict

from .core import FlowError, figure_name, safe_child


class TargetFields(TypedDict, total=False):
    author: str
    target_basename: str


@dataclass(frozen=True, slots=True)
class TargetIdentity:
    author: str | None = None
    target_basename: str | None = None

    def fields(self) -> TargetFields:
        result: TargetFields = {}
        if self.author is not None:
            result['author'] = self.author
        if self.target_basename is not None:
            result['target_basename'] = self.target_basename
        return result

    def basename(self, folder_name: str, figure_number: str) -> str:
        if self.author is not None and not isinstance(self.author, str):
            raise FlowError('target_identity', '显式目标作者必须是字符串')
        if self.author is not None and any(ord(char) < 32 for char in self.author):
            raise FlowError('target_identity', '显式目标作者不能含控制字符')
        if self.target_basename is None:
            return figure_name(self.author if self.author is not None else folder_name, figure_number)
        value = self.target_basename
        if not isinstance(value, str):
            raise FlowError('target_identity', '显式目标文件名必须是字符串')
        if any(ord(char) < 32 for char in value):
            raise FlowError('target_identity', '显式目标文件名不能含控制字符')
        path = Path(value)
        windows_path = PureWindowsPath(value)
        if path.is_absolute() or windows_path.is_absolute() or path.name != value or windows_path.name != value:
            raise FlowError('unsafe_path', '显式目标文件名不得包含目录或绝对路径')
        suffix = f'-图{figure_number}.pdf'
        if not value.endswith(suffix):
            raise FlowError('target_identity', '显式目标文件名必须匹配图号并以.pdf结尾')
        target_author = value[:-len(suffix)]
        if figure_name(target_author, figure_number) != value:
            raise FlowError('target_identity', '显式目标文件名必须为安全作者-图号PDF')
        if self.author is not None and figure_name(self.author, figure_number) != value:
            raise FlowError('target_identity', '显式目标作者与文件名不匹配')
        return value

    def target(self, folder: Path, figure_number: str) -> Path:
        return safe_child(folder, self.basename(folder.name, figure_number), existing=False)
