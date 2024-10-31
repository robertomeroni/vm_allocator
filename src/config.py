import os

# General
USE_RANDOM_SEED = True
SEED_NUMBER = 1
PRINT_TO_CONSOLE = True
SAVE_VM_AND_PM_SETS = False
SAVE_LOGS = True
PERFORMANCE_MEASUREMENT = True

# Workload 
USE_REAL_DATA = True
USE_FILTER = True

# WORKLOAD_NAME = 'Intel-NetbatchA-2012'
# WORKLOAD_NAME = 'LLNL-Thunder-2007'
# WORKLOAD_NAME = 'METACENTRUM-2009'
# WORKLOAD_NAME = 'METACENTRUM-2013'
# WORKLOAD_NAME = 'PIK-IPLEX-2009'
# WORKLOAD_NAME = 'TU-Delft-2007'
# WORKLOAD_NAME = 'UniLu-Gaia-2014'

WORKLOAD_NAME = 'Azure-2020'
# WORKLOAD_NAME = 'Chameleon-Legacy-2020'
# WORKLOAD_NAME = 'Chameleon-New-2020'

# Simulation parameters
STARTING_STEP = 1
TIME_STEP = 5 # Time step in seconds
NUM_TIME_STEPS = 20000 # Number of time steps to simulate
NEW_VMS_PER_STEP = 2  # Expected number of new VMs to generate at each time step

# Models to use
MASTER_MODEL = 'main'
# MASTER_MODEL = 'mini'
# MASTER_MODEL = 'hybrid'
# MASTER_MODEL = 'guazzone'
# MASTER_MODEL = 'shi'
# MASTER_MODEL = 'first_fit'
# MASTER_MODEL = 'worst_fit'
# MASTER_MODEL = 'best_fit'

MAIN_MODEL_MAX_PMS = 100
PM_MANAGER_MAX_VMS = 100
PM_MANAGER_MAX_PMS = 200

# Hard time limits
HARD_TIME_LIMIT_MAIN = TIME_STEP / 2
HARD_TIME_LIMIT_MINI = TIME_STEP / 2

# CPLEX parameters
EPGAP_MAIN = 0.02
EPGAP_MINI = 0.01
EPGAP_PM_MANAGER = 0.05
EPGAP_MIGRATION = 0.01

# Paths
BASE_PATH = ''
SIMULATION_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/simulation_input')
SIMULATION_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/simulation_output')
MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_input_main')
MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_output_main')
MINI_MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_input_mini')
MINI_MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_output_mini')
PM_MANAGER_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/pm_manager/input')
PM_MANAGER_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/pm_manager/output')
OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/simulation_output')
MIGRATION_SCHEDULE_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/migration_schedule')
LOGS_FOLDER_PATH = os.path.join(BASE_PATH, 'logs')

FLOW_CONTROL_PATH = os.path.join(BASE_PATH, 'model/flow_control.mod')
INITIAL_PMS_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, f'physical_machines_{WORKLOAD_NAME}.dat')
INITIAL_VMS_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, 'virtual_machines.dat')
VMS_TRACE_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, f'workload_files/{WORKLOAD_NAME}.json')
POWER_FUNCTION_FILE = os.path.join(MODEL_INPUT_FOLDER_PATH, 'power_consumption_complete.dat')
WEIGHTS_FILE = os.path.join(BASE_PATH, 'src/weights.py')
WORKLOAD_START_TIMES_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, 'workload_start_times.json')