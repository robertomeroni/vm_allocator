from config import TIME_STEP

main_time_step = TIME_STEP  # in seconds
time_window = 10 * TIME_STEP  # in seconds

# Conversion factors
hr_to_s = 3.6 * 10**3  # hours to seconds
kWh_to_J = 3.6 * 10**6  # kilowatt-hours to joules

# Weights
network_bandwidth = 100.0  # GB/s

pue = 1.5  # Power Usage Effectiveness

price = {
    'cpu': 0.025 / hr_to_s,  # Price per core, converted from $/vCPUh to $/vCPUs
    'memory': 0.003 / hr_to_s  # Price per GB, converted from $/GBh to $/GBs
}

energy = {
    'cost': 0.1 / kWh_to_J,  # Cost, converted from $/kWh to $/J
    'limit': 1000000.0  # Energy limit
}

migration = {
    'time': {  # in seconds, offset + coefficient * memory_size
        'offset': 0.0,  
        'coefficient': 1 / network_bandwidth  
    },
    'energy': {  # in Joules, offset + coefficient * memory_size
        'offset': 20165,  
        'coefficient': 512.0
    },
    'penalty': 0.1  
}

w_load_cpu = 0.8 # How much the load of the CPU affects the energy consumption (compared to memory)

