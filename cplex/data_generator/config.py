# Configuration for Physical Machines
pm_config = {
    'cpu_capacity': [4, 8, 16, 32, 64, 128, 256],         # Available CPU capacities in cores
    'memory_capacity': [16, 32, 64, 128, 256, 512],   # Available memory capacities in GB
    'speed_range': (0.2, 5.0),              # Speed range for the machines 
    'time_to_turn_on_range': (30.0, 180.0), # Time to turn on range in seconds
    'time_to_turn_off_range': (15.0, 90.0), # Time to turn off range in seconds
    'state_percentage': 50,                  # Percentage of physical machines that are ON initially
    'latency_range': (0.1, 0.5)             # Range of latencies between machines in milliseconds
}

# Configuration for Virtual Machines
vm_config = {
    'requested_cpu': [1, 2, 4, 8],          # Requested CPU capacities in cores
    'requested_memory': [2, 4, 8, 16],      # Requested memory capacities in GB
    'allocation_time_range': (1.0, 3.0),    # Range for allocation time in seconds
    'execution_time_range': (2.0, 6.0),     # Range for execution time in seconds
}

# Configuration for Network
network_config = {
    'network_bandwidth': 10.0  # Network bandwidth for migration time calculation in GB/s
}

# Default Values for the Number of Machines
default_values = {
    'num_physical_machines': 10,            # Default number of physical machines
    'num_virtual_machines': 20,             # Default number of virtual machines
    'running_percentage': 0                # Percentage of VMs that are running at the beginning
}

# Data Folder Path
data_folder_path = 'model/data'




# Convenience Aliases for Easy Access
pm_cpu_capacity = pm_config['cpu_capacity']
pm_memory_capacity = pm_config['memory_capacity']
pm_speed_range = pm_config['speed_range']
pm_time_to_turn_on_range = pm_config['time_to_turn_on_range']
pm_time_to_turn_off_range = pm_config['time_to_turn_off_range']
state_percentage = pm_config['state_percentage']
latency_range = pm_config['latency_range']

vm_requested_cpu = vm_config['requested_cpu']
vm_requested_memory = vm_config['requested_memory']
allocation_time_range = vm_config['allocation_time_range']
execution_time_range = vm_config['execution_time_range']

network_bandwidth = network_config['network_bandwidth']

default_num_physical_machines = default_values['num_physical_machines']
default_num_virtual_machines = default_values['num_virtual_machines']
running_percentage = default_values['running_percentage']
