import pandas as pd
import numpy as np
from sklearn.linear_model import RidgeCV, LassoCV
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score

class SumOfProcessRegressions:
    def __init__(self, features, model='ridge'):
        self.features = features
        self.model_type = model
        self.scaler = StandardScaler()
        self.model = RidgeCV(alphas=[0.1, 1.0, 10.0]) if model == 'ridge' else LassoCV(cv=5)

    def fit(self, df):
        # Grouped total energy per interval
        y_interval = df.groupby('_time')["interval_energy"].first()

        # Sum of per-process features per interval
        X_interval = df.groupby('_time')[self.features].sum()

        X_scaled = self.scaler.fit_transform(X_interval)
        self.model.fit(X_scaled, y_interval)

    def predict(self, df):
        # Predict per-process energy
        X_proc = df[self.features].fillna(0)
        X_scaled = self.scaler.transform(X_proc)
        df = df.copy()
        df["predicted_process_energy"] = self.model.predict(X_scaled)
        return df

    def predict_interval_energy(self, df):
        df_pred = self.predict(df)
        return df_pred.groupby("_time")["predicted_process_energy"].sum()
