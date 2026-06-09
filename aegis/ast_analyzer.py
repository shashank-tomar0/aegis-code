import ast

class ASTSerializer(ast.NodeVisitor):
    """Depth-First Search (DFS) visitor to serialize AST structure into ordered type-tokens."""
    def __init__(self):
        self.tokens = []
        # Filter out noisy nodes that don't represent structural logic flow
        self.ignored_nodes = {
            'Load', 'Store', 'Param', 'Del', 'Module', 
            'Expr', 'Pass', 'Name', 'Constant'
        }

    def generic_visit(self, node):
        node_type = type(node).__name__
        if node_type not in self.ignored_nodes:
            self.tokens.append(node_type)
        super().generic_visit(node)

class ComplexityVisitor(ast.NodeVisitor):
    """Calculates McCabe Cyclomatic Complexity of functions in an AST."""
    def __init__(self):
        self.functions = []

    def visit_FunctionDef(self, node):
        self._calculate_complexity(node)

    def visit_AsyncFunctionDef(self, node):
        self._calculate_complexity(node)

    def _calculate_complexity(self, node):
        # Base complexity is 1
        complexity = 1
        
        # Traverse subtree of the function to count decision points
        for child in ast.walk(node):
            child_type = type(child).__name__
            
            # Decision nodes
            if child_type in ('If', 'While', 'For', 'AsyncFor', 'IfExp'):
                complexity += 1
            elif child_type == 'ExceptHandler':
                complexity += 1
            elif child_type == 'BoolOp':
                # Short-circuiting operators add complexity per operand beyond the first
                # e.g., 'a and b and c' has 2 decision points
                complexity += len(child.values) - 1
                
        # Get raw source lines if possible (fallback if lines are unknown)
        start_line = getattr(node, 'lineno', 1)
        end_line = getattr(node, 'end_lineno', start_line + 10)
        
        self.functions.append({
            "name": node.name,
            "complexity": complexity,
            "start_line": start_line,
            "end_line": end_line,
            "node": node
        })

def analyze_file(filepath):
    """
    Parses a python file and returns its:
    1. Normalized AST token list
    2. List of functions with their cyclomatic complexities
    3. Total lines of code
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        raise IOError(f"Could not read file {filepath}: {e}")

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in {filepath}: {e}")

    # 1. Structural Tokenization
    serializer = ASTSerializer()
    serializer.visit(tree)
    tokens = serializer.tokens

    # 2. Complexity Calculation
    complexity_visitor = ComplexityVisitor()
    complexity_visitor.visit(tree)
    functions = sorted(complexity_visitor.functions, key=lambda x: x["complexity"], reverse=True)

    # 3. Read raw source code lines for extraction later
    source_lines = source.splitlines()

    # Enrich function dictionaries with their actual source code snippets
    for fn in functions:
        start = max(0, fn["start_line"] - 1)
        end = min(len(source_lines), fn["end_line"])
        fn["source_code"] = "\n".join(source_lines[start:end])

    return {
        "tokens": tokens,
        "functions": functions,
        "lines_count": len(source_lines)
    }

def analyze_file_from_source(source: str) -> tuple[list, list]:
    """
    Parses a raw Python source string (not a file) and returns:
    - tokens: normalized AST token list
    - functions: list of function complexity dicts
    Used by the baseline bank to fingerprint Gemini-generated solutions.
    """
    try:
        tree = ast.parse(source, filename="<generated>")
    except SyntaxError:
        return [], []

    serializer = ASTSerializer()
    serializer.visit(tree)

    complexity_visitor = ComplexityVisitor()
    complexity_visitor.visit(tree)

    source_lines = source.splitlines()
    for fn in complexity_visitor.functions:
        start = max(0, fn["start_line"] - 1)
        end = min(len(source_lines), fn["end_line"])
        fn["source_code"] = "\n".join(source_lines[start:end])

    return serializer.tokens, complexity_visitor.functions
