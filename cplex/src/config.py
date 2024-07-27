import os

# Seed
USE_RANDOM_SEED = True 

# Paths
BASE_PATH = '/home/roberto/job/vm_allocator/cplex'
INITIAL_VMS_FILE = os.path.join(BASE_PATH, 'simulation/simulation_input/virtual_machines.dat')
INITIAL_PMS_FILE = os.path.join(BASE_PATH, 'simulation/simulation_input/physical_machines.dat')
OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/simulation_output')
MODEL_INPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_input')
MODEL_OUTPUT_FOLDER_PATH = os.path.join(BASE_PATH, 'simulation/model_output')
MAIN_MODEL_PATH = os.path.join(BASE_PATH, 'model/main.mod')

# Simulation parameters
TIME_STEP = 1.0  
NEW_VMS_PER_STEP = 2  # Number of new VMs to generate at each time step
NUM_TIME_STEPS = 20 # Number of time steps to simulate

