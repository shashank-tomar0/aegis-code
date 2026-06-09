import ast
import random
import importlib.util
import os
import sys

class HardcodeInspector(ast.NodeVisitor):
    """AST visitor that checks if input parameters are directly checked against constant values (test-case gaming)."""
    def __init__(self):
        self.hardcode_count = 0
        self.constants_checked = []

    def visit_Compare(self, node):
        # Checks if variable is compared to list, dict, tuple or constant
        # e.g., 'if arr == [1, 3, 5]:' or 'if target == 5:'
        left_name = isinstance(node.left, ast.Name) and node.left.id != "__name__"
        right_const = any(isinstance(c, (ast.Constant, ast.List, ast.Tuple, ast.Dict)) for c in node.comparators)
        
        # Reverse check (e.g., 'if 5 == target:')
        left_const = isinstance(node.left, (ast.Constant, ast.List, ast.Tuple, ast.Dict))
        right_name = any(isinstance(c, ast.Name) and c.id != "__name__" for c in node.comparators)

        if (left_name and right_const) or (left_const and right_name):
            # Also ensure we don't count comparisons to __main__
            is_boilerplate = False
            if left_name and node.left.id == "__name__":
                is_boilerplate = True
            for c in node.comparators:
                if isinstance(c, ast.Name) and c.id == "__name__":
                    is_boilerplate = True
                if isinstance(c, ast.Constant) and c.value == "__main__":
                    is_boilerplate = True
            if isinstance(node.left, ast.Constant) and node.left.value == "__main__":
                is_boilerplate = True
                
            if not is_boilerplate:
                self.hardcode_count += 1
                # Log the static values checked
                for c in node.comparators:
                    if isinstance(c, ast.Constant):
                        self.constants_checked.append(str(c.value))
                    elif isinstance(c, (ast.List, ast.Tuple)):
                        self.constants_checked.append("LIST/TUPLE")
        
        self.generic_visit(node)

def inspect_hardcoding(filepath):
    """Statically scans a file for hardcoded test-case checks."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filepath)
        inspector = HardcodeInspector()
        inspector.visit(tree)
        return inspector.hardcode_count, inspector.constants_checked
    except Exception:
        return 0, []

def trusted_binary_search(arr, target):
    """Reference implementation of binary search to compare student answers against."""
    try:
        return arr.index(target)
    except ValueError:
        return -1

def dynamic_fuzz_test(filepath, function_name="search"):
    """
    Dynamically loads the student function and runs 15 randomized fuzz inputs.
    Compares outputs against the trusted reference solver.
    """
    if not os.path.exists(filepath):
        return False, "File not found"

    # 1. Dynamically import student's module
    module_name = "student_code_fuzz"
    try:
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        # Suppress any output prints when loading student code
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        spec.loader.exec_module(module)
        sys.stdout = old_stdout
    except Exception as e:
        sys.stdout = old_stdout
        return False, f"Module load compilation error: {e}"

    # Verify function exists
    if not hasattr(module, function_name):
        return False, f"Function '{function_name}' not found in file"

    student_fn = getattr(module, function_name)

    # 2. Run 15 randomized fuzz checks
    for run in range(15):
        # Generate random sorted list of size 5 to 25
        size = random.randint(5, 25)
        arr = sorted(random.sample(range(-50, 100), size))
        
        # Decide if target is in the list or not
        if random.choice([True, False]):
            target = random.choice(arr)
        else:
            target = random.randint(-100, 150)
            
        try:
            expected = trusted_binary_search(arr, target)
            actual = student_fn(arr, target)
            
            if actual != expected:
                return False, f"Fuzz test failed on inputs: arr={arr}, target={target}. Expected: {expected}, Got: {actual}"
        except Exception as e:
            return False, f"Fuzz test raised exception on inputs: arr={arr}, target={target}. Error: {e}"

    return True, "Passed all fuzz test scenarios"
