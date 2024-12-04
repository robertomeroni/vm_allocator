import os

# General
USE_RANDOM_SEED = True
SEED_NUMBER = 1
PRINT_TO_CONSOLE = True
SAVE_VM_AND_PM_SETS = False
SAVE_LOGS = True

# Workload
USE_REAL_DATA = True

# WORKLOAD_NAME = "Intel-Netbatch-2012-A"
# WORKLOAD_NAME = "Intel-Netbatch-2012-B"
# WORKLOAD_NAME = "Intel-Netbatch-2012-C"
# WORKLOAD_NAME = "Intel-Netbatch-2012-D"
# WORKLOAD_NAME = "LLNL-Thunder-2007"
# WORKLOAD_NAME = "METACENTRUM-2009"
# WORKLOAD_NAME = "PIK-IPLEX-2009"
# WORKLOAD_NAME = "RICC-2010"
# WORKLOAD_NAME = "TU-Delft-2007"
# WORKLOAD_NAME = "UniLu-Gaia-2014"
# WORKLOAD_NAME = "Azure-2020"
# WORKLOAD_NAME = "Chameleon-Legacy-2020"
WORKLOAD_NAME = "Chameleon-New-2020"

# Simulation parameters
STARTING_STEP = 1
TIME_STEP = 50  # Time step in seconds
NUM_TIME_STEPS = 50000000  # Number of time steps to simulate

NEW_VMS_PER_STEP = 30  # Expected number of new VMs to generate at each time step
NEW_VMS_PATTERN = "random_spikes"

# Models to use
MASTER_MODEL = "main"
# MASTER_MODEL = "mini"
# MASTER_MODEL = "hybrid"
# MASTER_MODEL = "compound"
# MASTER_MODEL = "multilayer"
# MASTER_MODEL = "first_fit"
# MASTER_MODEL = "best_fit"
# MASTER_MODEL = "guazzone"
# MASTER_MODEL = "shi_OM"
# MASTER_MODEL = "shi_AC"
# MASTER_MODEL = "shi_PU"

MAIN_MODEL_MAX_SUBSETS = 5
MAIN_MODEL_MAX_PMS = 20
MINI_MODEL_MAX_PMS = 50
MINI_MODEL_MAX_VMS = 200
FAILED_MIGRATIONS_LIMIT = 5
MIGRATION_MODEL_MAX_FRAGMENTED_PMS = 4 * FAILED_MIGRATIONS_LIMIT
PM_MANAGER_MAX_PMS = 10

# Hard time limits
HARD_TIME_LIMIT_MAIN = TIME_STEP / 2
HARD_TIME_LIMIT_MINI = TIME_STEP / 2
HARD_TIME_LIMIT_MIGRATION = 1

# CPLEX parameters
EPGAP_MAIN = 0.01
EPGAP_MINI = 0.01
EPGAP_MIGRATION = 0.02
EPGAP_PM_MANAGER = 0.03

USE_LOAD_BALANCER = True
if not USE_REAL_DATA:
    WORKLOAD_NAME = "synthetic"

# Paths
BASE_PATH = ""
SIMULATION_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, "simulation/simulation_input")
MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, "simulation/model_input_main")
MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, "simulation/model_output_main")
MINI_MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, "simulation/model_input_mini")
MINI_MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, "simulation/model_output_mini")
MIGRATION_MODEL_INPUT_FOLDER_PATH = os.path.join(
    BASE_PATH, "simulation/model_input_migration"
)
MIGRATION_MODEL_OUTPUT_FOLDER_PATH = os.path.join(
    BASE_PATH, "simulation/model_output_migration"
)
PM_MANAGER_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, "simulation/pm_manager/input")
PM_MANAGER_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, "simulation/pm_manager/output")
OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, "simulation/simulation_output")
LOGS_FOLDER_PATH = os.path.join(BASE_PATH, "logs")

FLOW_CONTROL_PATH = os.path.join(BASE_PATH, "model/flow_control.mod")
INITIAL_PMS_FILE = os.path.join(
    SIMULATION_INPUT_FOLDER_PATH, f"physical_machines_{WORKLOAD_NAME}.dat"
)
INITIAL_VMS_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, "virtual_machines.dat")
VMS_TRACE_FILE = os.path.join(
    SIMULATION_INPUT_FOLDER_PATH, f"workload_files/{WORKLOAD_NAME}.json"
)
PM_DATABASE_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, "pm_database.csv")
SPECIFIC_POWER_FUNCTION_FILE = os.path.join(
    MODEL_INPUT_FOLDER_PATH, "specific_power_function.dat"
)
