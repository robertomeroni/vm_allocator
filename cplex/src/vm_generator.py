import numpy as np
from weights import price, migration

def generate_new_vms(active_vms, new_vms_per_step, existing_ids):
    num_new_vms = np.random.poisson(lam=new_vms_per_step)

    for _ in range(num_new_vms):
        new_vm_id = generate_unique_id(existing_ids)
        requested_cpu = np.random.choice([1, 2, 4, 8, 16])
        requested_memory = np.random.choice([4, 8, 16, 32, 64])
        run_total_time = np.random.uniform(30.0, 600.0)

        profit = (requested_cpu * price['cpu'] + requested_memory * price['memory']) * run_total_time

        migration_total_time = migration['time']['offset'] + migration['time']['coefficient'] * requested_memory

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
                'from_pm': -1,
                'to_pm': -1
            },
            'group': np.random.randint(1, 10),  
            'profit': round(profit, 5)  # Calculated profit based on requested resources
        }
        active_vms.append(new_vm)
        existing_ids.add(new_vm_id)

def generate_unique_id(existing_ids):
    new_id = max(existing_ids) + 1 if existing_ids else 0
    while new_id in existing_ids:
        new_id += 1
    return new_id
