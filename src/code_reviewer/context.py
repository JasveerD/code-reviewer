"""Code map: strctured info about input files, built from tree sitter"""

from dataclasses import dataclass, field
from .ingestion.types import ReviewTarget

@dataclass
class FunctionInfo:
    name:str
    line_start:int # 1 indexed
    line_end:int   # 1 indexed, inclusive
    signature:str  # function siganture : def foo(...)
    is_async:bool = False

@dataclass
class ClassInfo:
    name:str
    line_start:int
    line_end:int
    methods:list[str] = field(default_factory=list)

@dataclass
class FileMap:
    path: str
    language: str
    total_lines: int
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

@dataclass 
class CodeContext:
    target:ReviewTarget
    file_maps:dict[str, FileMap] 

    def map_for(self, file_path:str) -> FileMap | None:
        return self.file_maps.get(file_path)
 

