"""
QueryEngine - safe pandas query execution.
Validates code against a blocklist, then executes in a restricted namespace.
"""

import pandas as pd
import ast

BLOCKED_OPERATIONS = {
    'eval', 'exec', '__import__', 'open', 'compile', 'globals', 'locals',
    'vars', 'dir', '__builtins__', 'getattr', 'setattr', 'delattr',
    'hasattr', 'callable', '__class__', '__dict__', '__code__',
    'os', 'sys', 'subprocess', 'importlib', 'pickle', 'shelve',
    'input', 'raw_input', 'file', 'execfile'
}


class QueryValidationError(Exception):
    pass


def validate_query(query_code: str):
    """
    Validate that query code only uses safe operations.
    Raises QueryValidationError if dangerous operations are detected.
    """
    if not query_code or not isinstance(query_code, str):
        raise QueryValidationError("Query code must be a non-empty string")

    query_lower = query_code.lower()
    for blocked in BLOCKED_OPERATIONS:
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
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_OPERATIONS:
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
        'df': df.copy(),
        '__builtins__': {
            'len': len, 'max': max, 'min': min, 'sum': sum,
            'abs': abs, 'round': round, 'sorted': sorted,
            'list': list, 'dict': dict, 'str': str,
            'int': int, 'float': float, 'bool': bool,
            'True': True, 'False': False, 'None': None,
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
