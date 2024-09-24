import json
import os
import sys
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from sklearn.model_selection import train_test_split, TimeSeriesSplit, GridSearchCV, RandomizedSearchCV
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential, Model
from tensorflow.keras.layers import LSTM, Dense, Conv1D, MaxPooling1D, Flatten, Input, Dropout
from sklearn.svm import SVR
import warnings
warnings.filterwarnings('ignore')

INPUT_FOLDER_PATH = '/home/roberto/job/workload_logs/json/part1'
WORKLOAD_PREDICTOR_FOLDER_PATH = '/home/roberto/job/vm_allocator/cplex/workload_predictor'


# Check if the input folder exists
if not os.path.exists(INPUT_FOLDER_PATH):
    print(f"Error: Input folder '{INPUT_FOLDER_PATH}' does not exist.")
    sys.exit(1)

def preprocess_data(vms_path):
    # Load your JSON data
    with open(vms_path, 'r') as f:
        vms = json.load(f)

    start_time_str = 'Wed Jun 01 02:12:45 CEST 2016'
    start_time = datetime.strptime(start_time_str, '%a %b %d %H:%M:%S %Z %Y')

    for vm in vms:
        vm['start_time'] = start_time + timedelta(seconds=vm['submit_time'])
        vm['end_time'] = vm['start_time'] + timedelta(seconds=vm['requested_time'])

    for vm in vms:
        vm['workload'] = vm['requested_processors'] 

    # Create a DataFrame
    df = pd.DataFrame(vms)

    # Set the index to start_time
    df.set_index('start_time', inplace=True)
    
    # Resample the data hourly and sum the workloads
    workload_ts = df['workload'].resample('h').sum()

    workload_ts = workload_ts.to_frame()

    workload_ts['hour'] = workload_ts.index.hour
    workload_ts['day_of_week'] = workload_ts.index.dayofweek

    for lag in range(1, 25):  # Last 24 hours
        workload_ts[f'lag_{lag}'] = workload_ts['workload'].shift(lag)
    return workload_ts

def arima_model(workload_ts):
    import pmdarima as pm
    # Drop rows with NaN values
    workload_ts = workload_ts.dropna()

    # Features and target
    y = workload_ts['workload']

    # Split data
    y_train, y_test = train_test_split(y, test_size=0.2, shuffle=False)

    # Grid search
    best_aic = float("inf")
    best_params = None
    max_p, max_d, max_q = 3, 1, 3
    for p in range(max_p + 1):
        for d in range(max_d + 1):
            for q in range(max_q + 1):
                try:
                    model = pm.ARIMA(order=(p, d, q), seasonal_order=(1,1,1,24))
                    results = model.fit(y_train)
                    aic = results.aic()
                    if aic < best_aic:
                        best_aic = aic
                        best_params = (p, d, q)
                except:
                    continue

    # Print best parameters
    print("ARIMA - Best parameters (p, d, q):", best_params)

    # Fit the model with best parameters
    best_model = pm.ARIMA(order=best_params)
    best_results = best_model.fit(y_train)

    # Predict
    predictions = best_results.predict(n_periods=len(y_test))
    predictions_df = pd.DataFrame({'date': y_test.index, 'workload': predictions})
    actual_df = pd.DataFrame({'date': y_test.index, 'workload': y_test.values})

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True), best_params

def random_forest_model(workload_ts):
    # Drop rows with NaN values (due to lag features)
    workload_ts = workload_ts.dropna()

    # Features and target
    X = workload_ts.drop('workload', axis=1)
    y = workload_ts['workload']

    # TimeSeriesSplit for cross-validation
    tscv = TimeSeriesSplit(n_splits=5)

    # Parameter grid
    param_grid = {
        'n_estimators': [50, 100, 400],
        'max_depth': [4, 6, 8, 10],
        'min_samples_split': [2, 6, 10],
        'min_samples_leaf': [2, 4],
        'max_features': ['sqrt'],
        'bootstrap': [True, False]
    }

    # Initialize model
    model = RandomForestRegressor()

    # GridSearchCV
    grid_search = GridSearchCV(model, param_grid, cv=tscv, scoring='neg_mean_absolute_error', n_jobs=-1)
    grid_search.fit(X, y)

    # Print best parameters
    print("Random Forest - Best parameters:", grid_search.best_params_)

    # Best estimator
    best_model = grid_search.best_estimator_

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    # Train model
    best_model.fit(X_train, y_train)

    # Predict
    predictions = best_model.predict(X_test)
    predictions_df = pd.DataFrame({'date': X_test.index, 'workload': predictions})
    actual_df = pd.DataFrame({'date': y_test.index, 'workload': y_test.values})

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True), grid_search.best_params_

def xgboost_model(workload_ts):
    # Drop rows with NaN values (due to lag features)
    workload_ts = workload_ts.dropna()

    # Features and target
    X = workload_ts.drop('workload', axis=1)
    y = workload_ts['workload']

    # TimeSeriesSplit for cross-validation
    tscv = TimeSeriesSplit(n_splits=5)

    # Parameter grid
    param_grid = {
        'n_estimators': [400, 500, 600],
        'max_depth': [4, 5, 6],
        'learning_rate': [0.001, 0.01],
        'subsample': [0.7,0.8, 0.9],
        'colsample_bytree': [0.7, 0.8, 0.9]
    }

    # Initialize model
    model = xgb.XGBRegressor(objective='reg:squarederror')

    # GridSearchCV
    grid_search = GridSearchCV(model, param_grid, cv=tscv, scoring='neg_mean_absolute_error', n_jobs=-1)
    grid_search.fit(X, y)

    # Print best parameters
    print("XGBoost - Best parameters:", grid_search.best_params_)

    # Best estimator
    best_model = grid_search.best_estimator_

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    # Train model
    best_model.fit(X_train, y_train)

    # Predict
    predictions = best_model.predict(X_test)
    predictions_df = pd.DataFrame({'date': X_test.index, 'workload': predictions})
    actual_df = pd.DataFrame({'date': y_test.index, 'workload': y_test.values})

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True), grid_search.best_params_

def lightgbm_model(workload_ts):
    # Drop rows with NaN values (due to lag features)
    workload_ts = workload_ts.dropna()

    # Features and target
    X = workload_ts.drop('workload', axis=1)
    y = workload_ts['workload']

    # TimeSeriesSplit for cross-validation
    tscv = TimeSeriesSplit(n_splits=5)

    # Parameter grid
    param_grid = {
        'n_estimators': [100, 500],
        'learning_rate': [0.01, 0.1],
        'num_leaves': [31, 50],
        'max_depth': [5, 10, -1],
        'min_child_samples': [20, 50],
        'subsample': [0.8, 1],
        'colsample_bytree': [0.8, 1]
    }

    # Initialize model
    model = lgb.LGBMRegressor()

    # GridSearchCV
    grid_search = GridSearchCV(model, param_grid, cv=tscv, scoring='neg_mean_absolute_error', n_jobs=-1)
    grid_search.fit(X, y)

    # Print best parameters
    print("LightGBM - Best parameters:", grid_search.best_params_)

    # Best estimator
    best_model = grid_search.best_estimator_

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    # Train model
    best_model.fit(X_train, y_train)

    # Predict
    predictions = best_model.predict(X_test)
    predictions_df = pd.DataFrame({'date': X_test.index, 'workload': predictions})
    actual_df = pd.DataFrame({'date': y_test.index, 'workload': y_test.values})

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True), grid_search.best_params_

def lstm_model(workload_ts):
    from sklearn.model_selection import ParameterGrid

    # Prepare data
    workload_ts = workload_ts.dropna()

    # Scale data
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(workload_ts[['workload']])

    # Create sequences
    def create_sequences(data, seq_length, dates):
        X = []
        y = []
        seq_dates = []
        for i in range(len(data) - seq_length):
            X.append(data[i:i + seq_length])
            y.append(data[i + seq_length])
            seq_dates.append(dates[i + seq_length])
        return np.array(X), np.array(y), seq_dates

    seq_length = 24
    X, y, dates = create_sequences(scaled_data, seq_length, workload_ts.index)

    # Split data
    split_index = int(len(X) * 0.8)
    X_train, X_test = X[:split_index], X[split_index:]
    y_train, y_test = y[:split_index], y[split_index:]
    dates_train, dates_test = dates[:split_index], dates[split_index:]

    # Hyperparameter tuning
    param_grid = {
        'units': [50, 100],
        'dropout': [0.0, 0.2],
        'batch_size': [16, 32],
        'epochs': [20, 50]
    }

    best_mae = float('inf')
    best_params = None
    best_model = None

    for params in ParameterGrid(param_grid):
        model = Sequential()
        model.add(LSTM(params['units'], activation='relu', input_shape=(seq_length, 1)))
        if params['dropout'] > 0.0:
            model.add(Dropout(params['dropout']))
        model.add(Dense(1))
        model.compile(optimizer='adam', loss='mse')
        model.fit(X_train, y_train, epochs=params['epochs'], batch_size=params['batch_size'], verbose=0)
        predictions = model.predict(X_test)
        predictions_inv = scaler.inverse_transform(predictions)
        y_test_inv = scaler.inverse_transform(y_test)
        mae = mean_absolute_error(y_test_inv, predictions_inv)
        if mae < best_mae:
            best_mae = mae
            best_params = params
            best_model = model

    # Print best parameters
    print("LSTM - Best parameters:", best_params)

    # Predict with best model
    predictions = best_model.predict(X_test)
    predictions_inv = scaler.inverse_transform(predictions)
    y_test_inv = scaler.inverse_transform(y_test)

    # Create DataFrames with date
    predictions_df = pd.DataFrame({'date': dates_test, 'workload': predictions_inv.flatten()})
    actual_df = pd.DataFrame({'date': dates_test, 'workload': y_test_inv.flatten()})

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True), best_params

def svm_model(workload_ts):
    # Drop rows with NaN values
    workload_ts = workload_ts.dropna()

    # Features and target
    X = workload_ts.drop('workload', axis=1)
    y = workload_ts['workload']

    # Scale features
    scaler_X = MinMaxScaler()
    scaler_y = MinMaxScaler()
    X_scaled = scaler_X.fit_transform(X)
    y_scaled = scaler_y.fit_transform(y.values.reshape(-1,1)).flatten()

    # TimeSeriesSplit for cross-validation
    tscv = TimeSeriesSplit(n_splits=5)

    # Parameter grid
    param_grid = {
        'C': [0.1, 1, 10],
        'epsilon': [0.01, 0.1, 1],
        'kernel': ['rbf']
    }

    # Initialize model
    model = SVR()

    # GridSearchCV
    grid_search = GridSearchCV(model, param_grid, cv=tscv, scoring='neg_mean_absolute_error', n_jobs=-1)
    grid_search.fit(X_scaled, y_scaled)

    # Print best parameters
    print("SVM - Best parameters:", grid_search.best_params_)

    # Best estimator
    best_model = grid_search.best_estimator_

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y_scaled, test_size=0.2, shuffle=False)

    # Keep track of dates
    dates_train = y.index[:len(y_train)]
    dates_test = y.index[len(y_train):]

    # Predict
    predictions = best_model.predict(X_test)
    predictions_inv = scaler_y.inverse_transform(predictions.reshape(-1,1)).flatten()
    y_test_inv = scaler_y.inverse_transform(y_test.reshape(-1,1)).flatten()

    # Create DataFrames with date
    predictions_df = pd.DataFrame({'date': dates_test, 'workload': predictions_inv})
    actual_df = pd.DataFrame({'date': dates_test, 'workload': y_test_inv})

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True), grid_search.best_params_

def cnn_model(workload_ts):
    from sklearn.model_selection import ParameterGrid

    # Prepare data
    workload_ts = workload_ts.dropna()

    # Scale data
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(workload_ts[['workload']])

    # Create sequences
    def create_sequences(data, seq_length, dates):
        X = []
        y = []
        seq_dates = []
        for i in range(len(data) - seq_length):
            X.append(data[i:i + seq_length])
            y.append(data[i + seq_length])
            seq_dates.append(dates[i + seq_length])
        return np.array(X), np.array(y), seq_dates

    seq_length = 24
    X, y, dates = create_sequences(scaled_data, seq_length, workload_ts.index)

    # Reshape for CNN input
    X = X.reshape((X.shape[0], X.shape[1], 1))

    # Split data
    split_index = int(len(X) * 0.8)
    X_train, X_test = X[:split_index], X[split_index:]
    y_train, y_test = y[:split_index], y[split_index:]
    dates_train, dates_test = dates[:split_index], dates[split_index:]

    # Hyperparameter tuning
    param_grid = {
        'filters': [32, 64],
        'kernel_size': [2, 4],
        'dropout': [0.0, 0.2],
        'batch_size': [16, 32],
        'epochs': [20, 50]
    }

    best_mae = float('inf')
    best_params = None
    best_model = None

    for params in ParameterGrid(param_grid):
        model = Sequential()
        model.add(Conv1D(filters=params['filters'], kernel_size=params['kernel_size'],
                         activation='relu', input_shape=(seq_length, 1)))
        model.add(MaxPooling1D(pool_size=2))
        if params['dropout'] > 0.0:
            model.add(Dropout(params['dropout']))
        model.add(Flatten())
        model.add(Dense(50, activation='relu'))
        model.add(Dense(1))
        model.compile(optimizer='adam', loss='mse')
        model.fit(X_train, y_train, epochs=params['epochs'], batch_size=params['batch_size'], verbose=0)
        predictions = model.predict(X_test)
        predictions_inv = scaler.inverse_transform(predictions)
        y_test_inv = scaler.inverse_transform(y_test)
        mae = mean_absolute_error(y_test_inv, predictions_inv)
        if mae < best_mae:
            best_mae = mae
            best_params = params
            best_model = model

    # Print best parameters
    print("CNN - Best parameters:", best_params)

    # Predict with best model
    predictions = best_model.predict(X_test)
    predictions_inv = scaler.inverse_transform(predictions)
    y_test_inv = scaler.inverse_transform(y_test)

    # Create DataFrames with date
    predictions_df = pd.DataFrame({'date': dates_test, 'workload': predictions_inv.flatten()})
    actual_df = pd.DataFrame({'date': dates_test, 'workload': y_test_inv.flatten()})

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True), best_params

def evaluate_model(predictions_df, actual_df, model_name):
    mae = mean_absolute_error(actual_df['workload'], predictions_df['workload'])
    mse = mean_squared_error(actual_df['workload'], predictions_df['workload'])
    r2 = r2_score(actual_df['workload'], predictions_df['workload'])
    print(f"{model_name} - MAE: {mae}, MSE: {mse}, R2: {r2}")

    # # Plotting
    # plt.figure(figsize=(15,5))
    # plt.plot(actual_df['date'], actual_df['workload'], label='Actual Workload')
    # plt.plot(predictions_df['date'], predictions_df['workload'], label=f'Predicted Workload ({model_name})')
    # plt.title(f'{model_name} Predictions vs Actual')
    # plt.legend()
    # plt.show()

def save_best_parameters(best_params, output_folder_path):
    with open(os.path.join(output_folder_path, 'best_parameters.json'), 'w') as f:
        json.dump(best_params, f, indent=4)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process some JSON files.')
    parser.add_argument('workload_name', type=str, help='The name of the workload to process.')
    args = parser.parse_args()
    workload_name = args.workload_name
    input_file = os.path.join(INPUT_FOLDER_PATH, f'{workload_name}.json')
    output_folder_path = os.path.join(WORKLOAD_PREDICTOR_FOLDER_PATH, workload_name)
    os.makedirs(output_folder_path, exist_ok=True)
    
    # Preprocess data
    workload_ts = preprocess_data(input_file)

    # Dictionary to store best parameters
    best_parameters = {}

    # Run models and store best parameters
    # predictions_arima, actual_arima, best_params_arima = arima_model(workload_ts)
    # best_parameters['ARIMA'] = best_params_arima

    predictions_rf, y_test_rf, best_params_rf = random_forest_model(workload_ts)
    best_parameters['Random Forest'] = best_params_rf

    predictions_xgb, y_test_xgb, best_params_xgb = xgboost_model(workload_ts)
    best_parameters['XGBoost'] = best_params_xgb

    predictions_lgbm, y_test_lgbm, best_params_lgbm = lightgbm_model(workload_ts)
    best_parameters['LightGBM'] = best_params_lgbm

    predictions_lstm, y_test_lstm, best_params_lstm = lstm_model(workload_ts)
    best_parameters['LSTM'] = best_params_lstm

    predictions_svm, y_test_svm, best_params_svm = svm_model(workload_ts)
    best_parameters['SVM'] = best_params_svm

    predictions_cnn, y_test_cnn, best_params_cnn = cnn_model(workload_ts)
    best_parameters['CNN'] = best_params_cnn

    # Save best parameters
    save_best_parameters(best_parameters, output_folder_path)

    # Evaluate Models
    # evaluate_model(predictions_arima, actual_arima, 'SARIMA')
    evaluate_model(predictions_rf, y_test_rf, 'Random Forest')
    evaluate_model(predictions_xgb, y_test_xgb, 'XGBoost')
    evaluate_model(predictions_lgbm, y_test_lgbm, 'LightGBM')
    evaluate_model(predictions_lstm, y_test_lstm, 'LSTM')
    evaluate_model(predictions_svm, y_test_svm, 'SVM')
    evaluate_model(predictions_cnn, y_test_cnn, 'CNN')
