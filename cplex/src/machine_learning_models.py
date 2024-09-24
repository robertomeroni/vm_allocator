import os
import json
from utils import get_start_time
from datetime import datetime, timedelta
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
import joblib
import argparse
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score # type: ignore
import pmdarima as pm # type: ignore
from sklearn.ensemble import RandomForestRegressor # type: ignore
import xgboost as xgb # type: ignore
import lightgbm as lgb # type: ignore
from sklearn.svm import SVR # type: ignore
from tensorflow.keras.models import Sequential # type: ignore
from tensorflow.keras.layers import LSTM, Dense, Conv1D, MaxPooling1D, Flatten, Dropout # type: ignore
from sklearn.preprocessing import MinMaxScaler # type: ignore
from sklearn.multioutput import MultiOutputRegressor
import config

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--workload', help='Name of the workload')
args = parser.parse_args()


# Take workload_name as an input if --workload is provided
if args.workload:
    WORKLOAD_NAME = args.workload
    print(f"Predicting workload: {WORKLOAD_NAME}")
else:
    WORKLOAD_NAME = config.WORKLOAD_NAME

VM_TRACE_PATH_TRAIN = os.path.join('/home/roberto/job/workload_logs/json/part1', f'{WORKLOAD_NAME}.json')
VM_TRACE_PATH_TEST = os.path.join('/home/roberto/job/workload_logs/json/part2', f'{WORKLOAD_NAME}.json')
WORKLOAD_PREDICTOR_FOLDER_PATH = f'workload_predictor/{WORKLOAD_NAME}/'
MODELS_FOLDER_PATH = os.path.join(WORKLOAD_PREDICTOR_FOLDER_PATH, 'models/')
PLOTS_FOLDER_PATH = os.path.join(WORKLOAD_PREDICTOR_FOLDER_PATH, 'plots/')


def load_best_params(folder_path):
    with open(os.path.join(folder_path, 'best_parameters.json'), 'r') as f:
        best_params = json.load(f)
    return best_params

def preprocess_data(vms_path):
    # Load your JSON data
    with open(vms_path, 'r') as f:
        vms = json.load(f)

    start_time_str = get_start_time(WORKLOAD_NAME)
    start_time = datetime.strptime(start_time_str, '%a %b %d %H:%M:%S %Z %Y')

    for vm in vms:
        vm['start_time'] = start_time + timedelta(seconds=vm['submit_time'])
        vm['workload_cpu'] = vm['requested_processors']
        vm['workload_memory'] = vm['requested_memory']
        
    # Create a DataFrame
    df = pd.DataFrame(vms)

    # Set the index to start_time
    df.set_index('start_time', inplace=True)

    workload_ts = df[['workload_cpu', 'workload_memory']].resample('h').sum()

    workload_ts['hour'] = workload_ts.index.hour
    workload_ts['day_of_week'] = workload_ts.index.dayofweek

    # Drop rows with NaN values
    workload_ts = workload_ts.dropna()

    # Features and target
    X = workload_ts.drop(['workload_cpu', 'workload_memory'], axis=1)
    y = workload_ts[['workload_cpu', 'workload_memory']]

    return X, y


def arima_model(y_train, y_test):
    # Fit separate ARIMA models for CPU and Memory
    cpu_train = y_train['workload_cpu']
    cpu_test = y_test['workload_cpu']
    memory_train = y_train['workload_memory']
    memory_test = y_test['workload_memory']

    # Fit ARIMA model on cpu_train
    cpu_model = pm.ARIMA(order=(3,0,3), seasonal_order=(1,1,1,24))
    cpu_results = cpu_model.fit(cpu_train)

    # Fit ARIMA model on memory_train
    memory_model = pm.ARIMA(order=(3,0,3), seasonal_order=(1,1,1,24))
    memory_results = memory_model.fit(memory_train)

    # Ensure the directory exists
    cpu_output_path = os.path.join(WORKLOAD_PREDICTOR_FOLDER_PATH, 'arima_cpu.pkl')
    memory_output_path = os.path.join(WORKLOAD_PREDICTOR_FOLDER_PATH, 'arima_memory.pkl')
    os.makedirs(os.path.dirname(cpu_output_path), exist_ok=True)

    # Save the models
    joblib.dump(cpu_model, cpu_output_path)
    joblib.dump(memory_model, memory_output_path)
    print(f"Models saved to {cpu_output_path} and {memory_output_path}")

    # Predict
    cpu_predictions = cpu_results.predict(start=cpu_test.index[0], end=cpu_test.index[-1])
    memory_predictions = memory_results.predict(start=memory_test.index[0], end=memory_test.index[-1])

    # Create DataFrames with date
    predictions_df = pd.DataFrame({
        'start_time': cpu_predictions.index,
        'workload_cpu': cpu_predictions.values,
        'workload_memory': memory_predictions.values
    })
    actual_df = pd.DataFrame({
        'start_time': cpu_test.index,
        'workload_cpu': cpu_test.values,
        'workload_memory': memory_test.values
    })

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True)

def random_forest_model(X_train, y_train, X_test, y_test, best_params):
    model_name = 'Random Forest'
    if model_name in best_params:
        params = best_params[model_name]
    else:
        params = {'max_depth':5, 'max_features':'sqrt', 'min_samples_leaf':3, 'min_samples_split':4, 'n_estimators':100}

    model = RandomForestRegressor(**params)
    model.fit(X_train, y_train)
    
    output_path = os.path.join(MODELS_FOLDER_PATH, 'random_forest.pkl')

    # Save the model
    joblib.dump(model, output_path)
    print(f"Model saved to {output_path}")

    # Predict
    predictions = model.predict(X_test)
    predictions_df = pd.DataFrame(predictions, columns=['workload_cpu', 'workload_memory'], index=X_test.index)
    actual_df = pd.DataFrame(y_test, columns=['workload_cpu', 'workload_memory'], index=y_test.index)

    return predictions_df.reset_index(), actual_df.reset_index()

def xgboost_model(X_train, y_train, X_test, y_test, best_params):
    model_name = 'XGBoost'
    if model_name in best_params:
        params = best_params[model_name]
    else:
        params = {'colsample_bytree':0.8, 'learning_rate':0.01, 'max_depth':5, 'n_estimators':400, 'subsample':0.7}

    # Ensure 'objective' is included
    params['objective'] = 'reg:squarederror'

    base_model = xgb.XGBRegressor(**params)
    model = MultiOutputRegressor(base_model)
    model.fit(X_train, y_train)

    output_path = os.path.join(MODELS_FOLDER_PATH, 'xgboost.pkl')

    # Save the model
    joblib.dump(model, output_path)
    print(f"Model saved to {output_path}")

    # Predict
    predictions = model.predict(X_test)
    predictions_df = pd.DataFrame(predictions, columns=['workload_cpu', 'workload_memory'], index=X_test.index)
    actual_df = pd.DataFrame(y_test, columns=['workload_cpu', 'workload_memory'], index=y_test.index)

    return predictions_df.reset_index(), actual_df.reset_index()

def lightgbm_model(X_train, y_train, X_test, y_test, best_params):
    model_name = 'LightGBM'
    if model_name in best_params:
        params = best_params[model_name]
    else:
        params = {'colsample_bytree':0.8, 'learning_rate':0.01, 'max_depth':10, 'min_child_samples':50, 'n_estimators':500, 'num_leaves':50, 'subsample':0.8}

    base_model = lgb.LGBMRegressor(**params)
    model = MultiOutputRegressor(base_model)
    model.fit(X_train, y_train)

    output_path = os.path.join(MODELS_FOLDER_PATH, 'lightgbm.pkl')

    # Save the model
    joblib.dump(model, output_path)
    print(f"Model saved to {output_path}")

    # Predict
    predictions = model.predict(X_test)
    predictions_df = pd.DataFrame(predictions, columns=['workload_cpu', 'workload_memory'], index=X_test.index)
    actual_df = pd.DataFrame(y_test, columns=['workload_cpu', 'workload_memory'], index=y_test.index)

    return predictions_df.reset_index(), actual_df.reset_index()

def lstm_model(y_train, y_test, best_params):
    model_name = 'LSTM'
    if model_name in best_params:
        params = best_params[model_name]
    else:
        params = {'units':100, 'dropout':0.2, 'epochs':20, 'batch_size':16}
    units = params.get('units', 100)
    dropout = params.get('dropout', 0.2)
    epochs = params.get('epochs', 20)
    batch_size = params.get('batch_size', 16)

    # Combine y_train and y_test to form the complete series
    y_all = pd.concat([y_train, y_test])

    # Prepare data
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(y_all[['workload_cpu', 'workload_memory']])

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

    seq_length = 24  # For hourly data
    X_all, y_all_seq, dates_all = create_sequences(scaled_data, seq_length, y_all.index)

    # Determine the split point
    split_point = len(y_train) - seq_length  # Because sequences start seq_length after the data starts

    X_train = X_all[:split_point]
    y_train_seq = y_all_seq[:split_point]
    dates_train = dates_all[:split_point]

    X_test = X_all[split_point:]
    y_test_seq = y_all_seq[split_point:]
    dates_test = dates_all[split_point:]

    # Build model
    model = Sequential()
    model.add(LSTM(units, activation='relu', input_shape=(seq_length, 2)))  # Units from params
    model.add(Dropout(dropout))
    model.add(Dense(2))  # Output layer with 2 units
    model.compile(optimizer='adam', loss='mse')

    # Train model
    model.fit(X_train, y_train_seq, epochs=epochs, batch_size=batch_size, verbose=0)

    output_path = os.path.join(MODELS_FOLDER_PATH, 'lstm.h5')

    # Save the model
    model.save(output_path)
    print(f"Model saved to {output_path}")

    # Predict
    predictions = model.predict(X_test)
    predictions_inv = scaler.inverse_transform(predictions)
    y_test_inv = scaler.inverse_transform(y_test_seq)

    # Create DataFrames with date
    predictions_df = pd.DataFrame({
        'start_time': dates_test,
        'workload_cpu': predictions_inv[:, 0],
        'workload_memory': predictions_inv[:, 1]
    })
    actual_df = pd.DataFrame({
        'start_time': dates_test,
        'workload_cpu': y_test_inv[:, 0],
        'workload_memory': y_test_inv[:, 1]
    })

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True)

def svm_model(X_train, y_train, X_test, y_test, best_params):
    model_name = 'SVM'
    if model_name in best_params:
        params = best_params[model_name]
    else:
        params = {'kernel':'rbf', 'C':1, 'epsilon':0.01}

    # Scale features
    scaler_X = MinMaxScaler()
    scaler_y = MinMaxScaler()
    X_train_scaled = scaler_X.fit_transform(X_train)
    X_test_scaled = scaler_X.transform(X_test)
    y_train_scaled = scaler_y.fit_transform(y_train)
    y_test_scaled = scaler_y.transform(y_test)

    # Initialize and train model
    model = MultiOutputRegressor(SVR(**params))
    model.fit(X_train_scaled, y_train_scaled)

    output_path = os.path.join(MODELS_FOLDER_PATH, 'svm.pkl')

    # Save the model
    joblib.dump(model, output_path)
    print(f"Model saved to {output_path}")

    # Predict
    predictions_scaled = model.predict(X_test_scaled)
    predictions_inv = scaler_y.inverse_transform(predictions_scaled)
    y_test_inv = scaler_y.inverse_transform(y_test_scaled)

    # Create DataFrames with date
    predictions_df = pd.DataFrame(predictions_inv, columns=['workload_cpu', 'workload_memory'], index=X_test.index)
    actual_df = pd.DataFrame(y_test_inv, columns=['workload_cpu', 'workload_memory'], index=y_test.index)

    return predictions_df.reset_index(), actual_df.reset_index()

def cnn_model(y_train, y_test, best_params):
    model_name = 'CNN'
    if model_name in best_params:
        params = best_params[model_name]
    else:
        params = {'filters':64, 'kernel_size':4, 'dropout':0.2, 'epochs':20, 'batch_size':16}
    filters = params.get('filters', 64)
    kernel_size = params.get('kernel_size', 4)
    dropout = params.get('dropout', 0.2)
    epochs = params.get('epochs', 20)
    batch_size = params.get('batch_size', 16)

    # Combine y_train and y_test to form the complete series
    y_all = pd.concat([y_train, y_test])

    # Prepare data
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(y_all[['workload_cpu', 'workload_memory']])

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

    seq_length = 24  # For hourly data
    X_all, y_all_seq, dates_all = create_sequences(scaled_data, seq_length, y_all.index)

    # Determine the split point
    split_point = len(y_train) - seq_length  # Because sequences start seq_length after the data starts

    X_train = X_all[:split_point]
    y_train_seq = y_all_seq[:split_point]
    dates_train = dates_all[:split_point]

    X_test = X_all[split_point:]
    y_test_seq = y_all_seq[split_point:]
    dates_test = dates_all[split_point:]

    # Build model
    model = Sequential()
    model.add(Conv1D(filters=filters, kernel_size=kernel_size, activation='relu', input_shape=(seq_length, 2)))
    model.add(MaxPooling1D(pool_size=2))
    model.add(Dropout(dropout))
    model.add(Flatten())
    model.add(Dense(50, activation='relu'))
    model.add(Dense(2))  # Output layer with 2 units
    model.compile(optimizer='adam', loss='mse')

    # Train model
    model.fit(X_train, y_train_seq, epochs=epochs, batch_size=batch_size, verbose=0)

    output_path = os.path.join(MODELS_FOLDER_PATH, 'cnn.h5')

    # Save the model
    model.save(output_path)
    print(f"Model saved to {output_path}")

    # Predict
    predictions = model.predict(X_test)
    predictions_inv = scaler.inverse_transform(predictions)
    y_test_inv = scaler.inverse_transform(y_test_seq)

    # Create DataFrames with date
    predictions_df = pd.DataFrame({
        'start_time': dates_test,
        'workload_cpu': predictions_inv[:, 0],
        'workload_memory': predictions_inv[:, 1]
    })
    actual_df = pd.DataFrame({
        'start_time': dates_test,
        'workload_cpu': y_test_inv[:, 0],
        'workload_memory': y_test_inv[:, 1]
    })

    return predictions_df.reset_index(drop=True), actual_df.reset_index(drop=True)


def evaluate_model(predictions_df, actual_df, model_name):
    mae_cpu = mean_absolute_error(actual_df['workload_cpu'], predictions_df['workload_cpu'])
    mse_cpu = mean_squared_error(actual_df['workload_cpu'], predictions_df['workload_cpu'])
    r2_cpu = r2_score(actual_df['workload_cpu'], predictions_df['workload_cpu'])

    mae_memory = mean_absolute_error(actual_df['workload_memory'], predictions_df['workload_memory'])
    mse_memory = mean_squared_error(actual_df['workload_memory'], predictions_df['workload_memory'])
    r2_memory = r2_score(actual_df['workload_memory'], predictions_df['workload_memory'])

    print(f"{model_name} - CPU - MAE: {mae_cpu}, MSE: {mse_cpu}, R2: {r2_cpu}")
    print(f"{model_name} - Memory - MAE: {mae_memory}, MSE: {mse_memory}, R2: {r2_memory}")

    # Create directories if they don't exist
    os.makedirs(PLOTS_FOLDER_PATH, exist_ok=True)
    
    # Save results to a JSON file
    results_file = os.path.join(WORKLOAD_PREDICTOR_FOLDER_PATH, 'results.json')
    results_data = {
        "model_name": model_name,
        "cpu": {
            "mae": mae_cpu,
            "mse": mse_cpu,
            "r2": r2_cpu
        },
        "memory": {
            "mae": mae_memory,
            "mse": mse_memory,
            "r2": r2_memory
        }
    }

    # Append to the JSON file
    if os.path.exists(results_file):
        with open(results_file, 'r+') as f:
            existing_data = json.load(f)
            existing_data.append(results_data)
            f.seek(0)
            json.dump(existing_data, f, indent=4)
    else:
        with open(results_file, 'w') as f:
            json.dump([results_data], f, indent=4)

    # Plotting
    plt.figure(figsize=(30,10))
    plt.plot(actual_df['start_time'], actual_df['workload_cpu'], label='Actual CPU Workload')
    plt.plot(predictions_df['start_time'], predictions_df['workload_cpu'], label=f'Predicted CPU Workload ({model_name})')
    plt.title(f'{model_name} CPU Predictions vs Actual')
    plt.legend()
    plt.savefig(os.path.join(PLOTS_FOLDER_PATH, f'{model_name}_cpu_predictions_vs_actual.png'))
    plt.close()

    plt.figure(figsize=(30,10))
    plt.plot(actual_df['start_time'], actual_df['workload_memory'], label='Actual Memory Workload')
    plt.plot(predictions_df['start_time'], predictions_df['workload_memory'], label=f'Predicted Memory Workload ({model_name})')
    plt.title(f'{model_name} Memory Predictions vs Actual')
    plt.legend()
    plt.savefig(os.path.join(PLOTS_FOLDER_PATH, f'{model_name}_memory_predictions_vs_actual.png'))
    plt.close()

if __name__ == "__main__":
    # Ensure directories exist
    os.makedirs(MODELS_FOLDER_PATH, exist_ok=True)
    os.makedirs(PLOTS_FOLDER_PATH, exist_ok=True)

    # Preprocess data
    X_train, y_train = preprocess_data(VM_TRACE_PATH_TRAIN)
    X_test, y_test = preprocess_data(VM_TRACE_PATH_TEST)
    best_params = load_best_params(WORKLOAD_PREDICTOR_FOLDER_PATH)
    
    # Run models
    print("Running ARIMA model...")
    # predictions_arima, actual_arima = arima_model(y_train, y_test)
    print("Running Random Forest model...")
    predictions_rf, actual_rf = random_forest_model(X_train, y_train, X_test, y_test, best_params)
    print("Running XGBoost model...")
    predictions_xgb, actual_xgb = xgboost_model(X_train, y_train, X_test, y_test, best_params)
    print("Running LightGBM model...")
    predictions_lgbm, actual_lgbm = lightgbm_model(X_train, y_train, X_test, y_test, best_params)
    print("Running LSTM model...")
    predictions_lstm, actual_lstm = lstm_model(y_train, y_test, best_params)
    print("Running SVM model...")
    predictions_svm, actual_svm = svm_model(X_train, y_train, X_test, y_test, best_params)
    print("Running CNN model...")
    predictions_cnn, actual_cnn = cnn_model(y_train, y_test, best_params)

    # Evaluate Models
    # evaluate_model(predictions_arima, actual_arima, 'ARIMA')
    evaluate_model(predictions_rf, actual_rf, 'Random Forest')
    evaluate_model(predictions_xgb, actual_xgb, 'XGBoost')
    evaluate_model(predictions_lgbm, actual_lgbm, 'LightGBM')
    evaluate_model(predictions_lstm, actual_lstm, 'LSTM')
    evaluate_model(predictions_svm, actual_svm, 'SVM')
    evaluate_model(predictions_cnn, actual_cnn, 'CNN')
