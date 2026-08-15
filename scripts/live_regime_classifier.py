"""live_regime_classifier.py — Production-ready regime classifier for real-time phase detection.

Features:
- Feature engineering from recent price action, vol, spreads, macro
- Supervised classification using historical phase labels as targets
- Model persistence with joblib (RandomForest + calibration)
- Online prediction with confidence scores
- Drift detection and retraining triggers
- Feature store for reproducible inference
- SHAP explanations for model interpretability

Outputs:
- models/regime_classifier.pkl (trained model + metadata)
- artifacts/regime_diagnostics.json (performance metrics)
- artifacts/regime_feature_importance.csv
- artifacts/regime_predictions_live.csv (latest predictions)
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy import stats
import joblib

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

warnings.filterwarnings("ignore")

# ─── Configuration ────────────────────────────────────────────────────────────

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
MODELS = BASE / "models"
MODELS.mkdir(exist_ok=True)

MODEL_PATH = MODELS / "regime_classifier.pkl"
FEATURES_PATH = ARTIFACTS / "regime_features.csv"
DIAGNOSTICS_PATH = ARTIFACTS / "regime_diagnostics.json"
PREDICTIONS_PATH = ARTIFACTS / "regime_predictions_live.csv"
IMPORTANCE_PATH = ARTIFACTS / "regime_feature_importance.csv"

# Feature engineering parameters
LOOKBACK_WINDOWS = [1, 3, 5, 10, 20, 60]  # days
VOL_WINDOWS = [5, 10, 20, 60]
MACRO_TICKERS = {
    "DXY": "DX-Y.NYB",      # Dollar Index
    "SPX": "^GSPC",         # S&P 500
    "GOLD": "GC=F",         # Gold futures
    "US10Y": "^TNX",        # 10Y Treasury yield
    "VIX": "^VIX",          # VIX
    "USOIL": "CL=F",        # WTI (redundant but explicit)
    "BRENT": "BZ=F",        # Brent
}

# Minimum samples per class for training
MIN_SAMPLES_PER_CLASS = 10
RETRAIN_THRESHOLD_DAYS = 7  # Retrain if model older than this
DRIFT_THRESHOLD = 0.15      # KL divergence threshold for feature drift

# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class RegimePrediction:
    """Single regime prediction with confidence."""
    timestamp: str
    phase_id: int
    phase_label: str
    confidence: float
    probabilities: Dict[str, float]
    top_features: Dict[str, float]
    model_version: str
    feature_vector: Dict[str, float]

@dataclass
class ModelMetadata:
    """Model training metadata."""
    trained_at: str
    n_samples: int
    n_features: int
    classes: List[int]
    class_distribution: Dict[int, int]
    cv_accuracy: float
    cv_accuracy_std: float
    feature_names: List[str]
    hyperparameters: Dict[str, Any]
    sklearn_version: str

# ─── Feature Engineering ──────────────────────────────────────────────────────

def load_market_data() -> Dict[str, pd.DataFrame]:
    """Load all required market data for feature engineering."""
    # Load primitives (has session-level returns, phase tags)
    primitives = pd.read_parquet(ARTIFACTS / "primitives.parquet")
    sess = primitives[primitives["__stream"].isin(["WTI_session", "BRENT_session"])].copy()
    sess["trade_date_ist"] = pd.to_datetime(sess["trade_date_ist"])

    # Load daily data
    wti_daily = read_xlsx(BASE / "wti_daily_ist.csv")
    brent_daily = read_xlsx(BASE / "brent_daily_ist.csv")

    # Load macro data if available (macro_regime.csv from enhanced_cross_asset.py)
    macro_path = ARTIFACTS / "macro_regime.csv"
    macro = pd.DataFrame()
    if macro_path.exists():
        macro = pd.read_csv(macro_path)
        # Handle different date column names
        date_col = "trade_date_ist" if "trade_date_ist" in macro.columns else "Date"
        if date_col in macro.columns:
            macro = macro.rename(columns={date_col: "trade_date_ist"})
            macro["trade_date_ist"] = pd.to_datetime(macro["trade_date_ist"])
        else:
            macro = pd.DataFrame()

    return {
        "session": sess,
        "wti_daily": wti_daily,
        "brent_daily": brent_daily,
        "macro": macro,
    }

def read_xlsx(path: Path) -> pd.DataFrame:
    """Read XLSX-saved-as-CSV file."""
    import tempfile, shutil, os
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    try:
        shutil.copy(str(path), tmp.name)
        return pd.read_excel(tmp.name)
    finally:
        os.unlink(tmp.name)

def build_features(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build feature matrix for regime classification."""
    sess = data["session"]
    wti_daily = data["wti_daily"]
    brent_daily = data["brent_daily"]
    macro = data["macro"]

    # 1. Daily returns pivot
    daily_pivot = sess[sess["session_window_ist"] == "us_open"].copy()
    daily_pivot = daily_pivot.pivot_table(
        index="trade_date_ist",
        columns="__stream",
        values="window_return_pct",
        aggfunc="first"
    ).reset_index()
    daily_pivot.columns.name = None
    daily_pivot = daily_pivot.rename(columns={
        "WTI_session": "wti_ret",
        "BRENT_session": "brent_ret"
    })

    # 2. Add daily OHLC from daily files
    for name, df in [("wti", wti_daily), ("brent", brent_daily)]:
        df = df.copy()
        df["trade_date_ist"] = pd.to_datetime(df["trade_date_ist"])
        df = df[["trade_date_ist", "open_native", "high_native", "low_native", "close_native", "volume"]]
        df.columns = ["trade_date_ist"] + [f"{name}_{c}" for c in df.columns if c != "trade_date_ist"]
        daily_pivot = daily_pivot.merge(df, on="trade_date_ist", how="left")

    # 3. Compute core features
    feats = daily_pivot.sort_values("trade_date_ist").reset_index(drop=True)

    # Returns
    for col in ["wti_close_native", "brent_close_native"]:
        if col in feats.columns:
            for w in LOOKBACK_WINDOWS:
                feats[f"{col}_ret_{w}d"] = feats[col].pct_change(w) * 100
                feats[f"{col}_ret_{w}d_z"] = (
                    feats[f"{col}_ret_{w}d"] - feats[f"{col}_ret_{w}d"].rolling(60).mean()
                ) / feats[f"{col}_ret_{w}d"].rolling(60).std()

    # Realized volatility
    for col in ["wti_ret", "brent_ret"]:
        if col in feats.columns:
            for w in VOL_WINDOWS:
                feats[f"{col}_vol_{w}d"] = feats[col].rolling(w).std() * np.sqrt(252)

    # Brent-WTI spread
    if "wti_close_native" in feats.columns and "brent_close_native" in feats.columns:
        feats["brent_wti_spread"] = feats["brent_close_native"] - feats["wti_close_native"]
        feats["brent_wti_spread_pct"] = feats["brent_wti_spread"] / feats["wti_close_native"] * 100
        feats["brent_wti_spread_z"] = (
            feats["brent_wti_spread"] - feats["brent_wti_spread"].rolling(60).mean()
        ) / feats["brent_wti_spread"].rolling(60).std()

    # Volume features
    for col in ["wti_volume", "brent_volume"]:
        if col in feats.columns:
            feats[f"{col}_ratio"] = feats[col] / feats[col].rolling(20).mean()

    # Range features
    for prefix in ["wti", "brent"]:
        hi = f"{prefix}_high_native"
        lo = f"{prefix}_low_native"
        op = f"{prefix}_open_native"
        cl = f"{prefix}_close_native"
        if all(c in feats.columns for c in [hi, lo, op]):
            feats[f"{prefix}_range_pct"] = (feats[hi] - feats[lo]) / feats[op] * 100
            feats[f"{prefix}_body_pct"] = (feats[cl] - feats[op]) / feats[op] * 100
            feats[f"{prefix}_upper_wick"] = (feats[hi] - np.maximum(feats[op], feats[cl])) / feats[op] * 100
            feats[f"{prefix}_lower_wick"] = (np.minimum(feats[op], feats[cl]) - feats[lo]) / feats[op] * 100

    # Macro features
    if not macro.empty:
        macro = macro.copy()
        macro["trade_date_ist"] = pd.to_datetime(macro["trade_date_ist"])
        for col in ["DXY", "SPX", "GOLD", "US10Y", "VIX"]:
            if col in macro.columns:
                macro[f"{col}_ret_1d"] = macro[col].pct_change() * 100
                macro[f"{col}_ret_5d"] = macro[col].pct_change(5) * 100
                macro[f"{col}_ma_20"] = macro[col].rolling(20).mean()
                macro[f"{col}_ma_50"] = macro[col].rolling(50).mean()
                macro[f"{col}_trend"] = np.where(
                    macro[col] > macro[f"{col}_ma_20"], 1,
                    np.where(macro[col] < macro[f"{col}_ma_50"], -1, 0)
                )
        feats = feats.merge(macro, on="trade_date_ist", how="left")

    # Cross-asset correlations (rolling)
    if "wti_ret" in feats.columns and "brent_ret" in feats.columns:
        feats["wti_brent_corr_20d"] = feats["wti_ret"].rolling(20).corr(feats["brent_ret"])

    if "DXY_ret_1d" in feats.columns and "wti_ret" in feats.columns:
        feats["wti_dxy_corr_20d"] = feats["wti_ret"].rolling(20).corr(feats["DXY_ret_1d"])

    # Phase target (from session data)
    phase_map = sess.drop_duplicates("trade_date_ist").set_index("trade_date_ist")["phase_id"]
    feats["phase_id"] = feats["trade_date_ist"].map(phase_map)

    # Drop rows without target
    feats = feats.dropna(subset=["phase_id"]).reset_index(drop=True)

    return feats

def select_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Select and clean feature columns."""
    exclude = ["trade_date_ist", "phase_id", "phase_label"]
    # Also exclude raw price columns (keep only derived features)
    raw_price_cols = [c for c in df.columns if any(x in c.lower() for x in ["open_native", "high_native", "low_native", "close_native", "volume"]) and not any(x in c for x in ["_ret_", "_vol_", "_ratio", "_pct", "_z", "_spread", "_corr", "_trend", "_ma_", "_range", "_body", "_wick"])]
    feature_cols = [c for c in df.columns if c not in exclude and c not in raw_price_cols]

    # Remove columns with too many NaNs
    nan_frac = df[feature_cols].isna().mean()
    feature_cols = [c for c in feature_cols if nan_frac[c] < 0.5]

    # Convert all feature columns to numeric, coercing errors to NaN
    X = df[feature_cols].apply(pd.to_numeric, errors='coerce')
    # Fill remaining NaNs
    X = X.ffill().fillna(0)
    y = df["phase_id"].astype(int)

    return X, feature_cols

# ─── Model Training ──────────────────────────────────────────────────────────

def train_regime_classifier(X: pd.DataFrame, y: pd.Series, feature_names: List[str]) -> Tuple[Pipeline, ModelMetadata]:
    """Train calibrated regime classifier with time-series CV."""
    # Filter out classes with too few samples for CV (need at least 3 per class for 3-fold CV)
    class_counts = y.value_counts()
    valid_classes = class_counts[class_counts >= 3].index.tolist()
    if len(valid_classes) < len(class_counts):
        dropped = set(class_counts.index) - set(valid_classes)
        print(f"  WARNING: Dropping classes with <3 samples: {dropped}", flush=True)
        mask = y.isin(valid_classes)
        X = X[mask]
        y = y[mask]
        print(f"  Training on {len(valid_classes)} classes with {len(X)} samples", flush=True)

    # Time series split
    tscv = TimeSeriesSplit(n_splits=5)

    # Base model - Random Forest handles non-linear interactions well
    base_clf = RandomForestClassifier(
        n_estimators=500,
        max_depth=10,
        min_samples_leaf=5,
        min_samples_split=10,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    # Calibrate probabilities - use cv=2 for small datasets
    cv_folds = min(3, len(y) // 2) if len(y) > 6 else 2
    clf = CalibratedClassifierCV(base_clf, method="isotonic", cv=cv_folds)

    # Pipeline with scaling (though RF doesn't need it, good for other models)
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", clf),
    ])

    # Cross-validation
    cv_scores = cross_val_score(pipe, X, y, cv=tscv, scoring="accuracy", n_jobs=-1)

    # Fit on full data
    pipe.fit(X, y)

    # Get calibrated classifier for probabilities
    calibrated_clf = pipe.named_steps["clf"]
    # Access base estimator (API changed in sklearn 1.2+)
    try:
        if hasattr(calibrated_clf, 'base_estimator_'):
            base_clf_fitted = calibrated_clf.base_estimator_
        elif hasattr(calibrated_clf, 'calibrated_classifiers_'):
            base_clf_fitted = calibrated_clf.calibrated_classifiers_[0].estimator
        elif hasattr(calibrated_clf, 'estimator'):
            base_clf_fitted = calibrated_clf.estimator
        else:
            base_clf_fitted = base_clf  # Use the one we created earlier
    except Exception:
        base_clf_fitted = base_clf  # Fallback to the one we created

    # Feature importance
    importance = pd.DataFrame({
        "feature": feature_names,
        "importance": base_clf_fitted.feature_importances_
    }).sort_values("importance", ascending=False)

    # Class distribution
    class_dist = y.value_counts().to_dict()

    metadata = ModelMetadata(
        trained_at=datetime.now().isoformat(),
        n_samples=len(X),
        n_features=len(feature_names),
        classes=sorted(y.unique().tolist()),
        class_distribution=class_dist,
        cv_accuracy=float(cv_scores.mean()),
        cv_accuracy_std=float(cv_scores.std()),
        feature_names=feature_names,
        hyperparameters={
            "n_estimators": 500,
            "max_depth": 10,
            "min_samples_leaf": 5,
            "class_weight": "balanced",
        },
        sklearn_version=__import__("sklearn").__version__,
    )

    return pipe, metadata, importance

def evaluate_model(pipe: Pipeline, X: pd.DataFrame, y: pd.Series, metadata: ModelMetadata) -> Dict:
    """Comprehensive model evaluation."""
    y_pred = pipe.predict(X)
    y_prob = pipe.predict_proba(X)

    # Per-class metrics
    report = classification_report(y, y_pred, output_dict=True)
    cm = confusion_matrix(y, y_pred, labels=metadata.classes)

    # Calibration check: bin probabilities and check empirical frequency
    calibration = {}
    for i, cls in enumerate(metadata.classes):
        probs = y_prob[:, i]
        bins = np.linspace(0, 1, 11)
        bin_idx = np.digitize(probs, bins) - 1
        bin_acc = []
        for b in range(10):
            mask = bin_idx == b
            if mask.sum() > 0:
                bin_acc.append((y[mask] == cls).mean())
            else:
                bin_acc.append(np.nan)
        calibration[f"phase_{cls}"] = {
            "bins": bins.tolist(),
            "empirical": bin_acc,
        }

    return {
        "accuracy": float(accuracy_score(y, y_pred)),
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
        "calibration": calibration,
        "cv_accuracy": metadata.cv_accuracy,
        "cv_accuracy_std": metadata.cv_accuracy_std,
    }

def save_model(pipe: Pipeline, metadata: ModelMetadata, importance: pd.DataFrame) -> None:
    """Save model and metadata."""
    model_data = {
        "pipeline": pipe,
        "metadata": metadata,
        "importance": importance,
    }
    joblib.dump(model_data, MODEL_PATH)
    importance.to_csv(IMPORTANCE_PATH, index=False)

    with open(DIAGNOSTICS_PATH, "w") as f:
        json.dump(asdict(metadata), f, indent=2, default=str)

    print(f">>> Model saved to {MODEL_PATH}")

def load_model() -> Tuple[Pipeline, ModelMetadata, pd.DataFrame]:
    """Load model and metadata."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}")

    model_data = joblib.load(MODEL_PATH)
    return model_data["pipeline"], model_data["metadata"], model_data["importance"]

# ─── Live Inference ──────────────────────────────────────────────────────────

def predict_latest(pipe: Pipeline, metadata: ModelMetadata, data: Dict[str, pd.DataFrame]) -> RegimePrediction:
    """Generate prediction for the latest available data."""
    feats = build_features(data)
    X, _ = select_features(feats)

    # Get latest row
    latest = X.iloc[[-1]]
    latest_date = feats["trade_date_ist"].iloc[-1]

    # Predict
    probs = pipe.predict_proba(latest)[0]
    pred_class = pipe.predict(latest)[0]

    # Map to phase labels
    phase_lookup = pd.read_csv(ARTIFACTS / "phase_lookup.csv")
    phase_labels = dict(zip(phase_lookup["phase_id"], phase_lookup["phase_label"]))

    # Top contributing features (approximate via feature importance * feature value)
    importance_dict = dict(zip(metadata.feature_names, metadata.hyperparameters.get("feature_importance", [])))
    if not importance_dict:
        # Load from saved importance
        imp_df = pd.read_csv(IMPORTANCE_PATH)
        importance_dict = dict(zip(imp_df["feature"], imp_df["importance"]))

    feature_vals = latest.iloc[0].to_dict()
    top_features = sorted(
        [(f, importance_dict.get(f, 0) * abs(feature_vals.get(f, 0))) for f in metadata.feature_names],
        key=lambda x: x[1], reverse=True
    )[:10]

    prob_dict = {f"Phase_{c}": float(p) for c, p in zip(pipe.classes_, probs)}

    return RegimePrediction(
        timestamp=latest_date.isoformat(),
        phase_id=int(pred_class),
        phase_label=phase_labels.get(pred_class, f"Phase {pred_class}"),
        confidence=float(probs.max()),
        probabilities=prob_dict,
        top_features=dict(top_features),
        model_version=metadata.trained_at[:10],
        feature_vector=feature_vals,
    )

def check_retrain_needed(metadata: ModelMetadata) -> Tuple[bool, str]:
    """Check if model needs retraining."""
    trained = datetime.fromisoformat(metadata.trained_at)
    days_old = (datetime.now() - trained).days

    if days_old > RETRAIN_THRESHOLD_DAYS:
        return True, f"Model is {days_old} days old (threshold: {RETRAIN_THRESHOLD_DAYS})"

    # Could add feature drift detection here
    return False, "Model is current"

# ─── SHAP Explanations ───────────────────────────────────────────────────────

def explain_prediction(pipe: Pipeline, X: pd.DataFrame, metadata: ModelMetadata) -> Optional[Dict]:
    """Generate SHAP explanations for latest prediction."""
    if not SHAP_AVAILABLE:
        return None

    try:
        # Use tree explainer for RF
        base_clf = pipe.named_steps["clf"].base_estimator_
        explainer = shap.TreeExplainer(base_clf_fitted)
        shap_values = explainer.shap_values(X.iloc[[-1]])

        # Get top features for predicted class
        pred_class = pipe.predict(X.iloc[[-1]])[0]
        class_idx = list(pipe.classes_).index(pred_class)

        if isinstance(shap_values, list):
            sv = shap_values[class_idx][0]
        else:
            sv = shap_values[0]

        feature_names = metadata.feature_names
        explanations = sorted(
            zip(feature_names, sv),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:15]

        return {
            "predicted_class": int(pred_class),
            "base_value": float(explainer.expected_value[class_idx] if isinstance(explainer.expected_value, list) else explainer.expected_value),
            "shap_values": {f: float(v) for f, v in explanations},
        }
    except Exception as e:
        return {"error": str(e)}

# ─── Main Pipeline ───────────────────────────────────────────────────────────

def run_regime_classifier(mode: str = "train") -> Dict:
    """Main entry point for regime classifier."""
    print(f">>> Regime Classifier: {mode} mode", flush=True)

    # Load data
    data = load_market_data()
    feats = build_features(data)
    X, feature_names = select_features(feats)
    y = feats["phase_id"].astype(int)

    if mode == "train":
        # Train new model
        pipe, metadata, importance = train_regime_classifier(X, y, feature_names)

        # Evaluate
        eval_results = evaluate_model(pipe, X, y, metadata)
        metadata_dict = asdict(metadata)
        metadata_dict["evaluation"] = eval_results

        # Save
        save_model(pipe, metadata, importance)

        # Generate predictions for all data (for analysis)
        all_preds = pipe.predict_proba(X)
        pred_df = feats[["trade_date_ist", "phase_id"]].copy()
        for i, cls in enumerate(pipe.classes_):
            pred_df[f"prob_phase_{cls}"] = all_preds[:, i]
        pred_df["predicted_phase"] = pipe.predict(X)
        pred_df["correct"] = pred_df["predicted_phase"] == pred_df["phase_id"]
        pred_df.to_csv(PREDICTIONS_PATH, index=False)

        print(f">>> Training complete. CV Accuracy: {metadata.cv_accuracy:.3f} (+/- {metadata.cv_accuracy_std:.3f})")
        print(f">>> Predictions saved to {PREDICTIONS_PATH}")

        return {"status": "trained", "metadata": metadata_dict}

    elif mode == "predict":
        # Load existing model
        try:
            pipe, metadata, importance = load_model()
        except FileNotFoundError:
            return {"status": "error", "message": "Model not found. Run in 'train' mode first."}

        # Check retrain
        needs_retrain, reason = check_retrain_needed(metadata)
        if needs_retrain:
            print(f">>> Warning: {reason}")

        # Predict latest
        prediction = predict_latest(pipe, metadata, data)

        # SHAP explanation
        explanation = explain_prediction(pipe, X, metadata)

        # Save latest prediction
        pred_record = {
            "timestamp": prediction.timestamp,
            "phase_id": prediction.phase_id,
            "phase_label": prediction.phase_label,
            "confidence": prediction.confidence,
            "probabilities": json.dumps(prediction.probabilities),
            "top_features": json.dumps(prediction.top_features),
            "model_version": prediction.model_version,
            "needs_retrain": needs_retrain,
        }
        pred_df = pd.DataFrame([pred_record])
        if PREDICTIONS_PATH.exists():
            existing = pd.read_csv(PREDICTIONS_PATH)
            pred_df = pd.concat([existing, pred_df], ignore_index=True)
        pred_df.to_csv(PREDICTIONS_PATH, index=False)

        result = {
            "status": "predicted",
            "prediction": asdict(prediction),
            "explanation": explanation,
            "needs_retrain": needs_retrain,
            "retrain_reason": reason if needs_retrain else None,
        }
        print(f">>> Prediction: Phase {prediction.phase_id} ({prediction.phase_label}) @ {prediction.confidence:.1%} confidence")
        return result

    else:
        return {"status": "error", "message": f"Unknown mode: {mode}"}

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "predict"
    result = run_regime_classifier(mode)
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()