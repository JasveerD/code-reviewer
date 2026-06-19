"""Build CodeContext from a ReviewTarget using tree-sitter."""
import tree_sitter
import tree_sitter_python
from .ingestion.types import ReviewTarget, ReviewFile
from .context import CodeContext, FileMap, FunctionInfo, ClassInfo


# Languages we know how to parse. Other files get a minimal FileMap.
_PY_LANGUAGE = tree_sitter.Language(tree_sitter_python.language())
_PARSERS: dict[str, tree_sitter.Parser] = {
    "python": tree_sitter.Parser(_PY_LANGUAGE),
}

def build_context(target: ReviewTarget) -> CodeContext:
    maps: dict[str, FileMap] = {}
    for file in target.files:
        maps[file.path] = _build_file_map(file)
    return CodeContext(target=target, file_maps=maps)


def _build_file_map(file: ReviewFile) -> FileMap:
    fm = FileMap(
        path=file.path,
        language=file.language,
        total_lines=file.content.count("\n") + 1,
    )
    parser = _PARSERS.get(file.language)
    if parser is None:
        return fm   # unknown language → empty map, agents handle gracefully

    tree = parser.parse(bytes(file.content, "utf-8"))
    source_bytes = bytes(file.content, "utf-8")
    _walk(tree.root_node, source_bytes, fm)
    return fm

def _walk(node, source: bytes, fm: FileMap) -> None:
    """Recursively find function and class definitions."""
    if node.type in ("function_definition", "async_function_definition"):
        fm.functions.append(_function_info(node, source))
    elif node.type == "class_definition":
        fm.classes.append(_class_info(node, source))
    elif node.type in ("import_statement", "import_from_statement"):
        fm.imports.append(_text(node, source))

    for child in node.children:
        _walk(child, source, fm)

def _function_info(node, source: bytes) -> FunctionInfo:
    name_node = node.child_by_field_name("name")
    name = _text(name_node, source) if name_node else "<anonymous>"
    # signature = everything from "def" up to (but not including) the body's colon line
    body = node.child_by_field_name("body")
    sig_end_byte = body.start_byte if body else node.end_byte
    signature = source[node.start_byte:sig_end_byte].decode("utf-8").strip().rstrip(":").strip()
    return FunctionInfo(
        name=name,
        line_start=node.start_point[0] + 1,   # tree-sitter is 0-indexed
        line_end=node.end_point[0] + 1,
        signature=signature,
        is_async=node.type == "async_function_definition",
    )

def _class_info(node, source: bytes) -> ClassInfo:
    name_node = node.child_by_field_name("name")
    name = _text(name_node, source) if name_node else "<anonymous>"
    methods = []
    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type in ("function_definition", "async_function_definition"):
                mname = child.child_by_field_name("name")
                if mname:
                    methods.append(_text(mname, source))
    return ClassInfo(
        name=name,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        methods=methods,
    )


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")
