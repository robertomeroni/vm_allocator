import argparse
import importlib.util
import sys
import os
import time
import csv
import numpy as np

from log import create_log_folder, log_final_net_profit, log_initial_physical_machines
from simulation import simulate_time_steps
from utils import (
    clean_up_model_input_files,
    count_non_valid_entries,
    load_configuration,
    load_physical_machines,
    load_virtual_machines,
    parse_power_function,
    save_power_function,
)

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument(
    "--config", default="src/config.py", help="Path to the configuration file"
)
parser.add_argument("--trace", help="Path to the VM trace file")
if "--trace" in sys.argv:
    print("Trace file argument provided")
args = parser.parse_args()

# Dynamically import the config file
spec = importlib.util.spec_from_file_location("config", args.config)
config = importlib.util.module_from_spec(spec)

try:
    spec.loader.exec_module(config)
except FileNotFoundError:
    print(f"Configuration file {args.config} not found.")
    exit(1)
except Exception as e:
    print(f"Error loading configuration file: {e}")
    exit(1)

# Access configuration constants using the config object
INITIAL_VMS_FILE = getattr(config, "INITIAL_VMS_FILE", None)
INITIAL_PMS_FILE = getattr(config, "INITIAL_PMS_FILE", None)
POWER_FUNCTION_FILE = getattr(config, "POWER_FUNCTION_FILE", None)
SIMULATION_INPUT_FOLDER_PATH = getattr(config, "SIMULATION_INPUT_FOLDER_PATH", None)
OUTPUT_FOLDER_PATH = getattr(config, "OUTPUT_FOLDER_PATH", None)
MODEL_INPUT_FOLDER_PATH = getattr(config, "MODEL_INPUT_FOLDER_PATH", None)
MODEL_OUTPUT_FOLDER_PATH = getattr(config, "MODEL_OUTPUT_FOLDER_PATH", None)
MINI_MODEL_INPUT_FOLDER_PATH = getattr(config, "MINI_MODEL_INPUT_FOLDER_PATH", None)
MINI_MODEL_OUTPUT_FOLDER_PATH = getattr(config, "MINI_MODEL_OUTPUT_FOLDER_PATH", None)
MIGRATION_MODEL_INPUT_FOLDER_PATH = getattr(
    config, "MIGRATION_MODEL_INPUT_FOLDER_PATH", None
)
MIGRATION_MODEL_OUTPUT_FOLDER_PATH = getattr(
    config, "MIGRATION_MODEL_OUTPUT_FOLDER_PATH", None
)
PM_MANAGER_INPUT_FOLDER_PATH = getattr(config, "PM_MANAGER_INPUT_FOLDER_PATH", None)
PM_MANAGER_OUTPUT_FOLDER_PATH = getattr(config, "PM_MANAGER_OUTPUT_FOLDER_PATH", None)
TIME_STEP = getattr(config, "TIME_STEP", None)
NEW_VMS_PER_STEP = getattr(config, "NEW_VMS_PER_STEP", None)
NEW_VMS_PATTERN = getattr(config, "NEW_VMS_PATTERN", None)
NUM_TIME_STEPS = getattr(config, "NUM_TIME_STEPS", None)
USE_RANDOM_SEED = getattr(config, "USE_RANDOM_SEED", None)
SEED_NUMBER = getattr(config, "SEED_NUMBER", None)
STARTING_STEP = getattr(config, "STARTING_STEP", None)
USE_REAL_DATA = getattr(config, "USE_REAL_DATA", None)
WORKLOAD_NAME = getattr(config, "WORKLOAD_NAME", None)
PRINT_TO_CONSOLE = getattr(config, "PRINT_TO_CONSOLE", None)
SAVE_LOGS = getattr(config, "SAVE_LOGS", None)
SAVE_VM_AND_PM_SETS = getattr(config, "SAVE_VM_AND_PM_SETS", None)
MASTER_MODEL = getattr(config, "MASTER_MODEL", None)
USE_FILTER = getattr(config, "USE_FILTER", None)
MAIN_MODEL_MAX_PMS = getattr(config, "MAIN_MODEL_MAX_PMS", None)
MINI_MODEL_MAX_PMS = getattr(config, "MINI_MODEL_MAX_PMS", None)
MIGRATION_MODEL_MAX_FRAGMENTED_PMS = getattr(
    config, "MIGRATION_MODEL_MAX_FRAGMENTED_PMS", None
)
FAILED_MIGRATIONS_LIMIT = getattr(config, "FAILED_MIGRATIONS_LIMIT", None)
PM_MANAGER_MAX_PMS = getattr(config, "PM_MANAGER_MAX_PMS", None)
EPGAP_MAIN = getattr(config, "EPGAP_MAIN", None)
EPGAP_MINI = getattr(config, "EPGAP_MINI", None)
EPGAP_MIGRATION = getattr(config, "EPGAP_MIGRATION", None)
EPGAP_PM_MANAGER = getattr(config, "EPGAP_PM_MANAGER", None)
HARD_TIME_LIMIT_MAIN = getattr(config, "HARD_TIME_LIMIT_MAIN", None)
HARD_TIME_LIMIT_MINI = getattr(config, "HARD_TIME_LIMIT_MINI", None)

# Set VMS_TRACE_FILE if --trace argument is provided
if USE_REAL_DATA:
    VMS_TRACE_FILE = (
        args.trace if args.trace else getattr(config, "VMS_TRACE_FILE", None)
    )
    if (
        VMS_TRACE_FILE
        and not os.path.isabs(VMS_TRACE_FILE)
        and not os.path.exists(VMS_TRACE_FILE)
    ):
        VMS_TRACE_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, VMS_TRACE_FILE)
else:
    VMS_TRACE_FILE = None

if USE_RANDOM_SEED:
    np.random.seed(SEED_NUMBER)

# Ensure the directories exist
os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MODEL_INPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MODEL_OUTPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MINI_MODEL_INPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MINI_MODEL_OUTPUT_FOLDER_PATH, exist_ok=True)

if __name__ == "__main__":
    total_start_time = time.time()  # Record the start time

    initial_vms = load_virtual_machines(os.path.expanduser(INITIAL_VMS_FILE))
    initial_pms = load_physical_machines(os.path.expanduser(INITIAL_PMS_FILE))
    log_folder_path = create_log_folder()
    log_initial_physical_machines(initial_pms, log_folder_path)
    performance_log_file = os.path.join(log_folder_path, "performance.csv")
    load_configuration(MODEL_INPUT_FOLDER_PATH, EPGAP_MAIN)
    load_configuration(MINI_MODEL_INPUT_FOLDER_PATH, EPGAP_MINI)
    load_configuration(MIGRATION_MODEL_INPUT_FOLDER_PATH, EPGAP_MIGRATION)
    load_configuration(PM_MANAGER_INPUT_FOLDER_PATH, EPGAP_PM_MANAGER)

    save_power_function(os.path.expanduser(INITIAL_PMS_FILE))
    pm_ids = list(initial_pms.keys())
    nb_points, power_function_dict = parse_power_function(POWER_FUNCTION_FILE, pm_ids)
    (
        total_revenue,
        total_costs,
        total_pm_energy_cost,
        total_migration_energy_cost,
        num_completed_migrations,
        max_percentage_of_pms_on,
        total_cpu_load,
        total_memory_load,
        total_fully_on_pm,
        num_steps,
    ) = simulate_time_steps(
        initial_vms,
        initial_pms,
        NUM_TIME_STEPS,
        NEW_VMS_PER_STEP,
        nb_points,
        power_function_dict,
        log_folder_path,
        VMS_TRACE_FILE,
        performance_log_file,
        TIME_STEP,
        MASTER_MODEL,
        USE_FILTER,
        USE_REAL_DATA,
        PRINT_TO_CONSOLE,
        STARTING_STEP,
        MAIN_MODEL_MAX_PMS,
        MINI_MODEL_MAX_PMS,
        MIGRATION_MODEL_MAX_FRAGMENTED_PMS,
        FAILED_MIGRATIONS_LIMIT,
        PM_MANAGER_MAX_PMS,
        HARD_TIME_LIMIT_MAIN,
        HARD_TIME_LIMIT_MINI,
        NEW_VMS_PATTERN,
    )
    non_valid_entries, total_entries = count_non_valid_entries(performance_log_file)
    log_final_net_profit(
        total_revenue,
        total_costs,
        total_pm_energy_cost,
        total_migration_energy_cost,
        num_completed_migrations,
        max_percentage_of_pms_on,
        total_cpu_load,
        total_memory_load,
        total_fully_on_pm,
        len(initial_pms),
        non_valid_entries,
        total_entries,
        log_folder_path,
        MASTER_MODEL,
        USE_RANDOM_SEED,
        SEED_NUMBER,
        TIME_STEP,
        num_steps,
        USE_REAL_DATA,
        WORKLOAD_NAME,
    )
    clean_up_model_input_files()

    total_end_time = time.time()  # Record the end time
    total_execution_time = (
        total_end_time - total_start_time
    )  # Calculate the total execution time
    with open(performance_log_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["Total Execution Time", total_execution_time]
        )  # Log the total execution time
    print(f"Total execution time: {total_execution_time} seconds")
