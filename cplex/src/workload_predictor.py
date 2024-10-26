import json
import os
import pandas as pd
import numpy as np
import joblib
from sklearn.linear_model import LinearRegression
from utils import get_start_time, get_exact_time, calculate_features, get_real_cpu_and_memory
from config import ARRIVALS_TRACKING_FILE
from weights import step_window_for_online_prediction, step_window_for_weights_accuracy

try:
    profile # type: ignore
except NameError:
    def profile(func):
        return func
    
@profile
def track_arrivals(workload_name, step, time_step, vms=[]):
    start_time_str = get_start_time(workload_name)
    exact_time = get_exact_time(start_time_str, step, time_step)
    total_cpu = sum(vm['requested']['cpu'] for vm in vms)
    total_memory = sum(vm['requested']['memory'] for vm in vms)
    print(f"Total workload arrived at step {step}: CPU = {total_cpu}, Memory = {total_memory}")

    arrival_data = {
        'time': exact_time.strftime('%Y-%m-%d %H:%M:%S'),
        'cpu': total_cpu,
        'memory': total_memory
    }

    # Append the new arrival data to the file
    with open(ARRIVALS_TRACKING_FILE, 'a') as file:
        json.dump(arrival_data, file)
        file.write('\n')

def preprocess_workload_trace(time_step, arrivals_tracking_file=ARRIVALS_TRACKING_FILE):
    results = []
    # Check if the file exists
    if os.path.exists(arrivals_tracking_file):
        with open(arrivals_tracking_file, 'r') as file:
            for line in file:
                # Remove any leading/trailing whitespace
                line = line.strip()
                if line:
                    # Parse each line as a JSON object
                    arrival = json.loads(line)
                    results.append({
                        'time': arrival['time'],
                        'cpu': arrival['cpu'],
                        'memory': arrival['memory']
                    })
    else:
        print(f"The file {arrivals_tracking_file} does not exist.")
        return pd.DataFrame()  # Return an empty DataFrame if the file doesn't exist

    # Convert the list of arrival data to a pandas DataFrame
    df = pd.DataFrame(results)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)

    # Ensure time_step is a valid frequency string
    if isinstance(time_step, int):
        time_step_str = f'{time_step}s'  # Convert to seconds if time_step is an integer
    else:
        time_step_str = time_step

    # Resample and aggregate the data
    aggregated = df.resample(time_step_str).sum()
    aggregated = aggregated.asfreq(time_step_str, fill_value=0)
    return aggregated

def get_weighted_accuracy(accuracies):
    N = len(accuracies)
    if N == 0:
        return None, None, None, None

    total_weight = N * (N + 1) / 2  # Sum of weights from 1 to N
    sum_accuracy_online_cpu = 0
    sum_accuracy_online_memory = 0
    sum_accuracy_offline_cpu = 0
    sum_accuracy_offline_memory = 0

    for i, (acc_online_cpu, acc_online_memory, acc_offline_cpu, acc_offline_memory) in enumerate(accuracies):
        weight = (i + 1) / total_weight  # Weights increase with each step
        sum_accuracy_online_cpu += weight * acc_online_cpu
        sum_accuracy_online_memory += weight * acc_online_memory
        sum_accuracy_offline_cpu += weight * acc_offline_cpu
        sum_accuracy_offline_memory += weight * acc_offline_memory

    accuracy_online_cpu = sum_accuracy_online_cpu
    accuracy_online_memory = sum_accuracy_online_memory
    accuracy_offline_cpu = sum_accuracy_offline_cpu
    accuracy_offline_memory = sum_accuracy_offline_memory

    return accuracy_online_cpu, accuracy_online_memory, accuracy_offline_cpu, accuracy_offline_memory

def calculate_accuracies(last_predictions, aggregated, start_time_str, actual_time_step, time_step):
    accuracies = []
    sorted_steps = sorted(last_predictions.keys())

    for step in sorted_steps:
        if step > actual_time_step:
            break
        real_cpu, real_memory = get_real_cpu_and_memory(step, start_time_str, aggregated, time_step)
        if real_cpu is None or real_memory is None:
            continue

        # Online predictions
        if 'online' in last_predictions[step]:
            predicted_cpu_online = last_predictions[step]['online']['cpu']
            predicted_memory_online = last_predictions[step]['online']['memory']

            # CPU error using sMAPE
            denominator_cpu_online = abs(real_cpu) + abs(predicted_cpu_online)
            if denominator_cpu_online == 0:
                error_cpu_online = 0  # Both real and predicted are zero
            else:
                error_cpu_online = 2 * abs(real_cpu - predicted_cpu_online) / denominator_cpu_online

            # Memory error using sMAPE
            denominator_memory_online = abs(real_memory) + abs(predicted_memory_online)
            if denominator_memory_online == 0:
                error_memory_online = 0  # Both real and predicted are zero
            else:
                error_memory_online = 2 * abs(real_memory - predicted_memory_online) / denominator_memory_online

            # Accuracy calculations
            step_accuracy_online_cpu = max(0, 1 - error_cpu_online / 2)
            step_accuracy_online_memory = max(0, 1 - error_memory_online / 2)
        else:
            step_accuracy_online_cpu = 0
            step_accuracy_online_memory = 0

        # Offline predictions
        if 'offline' in last_predictions[step]:
            predicted_cpu_offline = last_predictions[step]['offline']['cpu']
            predicted_memory_offline = last_predictions[step]['offline']['memory']

            # CPU error using sMAPE
            denominator_cpu_offline = abs(real_cpu) + abs(predicted_cpu_offline)
            if denominator_cpu_offline == 0:
                error_cpu_offline = 0  # Both real and predicted are zero
            else:
                error_cpu_offline = 2 * abs(real_cpu - predicted_cpu_offline) / denominator_cpu_offline

            # Memory error using sMAPE
            denominator_memory_offline = abs(real_memory) + abs(predicted_memory_offline)
            if denominator_memory_offline == 0:
                error_memory_offline = 0  # Both real and predicted are zero
            else:
                error_memory_offline = 2 * abs(real_memory - predicted_memory_offline) / denominator_memory_offline

            # Accuracy calculations
            step_accuracy_offline_cpu = max(0, 1 - error_cpu_offline / 2)
            step_accuracy_offline_memory = max(0, 1 - error_memory_offline / 2)
        else:
            step_accuracy_offline_cpu = 0
            step_accuracy_offline_memory = 0

        accuracies.append((
            step_accuracy_online_cpu,
            step_accuracy_online_memory,
            step_accuracy_offline_cpu,
            step_accuracy_offline_memory
        ))
    return get_weighted_accuracy(accuracies)


def calculate_weights(last_predictions, aggregated, start_time_str, actual_time_step, time_step):
    accuracy_online_cpu, accuracy_online_memory, accuracy_offline_cpu, accuracy_offline_memory = calculate_accuracies(last_predictions, aggregated, start_time_str, actual_time_step, time_step)
    
    if accuracy_online_cpu and accuracy_online_memory:
        w_online_cpu = accuracy_online_cpu / (accuracy_online_cpu + accuracy_offline_cpu)
        w_online_memory = accuracy_online_memory / (accuracy_online_memory + accuracy_offline_memory)
    else:
        w_online_cpu = 0
        w_online_memory = 0

    if accuracy_offline_cpu and accuracy_offline_memory:
        w_offline_cpu = accuracy_offline_cpu / (accuracy_online_cpu + accuracy_offline_cpu)
        w_offline_memory = accuracy_offline_memory / (accuracy_online_memory + accuracy_offline_memory)
    else:
        w_offline_cpu = 0
        w_offline_memory = 0
    
    return w_online_cpu, w_online_memory, w_offline_cpu, w_offline_memory

def save_workload_prediction(predictions, step, method, predicted_cpu, predicted_memory, workload_prediction_file):
    if not isinstance(method, str):
        raise ValueError(f"Method must be a string, got {type(method)}")

    # Update the predictions dictionary
    predictions[step][method]['cpu'] = predicted_cpu
    predictions[step][method]['memory'] = predicted_memory

    # Ensure the directory exists
    os.makedirs(os.path.dirname(workload_prediction_file), exist_ok=True)

    # Load existing data if the file exists
    if os.path.isfile(workload_prediction_file):
        try:
            with open(workload_prediction_file, 'r') as file:
                existing_data = json.load(file)
                for existing_step, methods in existing_data.items():
                    step_key = int(existing_step) if isinstance(existing_step, str) and existing_step.isdigit() else existing_step
                    for existing_method, metrics in methods.items():
                        predictions[step_key][existing_method].update(metrics)
        except json.JSONDecodeError:
            print("Warning: JSON file is corrupted or empty. Starting fresh.")
        except Exception as e:
            print(f"An error occurred while loading existing predictions: {e}")

    with open(workload_prediction_file, 'w') as file:
        json.dump(predictions, file, indent=4)

def predict_workload_online(workload_prediciton_file, aggregated, actual_time_step, step_to_predict, step_window=step_window_for_online_prediction):
    last_steps = aggregated.iloc[-step_window:]
    relative_step_to_predict = step_to_predict - actual_time_step + step_window - 1

    # Prepare the time steps as features
    X = np.arange(len(last_steps)).reshape(-1, 1)

    # Predict CPU usage
    y_cpu = last_steps['cpu'].values
    model_cpu = LinearRegression()
    model_cpu.fit(X, y_cpu)
    predicted_cpu = model_cpu.predict(np.array([[relative_step_to_predict]]))[0]
    predicted_cpu = max(predicted_cpu, 0)  # Ensure no negative values

    # Predict Memory usage
    y_memory = last_steps['memory'].values
    model_memory = LinearRegression()
    model_memory.fit(X, y_memory)
    predicted_memory = model_memory.predict(np.array([[relative_step_to_predict]]))[0]
    predicted_memory = max(predicted_memory, 0)  # Ensure no negative values

    return predicted_cpu, predicted_memory

def predict_workload_offline(step_to_predict, start_time_str, predictor_model_path, time_step):
    trained_predictor = joblib.load(predictor_model_path)
    features = calculate_features(step_to_predict, start_time_str, time_step)
    predicted_workload_offline = trained_predictor.predict(features)

    return predicted_workload_offline[0]

def predict_workload(actual_time_step, step_to_predict, start_time_str, predictions, predictor_model_path, workload_prediction_file, time_step):
    print(f"\nFrom step {actual_time_step}: predicting workload for step {step_to_predict}...")
    # Online prediction
    if os.path.exists(ARRIVALS_TRACKING_FILE):
        aggregated = preprocess_workload_trace(time_step, ARRIVALS_TRACKING_FILE)
        predicted_cpu_online, predicted_memory_online = predict_workload_online(workload_prediction_file, aggregated, actual_time_step, step_to_predict)
        save_workload_prediction(predictions, step_to_predict, 'online', predicted_cpu_online, predicted_memory_online, workload_prediction_file)
        print(f"Online prediction: CPU = {predicted_cpu_online}, Memory = {predicted_memory_online}")
    else:
        print("No arrivals tracking file found, not using online prediction")
        predicted_cpu_online = 0
        predicted_memory_online = 0
        w_online_cpu = 0
        w_online_memory = 0

    # Offline prediction
    if os.path.exists(workload_prediction_file):
        predicted_cpu_offline, predicted_memory_offline = predict_workload_offline(step_to_predict, start_time_str, predictor_model_path, time_step)
        save_workload_prediction(predictions, step_to_predict, 'offline', predicted_cpu_offline, predicted_memory_offline, workload_prediction_file)
        w_offline_cpu = 1
        w_offline_memory = 1
        print(f"Offline prediction: CPU = {predicted_cpu_offline}, Memory = {predicted_memory_offline}")
    else:
        print("No predictor model found, not using offline prediction")
        predicted_cpu_offline = 0
        predicted_memory_offline = 0
        w_offline_cpu = 0
        w_offline_memory = 0

    if os.path.exists(ARRIVALS_TRACKING_FILE) and aggregated is not None:
        last_predictions = {}
        for prediction in predictions:
            if len(last_predictions) > step_window_for_weights_accuracy:
                break
            if prediction <= actual_time_step:
                last_predictions[prediction] = predictions[prediction]
        w_online_cpu, w_online_memory, w_offline_cpu, w_offline_memory = calculate_weights(last_predictions, aggregated, start_time_str, actual_time_step, time_step)

    print(f"step_window_for_weights_accuracy: {step_window_for_weights_accuracy}")
    print(f"w_online_cpu: {w_online_cpu}, w_online_memory: {w_online_memory}, w_offline_cpu: {w_offline_cpu}, w_offline_memory: {w_offline_memory}")
    predicted_cpu = predicted_cpu_online * w_online_cpu + predicted_cpu_offline * w_offline_cpu
    predicted_memory = predicted_memory_online * w_online_memory + predicted_memory_offline * w_offline_memory
    save_workload_prediction(predictions, step_to_predict, 'combined', predicted_cpu, predicted_memory, workload_prediction_file)
    print(f"Combined prediction: CPU = {predicted_cpu}, Memory = {predicted_memory}")
    return predicted_cpu, predicted_memory

