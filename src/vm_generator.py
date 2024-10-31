import numpy as np
from weights import price, migration

def generate_new_vms(new_vms_per_step, existing_ids):
    num_new_vms = np.random.poisson(lam=new_vms_per_step)
    new_vms = []  # List to store new VMs

    for _ in range(num_new_vms):
        new_vm_id = generate_unique_id(existing_ids)
        requested_cpu = np.random.choice([1, 2, 4, 8, 16])
        requested_memory = np.random.choice([4, 8, 16, 32, 64])
        run_total_time = np.random.uniform(30.0, 600.0)

        revenue = (requested_cpu * price['cpu'] + requested_memory * price['memory']) * run_total_time

        migration_first_round_time = requested_memory / migration['time']['network_bandwidth']
        migration_down_time = migration['time']['resume_vm_on_target'] + (migration_first_round_time * migration['time']['memory_dirty_rate']) / migration['time']['network_bandwidth']
        migration_total_time = migration_first_round_time + migration_down_time

        new_vm = {
            'id': new_vm_id,
            'requested': {
                'cpu': requested_cpu,
                'memory': requested_memory
            },
            'allocation': {
                'current_time': 0.0,
                'total_time': round(np.random.uniform(1.0, 10.0), 0),
                'pm': -1  # New VM is not running on any physical machine initially
            },
            'run': {
                'current_time': 0.0,
                'total_time': round(run_total_time, 0),
                'pm': -1
            },
            'migration': {
                'current_time': 0.0,
                'total_time': round(migration_total_time, 5),
                'down_time': round(migration_down_time, 5),
                'from_pm': -1,
                'to_pm': -1
            },
            'revenue': round(revenue, 5)  # Calculated revenue based on requested resources
        }
        existing_ids.add(new_vm_id)
        new_vms.append(new_vm)  # Add the new VM to the list

    return new_vms  # Return the list of new VMs

def generate_unique_id(existing_ids):
    new_id = max(existing_ids, default=-1) + 1
    while new_id in existing_ids:
        new_id += 1
    return new_id
