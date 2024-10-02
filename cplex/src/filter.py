def filter_full_physical_machines(physical_machines):
    filtered_physical_machines = []
    for pm in physical_machines:
        if pm['s']['load']['cpu'] < 1 and pm['s']['load']['memory'] < 1:
            filtered_physical_machines.append(pm)
    return filtered_physical_machines
