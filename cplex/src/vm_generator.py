import random

def generate_new_vms(active_vms, new_vms_per_step, existing_ids):
    for _ in range(new_vms_per_step):
        new_vm_id = generate_unique_id(existing_ids)
        new_vm = {
            'id': new_vm_id,
            'requested_cpu': random.choice([1, 2, 4, 8, 16]),
            'requested_memory': random.choice([4, 8, 16, 32, 64]),
            'current_execution_time': 0.0,
            'total_execution_time': round(random.uniform(1.0, 10.0), 1),
            'running_on_pm': -1,  # New VM is not running on any physical machine initially
            'expected_profit': round(random.uniform(100.0, 1000.0), 2)
        }
        active_vms.append(new_vm)
        existing_ids.add(new_vm_id)

def generate_unique_id(existing_ids):
    new_id = max(existing_ids) + 1 if existing_ids else 0
    while new_id in existing_ids:
        new_id += 1
    return new_id
