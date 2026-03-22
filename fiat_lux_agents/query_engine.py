"""
QueryEngine - safe pandas query execution and Plotly figure execution.
Validates code against a blocklist, then executes in a restricted namespace.
"""

import pandas as pd
import numpy as np
import ast
import json
from functools import lru_cache
from urllib.request import urlopen
try:
    import scipy.stats as _scipy_stats
except ImportError:
    _scipy_stats = None

try:
    import sklearn.linear_model as _skl_linear
    import sklearn.preprocessing as _skl_pre
    import sklearn.metrics as _skl_metrics
    import sklearn.model_selection as _skl_ms
    import sklearn.ensemble as _skl_ensemble
    import sklearn.cluster as _skl_cluster
    import sklearn as _sklearn
    _sklearn_available = True
except ImportError:
    _sklearn_available = False

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


def _df_to_records(df: pd.DataFrame) -> list:
    """Convert DataFrame to JSON-safe records (NaN → None, mixed dtypes handled)."""
    # Coerce object columns that contain mixed numeric/None — avoids pandas 2+ dtype errors
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col], errors='ignore')
            except Exception:
                pass
    return json.loads(df.to_json(orient='records'))


def _strip_imports(code: str) -> str:
    """Remove import lines from LLM-generated code.

    The execution namespace already has pd, np, px, go, scipy_stats pre-loaded,
    so import lines are redundant and only cause validation failures.
    """
    clean = []
    for line in code.splitlines():
        stripped = line.lstrip()
        if stripped.startswith('import ') or stripped.startswith('from ') and ' import ' in stripped:
            continue
        clean.append(line)
    return '\n'.join(clean)


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
    query_code = _strip_imports(query_code)
    try:
        validate_query(query_code)
    except QueryValidationError as e:
        return {'success': False, 'error': f"Validation failed: {str(e)}"}

    safe_namespace = {
        'pd': pd,
        'np': np,
        'scipy_stats': _scipy_stats,
        'df': df.copy(),
        # sklearn submodules — pre-imported so LLM code can use them without import statements
        **({'sklearn': _sklearn,
            'LinearRegression':      _skl_linear.LinearRegression,
            'LogisticRegression':    _skl_linear.LogisticRegression,
            'Ridge':                 _skl_linear.Ridge,
            'Lasso':                 _skl_linear.Lasso,
            'StandardScaler':        _skl_pre.StandardScaler,
            'LabelEncoder':          _skl_pre.LabelEncoder,
            'OneHotEncoder':         _skl_pre.OneHotEncoder,
            'train_test_split':      _skl_ms.train_test_split,
            'cross_val_score':       _skl_ms.cross_val_score,
            'r2_score':              _skl_metrics.r2_score,
            'mean_squared_error':    _skl_metrics.mean_squared_error,
            'accuracy_score':        _skl_metrics.accuracy_score,
            'classification_report': _skl_metrics.classification_report,
            'RandomForestClassifier':_skl_ensemble.RandomForestClassifier,
            'RandomForestRegressor': _skl_ensemble.RandomForestRegressor,
            'KMeans':                _skl_cluster.KMeans,
           } if _sklearn_available else {}),
        '__builtins__': {
            'len': len, 'max': max, 'min': min, 'sum': sum,
            'abs': abs, 'round': round, 'sorted': sorted,
            'list': list, 'dict': dict, 'str': str,
            'int': int, 'float': float, 'bool': bool,
            'True': True, 'False': False, 'None': None,
            'range': range, 'enumerate': enumerate, 'zip': zip,
            'print': print,
            '__import__': __import__,  # numpy needs this for internal lazy imports
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
                'data': _df_to_records(result),
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
                'data': _df_to_records(df_result),
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


_STATE_SLUGS = {
    'AL': 'al_alabama', 'AK': 'ak_alaska', 'AZ': 'az_arizona', 'AR': 'ar_arkansas',
    'CA': 'ca_california', 'CO': 'co_colorado', 'CT': 'ct_connecticut', 'DE': 'de_delaware',
    'FL': 'fl_florida', 'GA': 'ga_georgia', 'HI': 'hi_hawaii', 'ID': 'id_idaho',
    'IL': 'il_illinois', 'IN': 'in_indiana', 'IA': 'ia_iowa', 'KS': 'ks_kansas',
    'KY': 'ky_kentucky', 'LA': 'la_louisiana', 'ME': 'me_maine', 'MD': 'md_maryland',
    'MA': 'ma_massachusetts', 'MI': 'mi_michigan', 'MN': 'mn_minnesota', 'MS': 'ms_mississippi',
    'MO': 'mo_missouri', 'MT': 'mt_montana', 'NE': 'ne_nebraska', 'NV': 'nv_nevada',
    'NH': 'nh_new_hampshire', 'NJ': 'nj_new_jersey', 'NM': 'nm_new_mexico', 'NY': 'ny_new_york',
    'NC': 'nc_north_carolina', 'ND': 'nd_north_dakota', 'OH': 'oh_ohio', 'OK': 'ok_oklahoma',
    'OR': 'or_oregon', 'PA': 'pa_pennsylvania', 'RI': 'ri_rhode_island', 'SC': 'sc_south_carolina',
    'SD': 'sd_south_dakota', 'TN': 'tn_tennessee', 'TX': 'tx_texas', 'UT': 'ut_utah',
    'VT': 'vt_vermont', 'VA': 'va_virginia', 'WA': 'wa_washington', 'WV': 'wv_west_virginia',
    'WI': 'wi_wisconsin', 'WY': 'wy_wyoming', 'DC': 'dc_district_of_columbia',
}

@lru_cache(maxsize=60)
def _fetch_zip_geojson(state_abbr: str) -> dict:
    slug = _STATE_SLUGS.get(state_abbr.upper())
    if not slug:
        raise ValueError(f"Unknown state abbreviation: {state_abbr}")
    url = f"https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/{slug}_zip_codes_geo.min.json"
    with urlopen(url) as r:
        return json.load(r)


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

    fig_code = _strip_imports(fig_code)
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
        'get_zip_geojson': _fetch_zip_geojson,
        **({'sklearn': _sklearn,
            'LinearRegression':      _skl_linear.LinearRegression,
            'LogisticRegression':    _skl_linear.LogisticRegression,
            'Ridge':                 _skl_linear.Ridge,
            'Lasso':                 _skl_linear.Lasso,
            'StandardScaler':        _skl_pre.StandardScaler,
            'LabelEncoder':          _skl_pre.LabelEncoder,
            'OneHotEncoder':         _skl_pre.OneHotEncoder,
            'train_test_split':      _skl_ms.train_test_split,
            'cross_val_score':       _skl_ms.cross_val_score,
            'r2_score':              _skl_metrics.r2_score,
            'mean_squared_error':    _skl_metrics.mean_squared_error,
            'accuracy_score':        _skl_metrics.accuracy_score,
            'classification_report': _skl_metrics.classification_report,
            'RandomForestClassifier':_skl_ensemble.RandomForestClassifier,
            'RandomForestRegressor': _skl_ensemble.RandomForestRegressor,
            'KMeans':                _skl_cluster.KMeans,
           } if _sklearn_available else {}),
        '__builtins__': {
            'len': len, 'max': max, 'min': min, 'sum': sum,
            'abs': abs, 'round': round, 'sorted': sorted,
            'list': list, 'dict': dict, 'str': str,
            'int': int, 'float': float, 'bool': bool,
            'True': True, 'False': False, 'None': None,
            'range': range, 'enumerate': enumerate, 'zip': zip,
            'print': print,
            '__import__': __import__,
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
