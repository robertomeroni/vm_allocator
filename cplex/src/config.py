import os

# General
USE_RANDOM_SEED = True
SAVE_LOGS = False

# Paths
BASE_PATH = ''
WEIGHTS_FILE = os.path.join(BASE_PATH, 'src/weights.py')
INITIAL_VMS_FILE = os.path.join(BASE_PATH, 'simulation/simulation_input/virtual_machines.dat')
INITIAL_PMS_FILE = os.path.join(BASE_PATH, 'simulation/simulation_input/physical_machines.dat')
POWER_FUNCTION_FILE = os.path.join(BASE_PATH, 'simulation/model_input/power_consumption.dat')
OVERLOAD_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/overload')
OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/simulation_output')
LOGS_FOLDER_PATH = os.path.join(BASE_PATH, 'logs')

MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_input')
MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_output')
MAIN_MODEL_PATH = os.path.join(BASE_PATH, 'model/main.mod')
MINI_MODEL_PATH = os.path.join(BASE_PATH, 'model/mini_main.mod')

MINI_MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_input')
MINI_MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_output')

# Simulation parameters
TIME_STEP = 30  # Time step in seconds
NEW_VMS_PER_STEP = 3  # Expected number of new VMs to generate at each time step
NUM_TIME_STEPS = 30 # Number of time steps to simulate

