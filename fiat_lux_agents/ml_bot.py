"""
MLBot - flexible ML modeling agent for tabular DataFrames.

Handles the full modeling workflow in a single call:
  1. Preprocessing  (encoding, scaling, train/test split)
  2. Model training (sklearn | Keras/TF | HuggingFace transformers)
  3. Evaluation     (metrics, feature importance, predictions)
  4. Visualization  (Plotly chart)

Returns a structured dict every time:
  {
    "answer":             str   — plain-text summary of approach and results
    "metrics":            dict  — {"R2": 0.85} or {"accuracy": 0.87, "AUC": 0.91}
    "feature_importance": list  — [{"Feature": "x", "Importance": 0.3}, ...] or None
    "predictions":        list  — [{"id": 1, "predicted_churn": False}, ...] or None
    "fig_json":           str   — Plotly figure JSON or None
    "model_code":         str   — the executed code (for inspection / debugging)
    "error":              str   — execution error message, or None
  }

Usage:
    bot = MLBot(schema=MY_SCHEMA)
    result = bot.run(df, "train a random forest to predict churn")
    result = bot.run(df, "cluster employees into groups using KMeans")
    result = bot.run(df, "build a small neural net to predict salary")
"""

import ast
import json
import re
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .base import LLMBase, DEFAULT_MODEL
from .query_engine import _strip_imports, BLOCKED_SUBSTRINGS

# ── Optional ML backends ──────────────────────────────────────────────────────

try:
    from sklearn.linear_model import (
        LinearRegression, LogisticRegression, Ridge, Lasso, ElasticNet,
    )
    from sklearn.ensemble import (
        RandomForestClassifier, RandomForestRegressor,
        GradientBoostingClassifier, GradientBoostingRegressor,
        ExtraTreesClassifier, ExtraTreesRegressor,
    )
    from sklearn.svm import SVC, SVR
    from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
    from sklearn.preprocessing import (
        StandardScaler, MinMaxScaler, LabelEncoder, OneHotEncoder,
        PolynomialFeatures,
    )
    from sklearn.model_selection import (
        train_test_split, cross_val_score, GridSearchCV, StratifiedKFold,
    )
    from sklearn.metrics import (
        r2_score, mean_squared_error, mean_absolute_error,
        accuracy_score, roc_auc_score, f1_score,
        classification_report, confusion_matrix,
    )
    from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    import sklearn as _sklearn
    _sklearn_available = True
except ImportError:
    _sklearn_available = False

try:
    import tensorflow as tf
    import tensorflow.keras as keras
    import tensorflow.keras.layers as layers
    _tf_available = True
except ImportError:
    try:
        import keras
        import keras.layers as layers
        tf = None
        _tf_available = True
    except ImportError:
        tf = None
        keras = None
        layers = None
        _tf_available = False

try:
    import transformers as _transformers
    from transformers import pipeline as _hf_pipeline
    _transformers_available = True
except ImportError:
    _transformers = None
    _hf_pipeline = None
    _transformers_available = False


# ── MLBot ─────────────────────────────────────────────────────────────────────

class MLBot(LLMBase):
    """
    ML modeling agent. Generates and executes a full sklearn/Keras/HuggingFace
    pipeline from a natural language task description.

    Args:
        schema:     Dataset schema string (column names, types, description).
        model:      Claude model ID.
        max_tokens: Max tokens in the response (default 8192 — code can be long).

    Usage:
        bot = MLBot(schema=MY_SCHEMA)

        # Classification
        result = bot.run(df, "predict churn using a random forest")

        # Regression
        result = bot.run(df, "predict salary from tenure, performance, education")

        # Clustering
        result = bot.run(df, "cluster employees into segments using KMeans")

        # Neural net
        result = bot.run(df, "build a small neural net to predict salary")

        # Multi-turn
        result = bot.run(df, "now try gradient boosting instead", history=history)
    """

    def __init__(
        self,
        schema: str = "",
        model: str = DEFAULT_MODEL,
        max_tokens: int = 8192,
    ):
        super().__init__(model=model, max_tokens=max_tokens)
        self._schema = schema
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        backends = []
        if _sklearn_available:
            backends.append("sklearn")
        if _tf_available:
            backends.append("Keras/TensorFlow")
        if _transformers_available:
            backends.append("HuggingFace transformers")
        available_str = ", ".join(backends) if backends else "none detected"

        return f"""You are an expert ML engineer. Given a tabular dataset and a modeling task, generate a complete, executable ML pipeline.

Dataset schema:
{self._schema}

Available backends: {available_str}

RESPONSE FORMAT — return ONLY this JSON (exactly 3 fields, no other keys):
{{
  "answer":     "Plain-text summary: model type, key metrics, top features, any caveats.",
  "model_code": "Python code — see rules below.",
  "fig_code":   "Plotly visualization code — see rules below, or null."
}}

═══════════════════════════════
MODEL CODE RULES
═══════════════════════════════

NO import statements — everything is pre-injected. Available names:

  Data:       df (the DataFrame — work on a copy), pd, np
  sklearn:    LinearRegression, LogisticRegression, Ridge, Lasso, ElasticNet,
              RandomForestClassifier, RandomForestRegressor,
              GradientBoostingClassifier, GradientBoostingRegressor,
              ExtraTreesClassifier, ExtraTreesRegressor,
              SVC, SVR, KNeighborsClassifier, KNeighborsRegressor,
              DecisionTreeClassifier, DecisionTreeRegressor,
              StandardScaler, MinMaxScaler, LabelEncoder, OneHotEncoder,
              PolynomialFeatures, train_test_split, cross_val_score,
              GridSearchCV, StratifiedKFold,
              r2_score, mean_squared_error, mean_absolute_error,
              accuracy_score, roc_auc_score, f1_score,
              classification_report, confusion_matrix,
              KMeans, DBSCAN, AgglomerativeClustering, silhouette_score, PCA
  Keras/TF:   keras, tf, layers  (keras.Sequential, layers.Dense, layers.Dropout, etc.)
  HuggingFace: transformers, pipeline  (pipeline('text-classification', ...) etc.)

MUST assign all 3 output variables (set to None if not applicable):

  metrics            — dict: {{"R2": 0.85, "RMSE": 1200}} or {{"accuracy": 0.87, "AUC": 0.91}}
  feature_importance — pd.DataFrame with columns ["Feature", "Importance"], sorted descending, or None
  predictions        — pd.DataFrame with the original 'id' column + "predicted_<target>" column, or None

DTYPE RULE: pd.get_dummies returns bool in pandas 2+. Always cast:
  X = pd.get_dummies(df[cols], drop_first=True).astype(float)

SKLEARN PATTERN:
  data = df.copy().dropna(subset=[target])
  X = pd.get_dummies(data[feature_cols], drop_first=True).astype(float)
  y = data[target]
  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
  model = RandomForestClassifier(n_estimators=100, random_state=42)
  model.fit(X_train, y_train)
  y_pred = model.predict(X_test)
  metrics = {{"accuracy": round(accuracy_score(y_test, y_pred), 4)}}
  if len(y.unique()) == 2:
      metrics["AUC"] = round(roc_auc_score(y_test, model.predict_proba(X_test)[:,1]), 4)
  feature_importance = pd.DataFrame({{"Feature": X.columns, "Importance": model.feature_importances_}}).sort_values("Importance", ascending=False)
  predictions = pd.DataFrame({{"id": data["id"].values, "predicted_" + target: model.predict(X)}})

KERAS PATTERN (tabular, small net):
  # Prepare data as above, then:
  model = keras.Sequential([
      layers.Dense(64, activation='relu', input_shape=(X_train.shape[1],)),
      layers.Dropout(0.2),
      layers.Dense(32, activation='relu'),
      layers.Dense(1, activation='sigmoid'),  # or 'linear' for regression
  ])
  model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
  model.fit(X_train_scaled, y_train, epochs=50, batch_size=32, verbose=0, validation_split=0.1)
  # feature_importance = None  (neural nets don't have direct feature importance)

CLUSTERING PATTERN:
  model = KMeans(n_clusters=4, random_state=42, n_init=10)
  labels = model.fit_predict(X_scaled)
  metrics = {{"inertia": round(model.inertia_, 2), "n_clusters": 4, "silhouette": round(silhouette_score(X_scaled, labels), 4)}}
  feature_importance = None
  predictions = pd.DataFrame({{"id": data["id"].values, "cluster": labels}})

═══════════════════════════════
FIG CODE RULES
═══════════════════════════════

NO imports. Pre-injected: px, go, pd, np, plus all output variables from model_code.
Available: df, metrics, feature_importance, predictions

MUST assign a Plotly figure to 'fig'. Good choices:
  - Feature importance: horizontal bar of top 15 features
  - Regression: scatter actual vs predicted with trendline
  - Classification: bar of top features or confusion matrix heatmap
  - Clustering: scatter colored by cluster (use first 2 PCA components if >2 dims)
  - Always include key metrics in the chart title or subtitle

CRITICAL: Return ONLY valid JSON. No markdown fences. Escape all newlines as \\n in code strings."""

    def run(
        self,
        df: pd.DataFrame,
        task: str,
        history: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Run an ML modeling task against a DataFrame.

        Args:
            df:      The DataFrame to model.
            task:    Natural language description (e.g. "predict churn with random forest").
            history: Optional list of prior {"role", "content"} turns.

        Returns:
            dict with keys: answer, metrics, feature_importance, predictions,
                            fig_json, model_code, error
        """
        messages = []
        if history:
            for turn in history[-4:]:
                if turn.get("role") in ("user", "assistant") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": task})

        try:
            raw = self.call_api(self.system_prompt, messages)
        except Exception as e:
            return _error_result(str(e))

        # Parse JSON response
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    return _error_result(f"Could not parse LLM response: {raw[:300]}")
            else:
                return _error_result(f"No JSON in LLM response: {raw[:300]}")

        answer     = parsed.get("answer", "")
        model_code = parsed.get("model_code") or ""
        fig_code   = parsed.get("fig_code")

        # Execute model code
        exec_result = _execute_ml_code(model_code, df)
        if not exec_result["success"]:
            return {
                "answer": answer, "metrics": None, "feature_importance": None,
                "predictions": None, "fig_json": None,
                "model_code": model_code, "error": exec_result["error"],
            }

        ns = exec_result["namespace"]
        metrics = ns.get("metrics")

        # feature_importance → list of dicts
        fi_df = ns.get("feature_importance")
        feature_importance = None
        if isinstance(fi_df, pd.DataFrame) and not fi_df.empty:
            feature_importance = json.loads(
                fi_df.head(30).to_json(orient="records")
            )

        # predictions → list of dicts (capped at 1000 rows)
        pred_df = ns.get("predictions")
        predictions = None
        if isinstance(pred_df, pd.DataFrame) and not pred_df.empty:
            predictions = json.loads(pred_df.head(1000).to_json(orient="records"))

        # Execute fig code
        fig_json = None
        fig_error = None
        if fig_code:
            fig_result = _execute_fig_ml_code(fig_code, df, ns)
            if fig_result["success"]:
                fig_json = fig_result["fig_json"]
            else:
                fig_error = fig_result["error"]

        return {
            "answer":             answer,
            "metrics":            metrics,
            "feature_importance": feature_importance,
            "predictions":        predictions,
            "fig_json":           fig_json,
            "model_code":         model_code,
            "error":              fig_error,
        }


# ── Execution helpers ─────────────────────────────────────────────────────────

def _build_ml_namespace(df: pd.DataFrame) -> dict:
    """Build the pre-injected namespace for ML code execution."""
    ns = {
        "df": df.copy(),
        "pd": pd,
        "np": np,
        "__builtins__": {
            "len": len, "max": max, "min": min, "sum": sum,
            "abs": abs, "round": round, "sorted": sorted,
            "list": list, "dict": dict, "tuple": tuple,
            "str": str, "int": int, "float": float, "bool": bool,
            "True": True, "False": False, "None": None,
            "range": range, "enumerate": enumerate, "zip": zip,
            "print": print, "isinstance": isinstance, "type": type,
            "zip": zip, "map": map, "filter": filter,
            "__import__": __import__,   # needed by numpy/tf internals
        },
    }

    if _sklearn_available:
        ns.update({
            "LinearRegression": LinearRegression,
            "LogisticRegression": LogisticRegression,
            "Ridge": Ridge, "Lasso": Lasso, "ElasticNet": ElasticNet,
            "RandomForestClassifier": RandomForestClassifier,
            "RandomForestRegressor": RandomForestRegressor,
            "GradientBoostingClassifier": GradientBoostingClassifier,
            "GradientBoostingRegressor": GradientBoostingRegressor,
            "ExtraTreesClassifier": ExtraTreesClassifier,
            "ExtraTreesRegressor": ExtraTreesRegressor,
            "SVC": SVC, "SVR": SVR,
            "KNeighborsClassifier": KNeighborsClassifier,
            "KNeighborsRegressor": KNeighborsRegressor,
            "DecisionTreeClassifier": DecisionTreeClassifier,
            "DecisionTreeRegressor": DecisionTreeRegressor,
            "StandardScaler": StandardScaler, "MinMaxScaler": MinMaxScaler,
            "LabelEncoder": LabelEncoder, "OneHotEncoder": OneHotEncoder,
            "PolynomialFeatures": PolynomialFeatures,
            "train_test_split": train_test_split,
            "cross_val_score": cross_val_score,
            "GridSearchCV": GridSearchCV,
            "StratifiedKFold": StratifiedKFold,
            "r2_score": r2_score,
            "mean_squared_error": mean_squared_error,
            "mean_absolute_error": mean_absolute_error,
            "accuracy_score": accuracy_score,
            "roc_auc_score": roc_auc_score,
            "f1_score": f1_score,
            "classification_report": classification_report,
            "confusion_matrix": confusion_matrix,
            "KMeans": KMeans, "DBSCAN": DBSCAN,
            "AgglomerativeClustering": AgglomerativeClustering,
            "silhouette_score": silhouette_score,
            "PCA": PCA,
        })

    if _tf_available:
        ns.update({"keras": keras, "tf": tf, "layers": layers})

    if _transformers_available:
        ns.update({"transformers": _transformers, "pipeline": _hf_pipeline})

    return ns


def _validate_ml_code(code: str):
    """Validate ML code — blocks dangerous patterns, allows ML imports to be stripped."""
    code_lower = code.lower()
    for blocked in BLOCKED_SUBSTRINGS:
        if blocked in code_lower:
            raise ValueError(f"Blocked: {blocked}")

    tree = ast.parse(code)
    blocked_calls = {"eval", "exec", "open", "compile", "globals", "locals"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            raise ValueError("Function definitions not allowed")
        if isinstance(node, ast.ClassDef):
            raise ValueError("Class definitions not allowed")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in blocked_calls:
                raise ValueError(f"Blocked call: {node.func.id}")


def _execute_ml_code(code: str, df: pd.DataFrame) -> dict:
    """Strip imports, validate, and execute ML model code."""
    if not code:
        return {"success": False, "error": "No model_code provided", "namespace": {}}

    code = _strip_imports(code)

    try:
        _validate_ml_code(code)
    except (ValueError, SyntaxError) as e:
        return {"success": False, "error": f"Validation error: {e}", "namespace": {}}

    ns = _build_ml_namespace(df)
    try:
        exec(code, ns)
        return {"success": True, "namespace": ns}
    except Exception as e:
        return {"success": False, "error": f"Execution error: {e}", "namespace": ns}


def _execute_fig_ml_code(fig_code: str, df: pd.DataFrame, model_ns: dict) -> dict:
    """Execute Plotly fig code with access to model outputs."""
    if not fig_code:
        return {"success": False, "error": "No fig_code provided"}

    fig_code = _strip_imports(fig_code)

    try:
        _validate_ml_code(fig_code)
    except (ValueError, SyntaxError) as e:
        return {"success": False, "error": f"Validation error: {e}"}

    try:
        import plotly.express as px
        import plotly.graph_objects as go
    except ImportError:
        return {"success": False, "error": "plotly not installed"}

    ns = _build_ml_namespace(df)
    ns.update({"px": px, "go": go})
    # Inject model outputs so fig_code can reference them
    for key in ("metrics", "feature_importance", "predictions"):
        ns[key] = model_ns.get(key)

    try:
        exec(fig_code, ns)
        fig = ns.get("fig")
        if fig is None:
            return {"success": False, "error": "fig_code must assign a Plotly figure to 'fig'"}
        return {"success": True, "fig_json": fig.to_json()}
    except Exception as e:
        return {"success": False, "error": f"Execution error: {e}"}


def _error_result(msg: str) -> Dict:
    return {
        "answer": f"Modeling failed: {msg}",
        "metrics": None, "feature_importance": None,
        "predictions": None, "fig_json": None,
        "model_code": None, "error": msg,
    }
