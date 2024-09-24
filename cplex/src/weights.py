from config import TIME_STEP

main_time_step = TIME_STEP  # in seconds
time_window = 20 * TIME_STEP  # in seconds

# Conversion factors
hr_to_s = 3.6 * 10**3  # hours to seconds
kWh_to_J = 3.6 * 10**6  # kilowatt-hours to joules
bytes_to_GB = 10**(-9)  # bytes to gigabytes


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
    'time': {  # in seconds
        'memory_dirty_rate': 0.1,  # GB of memory that gets dirty per second during live migration
        'network_bandwidth': 10.0,  # GB/s
        'resume_vm_on_target': 20.0 / 10**3,  # in seconds
    },
    'energy': {  
        'cpu_overhead': {
            'source': 0.015,
            'target': 0.017,
        },
        'concurrent': 0.016
    }
}

safety_margin = 0.7

w_load_cpu = 0.8 # How much the load of the CPU affects the energy consumption (compared to memory)
expected_runtime_factor = 0.9  # What is the expected real completion time of a task compared to the declared run time: run time / real completion time (allocation time + run time + eventual migration time)

step_window_for_online_prediction = 10
step_window_for_weights_accuracy = 30
