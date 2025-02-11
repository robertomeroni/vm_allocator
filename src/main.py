import argparse
import csv
import importlib.util
import os
import shutil
import sys
import time
import numpy as np

from calculate import calculate_performance_metrics, count_non_valid_entries
from data_generator import generate_pms
from log import create_log_folder, log_final_net_profit, log_initial_physical_machines
from simulation import simulate_time_steps
from utils import (
    clean_up_model_input_files,
    load_configuration,
    load_physical_machines,
    load_pm_database,
    load_virtual_machines,
    save_energy_intensity,
)

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument(
    "--config", default="src/config.py", help="Path to the configuration file"
)
parser.add_argument("--trace", help="Path to the VM trace file")
if "--trace" in sys.argv:
    print("Trace file argument provided")
parser.add_argument(
    "--generate-pms", type=int, help="Number of physical machines to generate"
)
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
PM_DATABASE_FILE = getattr(config, "PM_DATABASE_FILE", None)
ENERGY_INTENSITY_FILE = getattr(config, "ENERGY_INTENSITY_FILE", None)
SIMULATION_INPUT_FOLDER_PATH = getattr(config, "SIMULATION_INPUT_FOLDER_PATH", None)
OUTPUT_FOLDER_PATH = getattr(config, "OUTPUT_FOLDER_PATH", None)
MACRO_MODEL_INPUT_FOLDER_PATH = getattr(config, "MACRO_MODEL_INPUT_FOLDER_PATH", None)
MACRO_MODEL_OUTPUT_FOLDER_PATH = getattr(config, "MACRO_MODEL_OUTPUT_FOLDER_PATH", None)
MICRO_MODEL_INPUT_FOLDER_PATH = getattr(config, "MICRO_MODEL_INPUT_FOLDER_PATH", None)
MICRO_MODEL_OUTPUT_FOLDER_PATH = getattr(config, "MICRO_MODEL_OUTPUT_FOLDER_PATH", None)
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
COMPOSITION = getattr(config, "COMPOSITION", None)
COMPOSITION_SHAPE = getattr(config, "COMPOSITION_SHAPE", None)
WORKLOAD_NAME = getattr(config, "WORKLOAD_NAME", None)
PRINT_TO_CONSOLE = getattr(config, "PRINT_TO_CONSOLE", None)
SAVE_LOGS = getattr(config, "SAVE_LOGS", None)
SAVE_VM_AND_PM_SETS = getattr(config, "SAVE_VM_AND_PM_SETS", None)
ALGORITHM = getattr(config, "ALGORITHM", None)
USE_LOAD_BALANCER = getattr(config, "USE_LOAD_BALANCER", None)
MACRO_MODEL_MAX_PMS = getattr(config, "MACRO_MODEL_MAX_PMS", None)
MACRO_MODEL_MAX_SUBSETS = getattr(config, "MACRO_MODEL_MAX_SUBSETS", None)
MICRO_MODEL_MAX_PMS = getattr(config, "MICRO_MODEL_MAX_PMS", None)
MICRO_MODEL_MAX_VMS = getattr(config, "MICRO_MODEL_MAX_VMS", None)
MIGRATION_MODEL_MAX_FRAGMENTED_PMS = getattr(
    config, "MIGRATION_MODEL_MAX_FRAGMENTED_PMS", None
)
FAILED_MIGRATIONS_LIMIT = getattr(config, "FAILED_MIGRATIONS_LIMIT", None)
PM_MANAGER_MAX_PMS = getattr(config, "PM_MANAGER_MAX_PMS", None)
EPGAP_MACRO = getattr(config, "EPGAP_MACRO", None)
EPGAP_MICRO = getattr(config, "EPGAP_MICRO", None)
EPGAP_MIGRATION = getattr(config, "EPGAP_MIGRATION", None)
EPGAP_PM_MANAGER = getattr(config, "EPGAP_PM_MANAGER", None)
HARD_TIME_LIMIT_MACRO = getattr(config, "HARD_TIME_LIMIT_MACRO", None)
HARD_TIME_LIMIT_MICRO = getattr(config, "HARD_TIME_LIMIT_MICRO", None)
HARD_TIME_LIMIT_MIGRATION = getattr(config, "HARD_TIME_LIMIT_MIGRATION", None)

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

if args.generate_pms:
    generate_pms(args.generate_pms, COMPOSITION, COMPOSITION_SHAPE)

if USE_RANDOM_SEED:
    np.random.seed(SEED_NUMBER)

# Ensure the directories exist
os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MACRO_MODEL_INPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MACRO_MODEL_OUTPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MICRO_MODEL_INPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MICRO_MODEL_OUTPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(SIMULATION_INPUT_FOLDER_PATH, exist_ok=True)

if os.path.expanduser(INITIAL_PMS_FILE) != os.path.join(
    SIMULATION_INPUT_FOLDER_PATH, os.path.basename(INITIAL_PMS_FILE)
):
    shutil.copy(
        os.path.expanduser(INITIAL_PMS_FILE),
        os.path.join(SIMULATION_INPUT_FOLDER_PATH, os.path.basename(INITIAL_PMS_FILE)),
    )


if __name__ == "__main__":
    total_start_time = time.time()  # Record the start time

    initial_vms = load_virtual_machines(os.path.expanduser(INITIAL_VMS_FILE))
    initial_pms = load_physical_machines(os.path.expanduser(INITIAL_PMS_FILE))
    log_folder_path, performance_log_file, vm_execution_time_file = create_log_folder()
    log_initial_physical_machines(initial_pms, log_folder_path)
    load_configuration(MACRO_MODEL_INPUT_FOLDER_PATH, EPGAP_MACRO)
    load_configuration(MICRO_MODEL_INPUT_FOLDER_PATH, EPGAP_MICRO)
    load_configuration(MIGRATION_MODEL_INPUT_FOLDER_PATH, EPGAP_MIGRATION)
    load_configuration(PM_MANAGER_INPUT_FOLDER_PATH, EPGAP_PM_MANAGER)

    save_energy_intensity(os.path.expanduser(INITIAL_PMS_FILE))
    (
        pm_database,
        power_function_database,
        speed_function_database,
        energy_intensity_database,
    ) = load_pm_database(COMPOSITION, COMPOSITION_SHAPE)
    nb_points = len(next(iter(energy_intensity_database.values())))

    (
        total_revenue,
        total_costs,
        total_pm_switch_costs,
        total_pm_load_costs,
        total_migration_costs,
        num_completed_migrations,
        max_percentage_of_pms_on,
        total_cpu_load,
        total_memory_load,
        total_fully_on_pm,
        num_steps,
        total_algorithm_runtime,
    ) = simulate_time_steps(
        initial_vms,
        initial_pms,
        NUM_TIME_STEPS,
        NEW_VMS_PER_STEP,
        nb_points,
        power_function_database,
        speed_function_database,
        energy_intensity_database,
        log_folder_path,
        VMS_TRACE_FILE,
        performance_log_file,
        vm_execution_time_file,
        TIME_STEP,
        ALGORITHM,
        USE_LOAD_BALANCER,
        USE_REAL_DATA,
        PRINT_TO_CONSOLE,
        SAVE_LOGS,
        STARTING_STEP,
        MACRO_MODEL_MAX_SUBSETS,
        MACRO_MODEL_MAX_PMS,
        MICRO_MODEL_MAX_PMS,
        MICRO_MODEL_MAX_VMS,
        MIGRATION_MODEL_MAX_FRAGMENTED_PMS,
        FAILED_MIGRATIONS_LIMIT,
        PM_MANAGER_MAX_PMS,
        HARD_TIME_LIMIT_MACRO,
        HARD_TIME_LIMIT_MICRO,
        HARD_TIME_LIMIT_MIGRATION,
        NEW_VMS_PATTERN,
    )

    non_valid_entries, total_entries = count_non_valid_entries(performance_log_file)
    avg_wait_time, runtime_efficiency, overall_time_efficiency = (
        calculate_performance_metrics(vm_execution_time_file)
    )

    log_final_net_profit(
        total_revenue,
        total_costs,
        total_pm_switch_costs,
        total_pm_load_costs,
        total_migration_costs,
        num_completed_migrations,
        max_percentage_of_pms_on,
        total_cpu_load,
        total_memory_load,
        total_fully_on_pm,
        len(initial_pms),
        non_valid_entries,
        total_entries,
        avg_wait_time,
        runtime_efficiency,
        overall_time_efficiency,
        total_algorithm_runtime,
        log_folder_path,
        ALGORITHM,
        USE_RANDOM_SEED,
        TIME_STEP,
        num_steps,
        USE_REAL_DATA,
        WORKLOAD_NAME,
        NEW_VMS_PATTERN,
    )
    clean_up_model_input_files()

    total_end_time = time.time()  # Record the end time
    total_execution_time = (
        total_end_time - total_start_time
    )  # Calculate the total execution time
    with open(performance_log_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Total Algorithm Runtime", total_algorithm_runtime])
        writer.writerow(
            ["Total Execution Time", total_execution_time]
        )  # Log the total execution time
    print(f"Total execution time: {total_execution_time} seconds")
