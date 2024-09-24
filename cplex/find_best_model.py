import json
import os

def find_best_model(workload_predictor_folder_path):
    best_models = {}

    for workload_name in os.listdir(workload_predictor_folder_path):
        workload_path = os.path.join(workload_predictor_folder_path, workload_name)
        results_file = os.path.join(workload_path, 'results.json')

        if os.path.isdir(workload_path) and os.path.exists(results_file):
            with open(results_file, 'r') as f:
                results_data = json.load(f)

            best_model = min(results_data, key=lambda x: x['cpu']['mae'])
            best_models[workload_name] = best_model

    return best_models

if __name__ == "__main__":
    # Path to the workload predictor folder
    WORKLOAD_PREDICTOR_FOLDER_PATH = 'workload_predictor'

    # Find the best models
    best_models = find_best_model(WORKLOAD_PREDICTOR_FOLDER_PATH)

    # Save the best models to a new JSON file
    best_models_file = os.path.join(WORKLOAD_PREDICTOR_FOLDER_PATH, 'best_models.json')
    with open(best_models_file, 'w') as f:
        json.dump(best_models, f, indent=4)