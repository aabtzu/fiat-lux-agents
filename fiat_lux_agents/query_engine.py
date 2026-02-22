"""
QueryEngine - safe pandas query execution and Plotly figure execution.
Validates code against a blocklist, then executes in a restricted namespace.
"""

import pandas as pd
import numpy as np
import ast
try:
    import scipy.stats as _scipy_stats
except ImportError:
    _scipy_stats = None

# Long, unambiguous strings safe to check as substrings in code text
BLOCKED_SUBSTRINGS = {
    '__import__', '__builtins__', '__class__', '__dict__', '__code__',
    'subprocess', 'importlib', 'execfile', 'raw_input',
}

# All blocked identifiers — checked at AST level (function calls + import names)
# Short names like 'os'/'sys' must only be checked by AST to avoid false positives
# (e.g. 'os' appears in 'position', 'annotation_position', etc.)
BLOCKED_CALLS = {
    'eval', 'exec', '__import__', 'open', 'compile', 'globals', 'locals',
    'vars', 'dir', 'getattr', 'setattr', 'delattr', 'hasattr', 'callable',
    'os', 'sys', 'subprocess', 'importlib', 'pickle', 'shelve',
    'input', 'raw_input', 'file', 'execfile',
}

# Keep for backwards-compat (used by external callers checking the set)
BLOCKED_OPERATIONS = BLOCKED_SUBSTRINGS | BLOCKED_CALLS


class QueryValidationError(Exception):
    pass


def validate_query(query_code: str):
    """
    Validate that query code only uses safe operations.
    Raises QueryValidationError if dangerous operations are detected.
    """
    if not query_code or not isinstance(query_code, str):
        raise QueryValidationError("Query code must be a non-empty string")

    # Substring check — only for long, unambiguous strings
    query_lower = query_code.lower()
    for blocked in BLOCKED_SUBSTRINGS:
        if blocked in query_lower:
            raise QueryValidationError(f"Blocked operation: {blocked}")

    try:
        tree = ast.parse(query_code)
    except SyntaxError as e:
        raise QueryValidationError(f"Invalid Python syntax: {e}")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise QueryValidationError("Import statements are not allowed")
        if isinstance(node, ast.FunctionDef):
            raise QueryValidationError("Function definitions are not allowed")
        if isinstance(node, ast.ClassDef):
            raise QueryValidationError("Class definitions are not allowed")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                raise QueryValidationError(f"Blocked function call: {node.func.id}")

    return True


def execute_query(query_code: str, df: pd.DataFrame, max_rows: int = 1000) -> dict:
    """
    Execute a validated pandas query against a DataFrame.

    The query code must assign its result to a variable named 'result'.

    Args:
        query_code: Python code string (e.g. "result = df.groupby('category')['value'].mean()")
        df: The DataFrame to query
        max_rows: Maximum rows to return

    Returns:
        dict with 'success', 'data', and optionally 'error', 'columns', 'row_count'
    """
    try:
        validate_query(query_code)
    except QueryValidationError as e:
        return {'success': False, 'error': f"Validation failed: {str(e)}"}

    safe_namespace = {
        'pd': pd,
        'np': np,
        'scipy_stats': _scipy_stats,
        'df': df.copy(),
        '__builtins__': {
            'len': len, 'max': max, 'min': min, 'sum': sum,
            'abs': abs, 'round': round, 'sorted': sorted,
            'list': list, 'dict': dict, 'str': str,
            'int': int, 'float': float, 'bool': bool,
            'True': True, 'False': False, 'None': None,
            'range': range, 'enumerate': enumerate, 'zip': zip,
            'print': print,
        }
    }

    try:
        exec(query_code, safe_namespace)
        result = safe_namespace.get('result')

        if result is None:
            return {'success': False, 'error': 'Query must assign result to a variable named "result"'}

        if isinstance(result, pd.DataFrame):
            if len(result) > max_rows:
                result = result.head(max_rows)
            return {
                'success': True,
                'data': result.to_dict(orient='records'),
                'columns': result.columns.tolist(),
                'row_count': len(result),
                'truncated': len(result) >= max_rows
            }
        elif isinstance(result, pd.Series):
            # Convert to single-column DataFrame so callers always get {data, columns}
            name = result.name if result.name is not None else 'value'
            df_result = result.dropna().to_frame(name=name)
            if len(df_result) > max_rows:
                df_result = df_result.head(max_rows)
            return {
                'success': True,
                'data': df_result.to_dict(orient='records'),
                'columns': df_result.columns.tolist(),
                'row_count': len(df_result),
                'truncated': len(df_result) >= max_rows,
            }
        elif isinstance(result, (list, dict, str, int, float, bool)):
            return {'success': True, 'data': result, 'type': type(result).__name__}
        else:
            return {'success': False, 'error': f'Unsupported result type: {type(result).__name__}'}

    except Exception as e:
        return {'success': False, 'error': f'Execution error: {str(e)}'}


def execute_fig_code(fig_code: str, df: pd.DataFrame, result: pd.DataFrame = None) -> dict:
    """
    Execute Plotly figure code safely.

    The code must assign a Plotly figure to a variable named 'fig'.
    Available in the execution namespace: df, result, px, go, pd, np.

    Args:
        fig_code: Python code that assigns a Plotly figure to 'fig'
        df: The full DataFrame
        result: Optional result DataFrame from a prior execute_query call

    Returns:
        {'success': True, 'fig_json': '<plotly json string>'}
        or {'success': False, 'error': '...'}
    """
    if not fig_code or not isinstance(fig_code, str):
        return {'success': False, 'error': 'No fig_code provided'}

    try:
        validate_query(fig_code)
    except QueryValidationError as e:
        return {'success': False, 'error': f'Validation failed: {str(e)}'}

    try:
        import plotly.express as px
        import plotly.graph_objects as go
    except ImportError:
        return {'success': False, 'error': 'plotly is not installed'}

    safe_namespace = {
        'df': df.copy(),
        'result': result,
        'px': px,
        'go': go,
        'pd': pd,
        'np': np,
        'scipy_stats': _scipy_stats,
        '__builtins__': {
            'len': len, 'max': max, 'min': min, 'sum': sum,
            'abs': abs, 'round': round, 'sorted': sorted,
            'list': list, 'dict': dict, 'str': str,
            'int': int, 'float': float, 'bool': bool,
            'True': True, 'False': False, 'None': None,
            'range': range, 'enumerate': enumerate, 'zip': zip,
            'print': print,
        }
    }

    try:
        exec(fig_code, safe_namespace)
        fig = safe_namespace.get('fig')

        if fig is None:
            return {'success': False, 'error': 'fig_code must assign a Plotly figure to a variable named "fig"'}

        return {'success': True, 'fig_json': fig.to_json()}

    except Exception as e:
        return {'success': False, 'error': f'Execution error: {str(e)}'}
