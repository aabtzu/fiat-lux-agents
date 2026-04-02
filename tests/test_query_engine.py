"""Tests for query_engine.py — execute_query and execute_fig_code.

No API calls or network access. All tests use a small toy DataFrame.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
import pandas as pd

from fiat_lux_agents.query_engine import (
    execute_query,
    execute_fig_code,
    validate_query,
    QueryValidationError,
)

# Shared toy DataFrame
_DF = pd.DataFrame({
    'city':   ['Austin', 'Denver', 'Miami', 'Seattle', 'Boston'],
    'price':  [450_000, 520_000, 610_000, 750_000, 680_000],
    'days':   [14, 21, 10, 18, 25],
    'region': ['South', 'West', 'South', 'West', 'East'],
})


class TestValidateQuery(unittest.TestCase):

    def test_valid_query_passes(self):
        validate_query("result = df[df.price > 500000]")

    def test_blocked_substring(self):
        with self.assertRaises(QueryValidationError):
            validate_query("result = __import__('os').system('rm -rf /')")

    def test_blocked_call_eval(self):
        with self.assertRaises(QueryValidationError):
            validate_query("result = eval('1+1')")

    def test_import_statement_blocked(self):
        with self.assertRaises(QueryValidationError):
            validate_query("import os\nresult = df")

    def test_function_def_blocked(self):
        with self.assertRaises(QueryValidationError):
            validate_query("def foo(): pass\nresult = df")

    def test_syntax_error(self):
        with self.assertRaises(QueryValidationError):
            validate_query("result = df[")


class TestExecuteQuery(unittest.TestCase):

    def test_basic_filter(self):
        r = execute_query("result = df[df.price > 700000]", _DF)
        self.assertTrue(r['success'])
        self.assertEqual(len(r['data']), 1)  # only Seattle (750k)

    def test_result_variable_required(self):
        r = execute_query("x = df[df.price > 0]", _DF)
        self.assertFalse(r['success'])
        self.assertIn('result', r['error'])

    def test_max_rows_respected(self):
        r = execute_query("result = df", _DF, max_rows=2)
        self.assertTrue(r['success'])
        self.assertEqual(len(r['data']), 2)

    def test_groupby_returns_correct_shape(self):
        r = execute_query(
            "result = df.groupby('region')['price'].mean().reset_index()",
            _DF,
        )
        self.assertTrue(r['success'])
        self.assertIn('region', r['columns'])
        self.assertIn('price', r['columns'])

    def test_series_result_converted_to_dataframe(self):
        r = execute_query("result = df['price']", _DF)
        self.assertTrue(r['success'])
        self.assertIsInstance(r['data'], list)
        self.assertIn('columns', r)

    def test_bad_code_returns_error(self):
        r = execute_query("result = df['nonexistent_column']", _DF)
        self.assertFalse(r['success'])
        self.assertIn('error', r)

    def test_columns_in_response(self):
        r = execute_query("result = df[['city', 'price']]", _DF)
        self.assertTrue(r['success'])
        self.assertEqual(sorted(r['columns']), ['city', 'price'])

    def test_import_stripped_before_execution(self):
        # LLM sometimes emits imports; they should be stripped silently
        code = "import pandas as pd\nresult = df[df.days < 20]"
        r = execute_query(code, _DF)
        self.assertTrue(r['success'])

    def test_scalar_result(self):
        r = execute_query("result = int(df['price'].max())", _DF)
        self.assertTrue(r['success'])
        self.assertEqual(r['data'], 750_000)

    def test_empty_dataframe_input(self):
        empty = pd.DataFrame(columns=['city', 'price'])
        r = execute_query("result = df", empty)
        self.assertTrue(r['success'])
        self.assertEqual(r['data'], [])


class TestExecuteFigCode(unittest.TestCase):

    def test_basic_bar_chart(self):
        code = "fig = px.bar(_DF, x='city', y='price')"
        # fig_code uses 'df' not '_DF'
        code = "fig = px.bar(df, x='city', y='price')"
        r = execute_fig_code(code, _DF)
        self.assertTrue(r['success'])
        self.assertIn('fig_json', r)

    def test_fig_variable_required(self):
        r = execute_fig_code("chart = px.bar(df, x='city', y='price')", _DF)
        self.assertFalse(r['success'])
        self.assertIn('fig', r['error'])

    def test_bad_code_returns_error(self):
        r = execute_fig_code("fig = px.bar(df, x='nonexistent')", _DF)
        self.assertFalse(r['success'])
        self.assertIn('error', r)

    def test_uses_result_dataframe(self):
        result_df = _DF[_DF.region == 'West']
        code = "fig = px.bar(result, x='city', y='price')"
        r = execute_fig_code(code, _DF, result=result_df)
        self.assertTrue(r['success'])

    def test_empty_code_returns_error(self):
        r = execute_fig_code("", _DF)
        self.assertFalse(r['success'])

    def test_fig_json_is_valid_json(self):
        import json
        code = "fig = px.scatter(df, x='days', y='price')"
        r = execute_fig_code(code, _DF)
        self.assertTrue(r['success'])
        parsed = json.loads(r['fig_json'])
        self.assertIn('data', parsed)


if __name__ == '__main__':
    unittest.main()
