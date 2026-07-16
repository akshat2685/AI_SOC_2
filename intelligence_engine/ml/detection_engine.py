import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer

class AutonomousDetectionEngine:
    def __init__(self, max_window_size: int = 10000):
        # Define numerical and categorical features for the pipeline
        self.numeric_features = ['bytes_in', 'bytes_out', 'duration', 'packet_count']
        self.categorical_features = ['protocol', 'action']
        
        # Sliding window for incremental retraining
        self.max_window_size = max_window_size
        self.history_window = pd.DataFrame()
        
        # Create preprocessors
        numeric_transformer = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler())
        ])
        categorical_transformer = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
            ('onehot', OneHotEncoder(handle_unknown='ignore'))
        ])
        
        self.preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, self.numeric_features),
                ('cat', categorical_transformer, self.categorical_features)
            ])
            
        # Initialize ML models
        self.anomaly_detector = Pipeline(steps=[
            ('preprocessor', self.preprocessor),
            ('model', IsolationForest(n_estimators=100, contamination=0.05, random_state=42))
        ])
        
        self.behavior_classifier = Pipeline(steps=[
            ('preprocessor', self.preprocessor),
            ('model', RandomForestClassifier(n_estimators=100, random_state=42))
        ])
        
        self.is_anomaly_detector_fitted = False
        self.is_classifier_fitted = False

    def extract_features(self, events: list[dict]) -> pd.DataFrame:
        """ Extract features from raw telemetry. Process JSON into a DataFrame. """
        if not events:
            return pd.DataFrame()
            
        df = pd.DataFrame(events)
        
        # Ensure expected columns exist, fill with defaults if missing
        expected_cols = {
            'bytes_in': 0.0,
            'bytes_out': 0.0,
            'duration': 0.0,
            'packet_count': 0,
            'protocol': 'unknown',
            'action': 'unknown'
        }
        
        for col, default_val in expected_cols.items():
            if col not in df.columns:
                df[col] = default_val
                
        return df

    def train_anomaly_detector(self, df: pd.DataFrame):
        """ Train the unsupervised Isolation Forest model using a sliding window. """
        if df.empty:
            raise ValueError("Empty DataFrame provided for training.")
            
        # Implement sliding window to avoid single-event training bias
        self.history_window = pd.concat([self.history_window, df], ignore_index=True)
        if len(self.history_window) > self.max_window_size:
            self.history_window = self.history_window.tail(self.max_window_size)
            
        self.anomaly_detector.fit(self.history_window)
        self.is_anomaly_detector_fitted = True
        
    def detect_anomalies(self, df: pd.DataFrame) -> np.ndarray:
        """ Returns anomaly scores. -1 for outliers (anomalies), 1 for inliers. """
        if not self.is_anomaly_detector_fitted:
            # Fit on the fly if not fitted
            self.train_anomaly_detector(df)
        return self.anomaly_detector.predict(df)
        
    def train_behavior_classifier(self, df: pd.DataFrame, y: np.ndarray):
        """ Train the supervised Random Forest model. """
        if df.empty:
            raise ValueError("Empty DataFrame provided for training.")
        self.behavior_classifier.fit(df, y)
        self.is_classifier_fitted = True
        
    def classify_behavior(self, df: pd.DataFrame) -> np.ndarray:
        """ Returns classification labels. """
        if not self.is_classifier_fitted:
            raise RuntimeError("Behavior classifier is not fitted yet.")
        return self.behavior_classifier.predict(df)

    def hunt_threats(self, df: pd.DataFrame, historical_context: list[dict] = None) -> list[dict]:
        """ 
        Threat Hunting Agent logic to query past behaviors and correlate with Threat Intel.
        Identifies specific anomalies and returns them as a list of threat records.
        """
        if df.empty:
            return []
            
        anomalies = self.detect_anomalies(df)
        
        # Vectorize processing of anomalies instead of iterating row by row
        anomaly_mask = anomalies == -1
        anomaly_indices = np.where(anomaly_mask)[0]
        
        if len(anomaly_indices) == 0:
            return []
            
        anomaly_df = df.iloc[anomaly_indices].copy()
        
        threats_df = pd.DataFrame({
            'index': anomaly_indices,
            'event_data': anomaly_df.to_dict('records'),
            'threat_level': 'HIGH',
            'reason': 'IsolationForest Anomaly'
        })
        
        return threats_df.to_dict('records')
