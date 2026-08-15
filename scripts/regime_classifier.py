"""regime_classifier.py — Live regime classifier framework.

Given current market data + optional news, outputs current phase_id with confidence.
Designed for live trading use: takes today's data, outputs phase classification.

Approach:
1. Feature engineering from recent price action (returns, vol, spreads, macro)
2. Supervised classification using historical phase labels as training data
3. Outputs: phase_id, confidence, key features, recommended playbook signals

Outputs:
- regime_model.pkl (trained classifier)
- regime_classifier.py (live inference script)
- regime_diagnostics.csv (out-of-sample performance)
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
import joblib

BASE = Path("/mnt/d/My Docs/Investing/Crude Analysis Agentic")
ARTIFACTS = BASE / "artifacts"
MODELS = BASE / "models"
MODELS.mkdir(exist_ok=True)


def build_features(primitives: pd.DataFrame, macro: pd.DataFrame = None) -> pd.DataFrame:
    """Build feature matrix for regime classification.

    Features per day:
    - Recent returns (1d, 5d, 20d) for WTI, Brent
    - Realized vol (5d, 20d)
    - Brent-WTI spread
    - DXY, SPX, GOLD, US10Y, VIX levels and trends
    - Session window return statistics (recent)
    - Day-type archetype (if available)
    """
    # Use session-level data for daily features
    sess = primitives[primitives["__stream"].isin(["WTI_session", "BRENT_session"])].copy()
    sess["trade_date_ist"] = pd.to_datetime(sess["trade_date_ist"]).dt.normalize()

    # Daily aggregation: use us_open window as proxy for daily return
    us_open = sess[sess["session_window_ist"] == "us_open"].copy()
    if us_open.empty:
        # fallback to any available window
        us_open = sess.groupby("trade_date_ist").first().reset_index()

    # Pivot to get WTI and Brent daily returns
    daily = us_open.pivot_table(
        index="trade_date_ist",
        columns="__stream",
        values="window_return_pct",
        aggfunc="first"
    ).reset_index()

    daily.columns = ["trade_date_ist", "brent_ret", "wti_ret"]
    daily["trade_date_ist"] = pd.to_datetime(daily["trade_date_ist"])

    # Features
    daily["brent_wti_spread"] = daily["brent_ret"] - daily["wti_ret"]
    daily["brent_wti_cum_spread"] = (daily["brent_ret"] - daily["wti_ret"]).rolling(20).sum()

    # Rolling returns
    for w in [1, 5, 20]:
        daily[f"brent_ret_{w}d"] = daily["brent_ret"].rolling(w).sum()
        daily[f"wti_ret_{w}d"] = daily["wti_ret"].rolling(w).sum()

    # Realized vol
    for w in [5, 20]:
        daily[f"brent_vol_{w}d"] = daily["brent_ret"].rolling(w).std() * np.sqrt(w)
        daily[f"wti_vol_{w}d"] = daily["wti_ret"].rolling(w).std() * np.sqrt(w)

    # Correlation
    daily["brent_wti_corr_20d"] = daily["brent_ret"].rolling(20).corr(daily["wti_ret"])

    # Macro features (if available)
    # TODO: merge macro data here

    # Target: phase_id from phase_lookup.csv
    phase = pd.read_csv("artifacts/phase_lookup.csv")
    phase["start_dt"] = pd.to_datetime(phase["start_datetime_ist"])
    phase["end_dt"] = pd.to_datetime(phase["end_datetime_ist"])

    def get_phase(dt):
        for _, p in phase.iterrows():
            if p["start_dt"] <= dt <= p["end_dt"]:
                return p["phase_id"]
        return np.nan

    daily["phase_id"] = daily["trade_date_ist"].apply(get_phase)

    # Drop rows without phase
    daily = daily.dropna(subset=["phase_id"]).reset_index(drop=True)

    return daily


def train_classifier(features_df: pd.DataFrame):
    """Train regime classifier."""
    # Feature columns (exclude target and date)
    exclude = ["trade_date_ist", "phase_id", "brent_ret", "wti_ret"]
    feature_cols = [c for c in features_df.columns if c not in exclude and not features_df[c].isna().all()]

    X = features_df[feature_cols].ffill().fillna(0)
    y = features_df["phase_id"].astype(int)

    # Time series split
    tscv = TimeSeriesSplit(n_splits=5)

    # Random Forest classifier
    clf = RandomForestClassifier(
        n_estimators=500,
        max_depth=8,
        min_samples_leaf=5,
        min_samples_split=10,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    # Cross-validation
    cv_scores = cross_val_score(clf, X, y, cv=tscv, scoring="accuracy")
    print(f"CV Accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std()*2:.3f})", flush=True)

    # Fit on full data
    clf.fit(X, y)

    # Feature importance
    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": clf.feature_importances_
    }).sort_values("importance", ascending=False)

    print("\nTop 20 features:")
    print(importance.head(20).to_string(index=False), flush=True)

    # Train/test split for final evaluation
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred), flush=True)

    print("\nConfusion Matrix:")
    cm = confusion_matrix(y_test, y_pred, labels=sorted(y.unique()))
    classes = sorted(y.unique())
    print(pd.DataFrame(cm, index=[f"P{i}" for i in classes], columns=[f"P{i}" for i in classes]).to_string(), flush=True)

    return clf, feature_cols, importance


def save_model(clf, feature_cols, importance, path: Path):
    """Save trained model and metadata."""
    model_data = {
        "classifier": clf,
        "feature_cols": feature_cols,
        "importance": importance.to_dict(orient="records"),
        "n_features": len(feature_cols),
        "n_classes": 6,
    }
    joblib.dump(model_data, path)
    print(f">>> Model saved to {path}", flush=True)


def predict_regime(clf, feature_cols, latest_features: pd.DataFrame):
    """Predict regime for latest data point."""
    X = latest_features[feature_cols].ffill().fillna(0)
    prob = clf.predict_proba(X)
    pred = clf.predict(X)

    # Get all classes from classifier
    all_classes = clf.classes_
    result = {
        "phase_id": int(pred[0]),
        "confidence": float(prob[0].max()),
        "probabilities": {f"Phase {int(c)}": float(prob[0][j]) for j, c in enumerate(all_classes)},
    }
    return result


def main():
    print(">>> regime_classifier.py starting", flush=True)

    # Load primitives
    primitives = pd.read_parquet("artifacts/primitives.parquet")

    # Build features
    print("Building features...", flush=True)
    features = build_features(primitives)
    print(f"Features shape: {features.shape}", flush=True)
    print(f"Phases present: {features['phase_id'].value_counts().sort_index().to_dict()}", flush=True)

    # Train
    clf, feature_cols, importance = train_classifier(features)

    # Save model
    save_model(clf, feature_cols, importance, Path("models/regime_classifier.pkl"))

    # Save importance
    importance.to_csv("artifacts/regime_feature_importance.csv", index=False)

    # Save features for inspection
    features.to_csv("artifacts/regime_features.csv", index=False)

    # Predict on latest data
    latest = features.tail(1)
    pred = predict_regime(clf, feature_cols, latest)
    print(f"\nLatest prediction: {pred}", flush=True)

    # Save diagnostics
    diagnostics = {
        "n_samples": len(features),
        "feature_cols": feature_cols,
        "class_distribution": features["phase_id"].value_counts().to_dict(),
    }
    import json
    with open("artifacts/regime_diagnostics.json", "w") as f:
        json.dump(diagnostics, f, indent=2, default=str)

    print("\n>>> regime_classifier.py complete", flush=True)


if __name__ == "__main__":
    main()