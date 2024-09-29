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
USE_WORKLOAD_PREDICTOR = False

# WORKLOAD_NAME = 'KIT-FH2-2016'
# WORKLOAD_NAME = 'UniLu-Gaia-2014'
# WORKLOAD_NAME = 'METACENTRUM-2009'
# WORKLOAD_NAME = 'PIK-IPLEX-2009'
# WORKLOAD_NAME = 'LLNL-Thunder-2007'
WORKLOAD_NAME = 'Intel-NetbatchA-2012'

# Simulation parameters
STARTING_STEP = 1
TIME_STEP = 250  # Time step in seconds
NUM_TIME_STEPS = 1500 # Number of time steps to simulate
NEW_VMS_PER_STEP = 2  # Expected number of new VMs to generate at each time step

# Models to use
# MASTER_MODEL = 'main'
# MASTER_MODEL = 'mini'
# MASTER_MODEL = 'mixed'
# MASTER_MODEL = 'guazzone'
# MASTER_MODEL = 'shi'
MASTER_MODEL = 'best_fit'

MAIN_MODEL_PERIOD = 4  # The main model will be run every MAIN_MODEL_PERIOD time steps
MINI_MODEL_PERIOD = 2  # The mini model will be run every MINI_MODEL_PERIOD time steps (when the main model is not running)

# Paths
BASE_PATH = ''
SIMULATION_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/simulation_input')
SIMULATION_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/simulation_output')
MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_input')
MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_output')
MINI_MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_input')
MINI_MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_output')
OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/simulation_output')
MIGRATION_SCHEDULE_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/migration_schedule')
LOGS_FOLDER_PATH = os.path.join(BASE_PATH, 'logs')
PREDICTORS_FOLDER_PATH = os.path.join(BASE_PATH, f'workload_predictor/{WORKLOAD_NAME}')

MAIN_MODEL_PATH = os.path.join(BASE_PATH, 'model/main.mod')
MINI_MODEL_PATH = os.path.join(BASE_PATH, 'model/mini_main.mod')
PREDICTOR_MODEL_PATH = os.path.join(PREDICTORS_FOLDER_PATH, 'models/random_forest.pkl')
INITIAL_PMS_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, f'physical_machines_{WORKLOAD_NAME}.dat')
INITIAL_VMS_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, 'virtual_machines.dat')
VMS_TRACE_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, f'workload_files/{WORKLOAD_NAME}.json')
POWER_FUNCTION_FILE = os.path.join(MODEL_INPUT_FOLDER_PATH, 'power_consumption_complete.dat')
WEIGHTS_FILE = os.path.join(BASE_PATH, 'src/weights.py')
WORKLOAD_START_TIMES_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, 'workload_start_times.json')
WORKLOAD_PREDICTION_MODEL = os.path.join(PREDICTORS_FOLDER_PATH, 'models/random_forest.pkl')
ARRIVALS_TRACKING_FILE = os.path.join(SIMULATION_OUTPUT_FOLDER_PATH, 'arrivals_tracking.json')
WORKLOAD_PREDICTION_FILE = os.path.join(SIMULATION_OUTPUT_FOLDER_PATH, 'workload_prediction.json')