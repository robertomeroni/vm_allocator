# Conversion factors
hr_to_s = 3.6 * 10**3  # hours to seconds
kWh_to_J = 3.6 * 10**6  # kilowatt-hours to joules

EPSILON = 0.00001

pue = 1.5  # Power Usage Effectiveness

price = {
    "cpu": 0.025 / hr_to_s,  # Price per core, converted from $/vCPUh to $/vCPUs
    "memory": 0.003 / hr_to_s,  # Price per GB, converted from $/GBh to $/GBs
    "energy": 0.1 / kWh_to_J,  # Cost, converted from $/kWh to $/J
}

migration = {
    "time": {  # in seconds
        "memory_dirty_rate": 0.1,  # GB of memory that gets dirty per second during live migration
        "network_bandwidth": 1.0,  # GB/s
        "resume_vm_on_target": 200.0 / 10**3,  # in seconds
    },
    "energy": {  # in J
        "coefficient": 512,
        "constant": 20.165,
    },
}

w_load_cpu = 0.8  # How much the load of the CPU affects the energy consumption (compared to memory)
