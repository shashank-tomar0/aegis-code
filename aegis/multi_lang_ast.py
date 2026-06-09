"""
aegis/multi_lang_ast.py — Multi-Language Support via Tree-sitter

Extends AST parsing to JavaScript, Java, and C++ to support a wider
range of CS courses. Falls back to Python `ast` module if language
is Python and tree-sitter is unavailable.
"""

import os

try:
    import tree_sitter
    import tree_sitter_python
    import tree_sitter_javascript
    import tree_sitter_java
    import tree_sitter_cpp
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

LANG_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "cpp",
    ".h": "cpp",
    ".hpp": "cpp"
}

def get_language(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return LANG_MAP.get(ext, "unknown")

def get_parser(lang: str):
    if not TREE_SITTER_AVAILABLE:
        return None
        
    try:
        # Support for tree-sitter >= 0.22.0 API
        if lang == "python":
            lang_obj = tree_sitter.Language(tree_sitter_python.language())
        elif lang == "javascript":
            lang_obj = tree_sitter.Language(tree_sitter_javascript.language())
        elif lang == "java":
            lang_obj = tree_sitter.Language(tree_sitter_java.language())
        elif lang == "cpp":
            lang_obj = tree_sitter.Language(tree_sitter_cpp.language())
        else:
            return None
            
        parser = tree_sitter.Parser(lang_obj)
        return parser
    except Exception as e:
        print(f"Tree-sitter parser error: {e}")
        return None

def analyze_file_multilang(file_path: str) -> dict:
    """
    Parses a file using tree-sitter if supported, returning AST tokens
    and basic function metrics. Fallback to aegis.ast_analyzer for Python.
    """
    lang = get_language(file_path)
    
    if lang == "python" or not TREE_SITTER_AVAILABLE:
        from aegis.ast_analyzer import analyze_file
        return analyze_file(file_path)
        
    parser = get_parser(lang)
    if not parser:
        return {"tokens": [], "functions": [], "lines_count": 0}
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        raise IOError(f"Could not read file {file_path}: {e}")
        
    tree = parser.parse(bytes(source, "utf8"))
    
    tokens = []
    functions = []
    
    def traverse(node):
        node_type = node.type
        # Filter out noisy leaf nodes
        if node_type not in ["string", "comment", "integer", "{", "}", "(", ")", ";", ",", "=", ".", "identifier"]:
            tokens.append(node_type)
            
        if "function" in node_type or "method" in node_type:
            complexity = 1
            # A shallow complexity approximation
            for child in node.children:
                if child.type in ["if_statement", "for_statement", "while_statement", "catch_clause"]:
                    complexity += 1
            
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            functions.append({
                "name": f"{lang}_func",
                "complexity": complexity,
                "start_line": start_line,
                "end_line": end_line,
                "source_code": "\n".join(source.splitlines()[start_line-1:end_line])
            })
            
        for child in node.children:
            traverse(child)

    traverse(tree.root_node)
    source_lines = source.splitlines()
    
    return {
        "tokens": tokens,
        "functions": functions,
        "lines_count": len(source_lines)
    }
