import json
import math
import os
import re

import numpy as np
import pandas as pd
from colorama import Style

from config import (
    MODEL_INPUT_FOLDER_PATH,
    PM_DATABASE_FILE,
    SPECIFIC_POWER_FUNCTION_FILE,
)
from weights import migration, price, pue, w_load_cpu

try:
    profile  # type: ignore
except NameError:

    def profile(func):
        return func


# Check if NO_COLOR environment variable is set
NO_COLOR = os.environ.get("NO_COLOR", "0") == "1"


def load_new_vms(vms_trace_file_path):
    if not os.path.exists(vms_trace_file_path):
        raise ValueError(
            f"File {vms_trace_file_path} not found. Please provide a file with real VMs or set REAL_DATA to False."
        )
    with open(vms_trace_file_path, "r") as file:
        real_vms = json.load(file)  # Load VMs from JSON file

    # Convert real_vms to the format expected by the simulation
    new_vms = []
    for vm in real_vms:
        requested_cpu = math.ceil(vm["requested_processors"])
        requested_memory = math.ceil(vm["requested_memory"])
        run_total_time = vm["run_time"]
        revenue = (
            requested_cpu * price["cpu"] + requested_memory * price["memory"]
        ) * run_total_time
        migration_first_round_time = (
            requested_memory / migration["time"]["network_bandwidth"]
        )
        migration_down_time = (
            migration["time"]["resume_vm_on_target"]
            + migration_first_round_time
            * migration["time"]["memory_dirty_rate"]
            / migration["time"]["network_bandwidth"]
        )
        migration_total_time = migration_first_round_time + migration_down_time
        migration_energy = (
            migration["energy"]["coefficient"] * requested_memory
            + migration["energy"]["constant"]
        )

        new_vm = {
            "id": vm["job_number"],
            "requested": {"cpu": requested_cpu, "memory": requested_memory},
            "allocation": {
                "current_time": 0.0,
                "total_time": min(vm["run_time"] * 0.001, 0.9),
                "pm": -1,
            },
            "run": {"current_time": 0.0, "total_time": vm["run_time"], "pm": -1},
            "migration": {
                "current_time": 0.0,
                "total_time": migration_total_time,
                "down_time": migration_down_time,
                "from_pm": -1,
                "to_pm": -1,
                "energy": migration_energy,
            },
            "arrival_time": vm["submit_time"],
            "arrival_step": -1,
            "revenue": revenue,
        }
        new_vms.append(new_vm)

    sorted_vms = sorted(new_vms, key=lambda x: x["arrival_time"])

    return sorted_vms


def load_virtual_machines(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as file:
        data = file.read()
    try:
        vm_lines = (
            data.split("virtual_machines = {")[1].split("};")[0].strip().split("\n")
        )
    except IndexError:
        print()
        raise ValueError(
            f"Error in loading virtual machines: Check the format of {file_path}"
        )

    vms = {}
    for line in vm_lines:
        line = line.strip().strip("<").strip(">")
        parts = [part.strip().strip("<").strip(">") for part in line.split(",")]
        vm = {
            "id": int(parts[0]),
            "requested": {"cpu": int(parts[1]), "memory": int(parts[2])},
            "allocation": {
                "current_time": float(parts[3]),
                "total_time": float(parts[4]),
                "pm": int(parts[5]),
            },
            "run": {
                "current_time": float(parts[6]),
                "total_time": float(parts[7]),
                "pm": int(parts[8]),
            },
            "migration": {
                "current_time": float(parts[9]),
                "total_time": float(parts[10]),
                "down_time": float(parts[11]),
                "from_pm": int(parts[12]),
                "to_pm": int(parts[13]),
                "energy": float(parts[14]),
            },
        }
        vms[vm["id"]] = vm  # Store VM in dictionary keyed by ID
    return vms


def load_physical_machines(file_path):
    if not os.path.exists(file_path):
        print(
            f"File {file_path} not found. Please provide an initial Physical Machines file."
        )
        return {}

    with open(file_path, "r") as file:
        data = file.read()

    try:
        pm_section = (
            data.split("physical_machines = {")[1].split("};")[0].strip().split("\n")
        )
    except IndexError:
        print()
        raise ValueError(
            f"Error in loading physical machines: Check the format of {file_path}"
        )

    pms = {}
    for line in pm_section:
        line = line.strip().strip("<").strip(">")  # Clean the line
        parts = line.split(",")  # Split by commas at the top level

        # Extract and clean components
        pm_id = int(parts[0].strip())  # ID
        capacity = {
            "cpu": int(parts[1].strip().strip("<")),
            "memory": int(parts[2].strip().strip(">")),
        }
        time_to_turn_on = float(parts[3].strip("<> \n"))
        time_to_turn_off = float(parts[4].strip())
        load = {
            "cpu": float(parts[5].strip().strip("<")),
            "memory": float(parts[6].strip().strip(">")),
        }
        state = int(parts[7].strip(">"))
        pm_type = int(parts[8].strip().strip(">"))  # Type (last part)

        # Build the PM dictionary
        pm = {
            "id": pm_id,
            "capacity": capacity,
            "s": {
                "time_to_turn_on": time_to_turn_on,
                "time_to_turn_off": time_to_turn_off,
                "load": load,
                "state": state,
            },
            "type": pm_type,
        }
        pms[pm_id] = pm  # Store PM in dictionary keyed by ID

    return pms


def load_pm_database(composition, shape="average"):
    pm_database = {}
    power_function_database = {}
    speed_function_database = {}
    specific_power_function_database = {}

    # Load the CSV file
    df = pd.read_csv(PM_DATABASE_FILE, encoding="ISO-8859-1")

    for index, row in df.iterrows():
        pm_database[index] = {
            "capacity": {
                "cpu": math.ceil(row["# Cores"]),
                "memory": math.ceil(row["Memory (GB)"]),
            },
            "s": {
                "time_to_turn_on": 5 + 0.2 * (row["# Cores"] + row["Memory (GB)"]),
                "time_to_turn_off": 2 + 0.05 * (row["# Cores"] + row["Memory (GB)"]),
                "load": {"cpu": 0.0, "memory": 0.0},
                "state": 0,
            },
            "type": index,
        }

        if composition == "heterogeneous":
            power_function_database[index] = {
                "0.0": row["Average watts @ active idle"],
                "0.1": row["Average watts @ 10% of target load"],
                "0.2": row["Average watts @ 20% of target load"],
                "0.3": row["Average watts @ 30% of target load"],
                "0.4": row["Average watts @ 40% of target load"],
                "0.5": row["Average watts @ 50% of target load"],
                "0.6": row["Average watts @ 60% of target load"],
                "0.7": row["Average watts @ 70% of target load"],
                "0.8": row["Average watts @ 80% of target load"],
                "0.9": row["Average watts @ 90% of target load"],
                "1.0": row["Average watts @ 100% of target load"],
            }

            speed_function_database[index] = {
                "0.0": row["speed @ 10% of target load"],
                "0.1": row["speed @ 10% of target load"],
                "0.2": row["speed @ 20% of target load"],
                "0.3": row["speed @ 30% of target load"],
                "0.4": row["speed @ 40% of target load"],
                "0.5": row["speed @ 50% of target load"],
                "0.6": row["speed @ 60% of target load"],
                "0.7": row["speed @ 70% of target load"],
                "0.8": row["speed @ 80% of target load"],
                "0.9": row["speed @ 90% of target load"],
                "1.0": row["speed @ 100% of target load"],
            }

        elif composition == "almost_heterogeneous":
            if shape == "average":
                power_function_database[index] = {
                    "0.0": row["Average watts @ active idle"],
                    "0.1": 1.945 * row["Average watts @ active idle"],
                    "0.2": 2.121 * row["Average watts @ active idle"],
                    "0.3": 2.336 * row["Average watts @ active idle"],
                    "0.4": 2.549 * row["Average watts @ active idle"],
                    "0.5": 2.899 * row["Average watts @ active idle"],
                    "0.6": 3.133 * row["Average watts @ active idle"],
                    "0.7": 3.405 * row["Average watts @ active idle"],
                    "0.8": 3.677 * row["Average watts @ active idle"],
                    "0.9": 3.911 * row["Average watts @ active idle"],
                    "1.0": 4.165 * row["Average watts @ active idle"],
                }

            elif shape == "linear":
                power_function_database[index] = {
                    "0.0": row["Average watts @ active idle"],
                    "0.1": 1.0261 * row["Average watts @ active idle"],
                    "0.2": 1.0557 * row["Average watts @ active idle"],
                    "0.3": 1.0835 * row["Average watts @ active idle"],
                    "0.4": 1.1113 * row["Average watts @ active idle"],
                    "0.5": 1.1409 * row["Average watts @ active idle"],
                    "0.6": 1.1704 * row["Average watts @ active idle"],
                    "0.7": 1.2000 * row["Average watts @ active idle"],
                    "0.8": 1.2243 * row["Average watts @ active idle"],
                    "0.9": 1.2452 * row["Average watts @ active idle"],
                    "1.0": 1.2739 * row["Average watts @ active idle"],
                }

            elif shape == "exponential":
                power_function_database[index] = {
                    "0.0": row["Average watts @ active idle"],
                    "0.1": 2.8280 * row["Average watts @ active idle"],
                    "0.2": 3.3491 * row["Average watts @ active idle"],
                    "0.3": 3.8715 * row["Average watts @ active idle"],
                    "0.4": 4.4164 * row["Average watts @ active idle"],
                    "0.5": 5.0362 * row["Average watts @ active idle"],
                    "0.6": 5.9052 * row["Average watts @ active idle"],
                    "0.7": 6.7985 * row["Average watts @ active idle"],
                    "0.8": 8.2114 * row["Average watts @ active idle"],
                    "0.9": 9.8769 * row["Average watts @ active idle"],
                    "1.0": 11.2660 * row["Average watts @ active idle"],
                }

            speed_function_database[index] = {
                "0.0": row["speed @ 10% of target load"],
                "0.1": row["speed @ 10% of target load"],
                "0.2": 0.9992 * row["speed @ 10% of target load"],
                "0.3": 1.0033 * row["speed @ 10% of target load"],
                "0.4": 1.0006 * row["speed @ 10% of target load"],
                "0.5": 1.0002 * row["speed @ 10% of target load"],
                "0.6": 0.9993 * row["speed @ 10% of target load"],
                "0.7": 1.0015 * row["speed @ 10% of target load"],
                "0.8": 0.9999 * row["speed @ 10% of target load"],
                "0.9": 0.9981 * row["speed @ 10% of target load"],
                "1.0": 0.9962 * row["speed @ 10% of target load"],
            }

        elif composition == "almost_homogeneous" or composition == "homogeneous":
            if index == 0:
                power_function_database[index] = {
                    "0.0": row["Average watts @ active idle"],
                    "0.1": row["Average watts @ 10% of target load"],
                    "0.2": row["Average watts @ 20% of target load"],
                    "0.3": row["Average watts @ 30% of target load"],
                    "0.4": row["Average watts @ 40% of target load"],
                    "0.5": row["Average watts @ 50% of target load"],
                    "0.6": row["Average watts @ 60% of target load"],
                    "0.7": row["Average watts @ 70% of target load"],
                    "0.8": row["Average watts @ 80% of target load"],
                    "0.9": row["Average watts @ 90% of target load"],
                    "1.0": row["Average watts @ 100% of target load"],
                }

                speed_function_database[index] = {
                    "0.0": row["speed @ 10% of target load"],
                    "0.1": row["speed @ 10% of target load"],
                    "0.2": row["speed @ 20% of target load"],
                    "0.3": row["speed @ 30% of target load"],
                    "0.4": row["speed @ 40% of target load"],
                    "0.5": row["speed @ 50% of target load"],
                    "0.6": row["speed @ 60% of target load"],
                    "0.7": row["speed @ 70% of target load"],
                    "0.8": row["speed @ 80% of target load"],
                    "0.9": row["speed @ 90% of target load"],
                    "1.0": row["speed @ 100% of target load"],
                }

            else:
                power_function_database[index] = power_function_database[0]
                speed_function_database[index] = speed_function_database[0]

        specific_power_function_database[index] = {
            "0.0": power_function_database[index]["0.0"]
            / speed_function_database[index]["0.0"],
            "0.1": power_function_database[index]["0.1"]
            / speed_function_database[index]["0.1"],
            "0.2": power_function_database[index]["0.2"]
            / speed_function_database[index]["0.2"],
            "0.3": power_function_database[index]["0.3"]
            / speed_function_database[index]["0.3"],
            "0.4": power_function_database[index]["0.4"]
            / speed_function_database[index]["0.4"],
            "0.5": power_function_database[index]["0.5"]
            / speed_function_database[index]["0.5"],
            "0.6": power_function_database[index]["0.6"]
            / speed_function_database[index]["0.6"],
            "0.7": power_function_database[index]["0.7"]
            / speed_function_database[index]["0.7"],
            "0.8": power_function_database[index]["0.8"]
            / speed_function_database[index]["0.8"],
            "0.9": power_function_database[index]["0.9"]
            / speed_function_database[index]["0.9"],
            "1.0": power_function_database[index]["1.0"]
            / speed_function_database[index]["1.0"],
        }

    return (
        pm_database,
        power_function_database,
        speed_function_database,
        specific_power_function_database,
    )


def load_configuration(folder_path, epgap):
    weights_data = f"""
epgap = {epgap};

price = <{price['cpu']}, {price['memory']}, {price['energy']}>;

PUE = {pue};

w_load_cpu = {w_load_cpu};
"""

    # Ensure the model input folder exists
    os.makedirs(folder_path, exist_ok=True)

    # Define the path to the weights.dat file
    weights_file_path = os.path.join(folder_path, "weights.dat")

    # Write the configuration to the weights.dat file
    with open(weights_file_path, "w") as file:
        file.write(weights_data)


def convert_to_serializable(obj):
    """Recursively convert numpy types to native Python types."""
    if isinstance(obj, np.int64) or isinstance(obj, np.int32):
        return int(obj)
    elif isinstance(obj, np.float64) or isinstance(obj, np.float32):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_to_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    return obj


def save_vm_sets(active_vms, terminated_vms, step, output_folder_path):
    active_file_path = os.path.join(output_folder_path, f"active_vms_t{step}.json")
    terminated_file_path = os.path.join(
        output_folder_path, f"terminated_vms_t{step}.json"
    )

    # Convert data to serializable format before saving
    active_vms_serializable = convert_to_serializable(active_vms)
    terminated_vms_serializable = convert_to_serializable(terminated_vms)

    with open(active_file_path, "w") as file:
        json.dump(active_vms_serializable, file, indent=4)
    with open(terminated_file_path, "w") as file:
        json.dump(terminated_vms_serializable, file, indent=4)


def save_pm_sets(pms, step, output_folder_path):
    file_path = os.path.join(output_folder_path, f"pms_t{step}.json")

    # Convert data to serializable format before saving
    pms_serializable = convert_to_serializable(pms)

    with open(file_path, "w") as file:
        json.dump(pms_serializable, file, indent=4)


def save_specific_power_function(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return

    with open(file_path, "r") as file:
        data = file.read()

    try:
        specific_power_function_section = (
            data.split("specific_power_function = [")[1].split("];")[0].strip() + "];"
        )
        nb_points_section = data.split("nb_points = ")[1].split(";")[0].strip() + ";"
    except IndexError:
        print()
        raise ValueError(
            f"Error in loading power function or nb_points: Check the format of {file_path}"
        )

    with open(SPECIFIC_POWER_FUNCTION_FILE, "w") as file:
        file.write("nb_points = " + nb_points_section + "\n\n")
        file.write("specific_power_function = [\n")
        file.write(specific_power_function_section)
        file.write("\n")


def convert_specific_power_function_to_model_input_format(
    pms, specific_power_function_database, nb_points
):
    output_content = f"\n\nnb_points = {nb_points};\n\nspecific_power_function = [\n"

    for pm in pms.values():
        specific_power_function_dict = specific_power_function_database[pm["type"]]
        formatted_values = ", ".join(
            f"<{x}, {value}>" for x, value in specific_power_function_dict.items()
        )
        output_content += f"  [{formatted_values}],\n"

    output_content = output_content.rstrip(",\n") + "\n];\n"
    return output_content


def convert_vms_to_model_input_format(vms):
    legend = "// <id, requested (cpu, memory), allocation (current_time, total_time, pm), run (current_time, total_time, pm), migration (current_time, total_time, down_time, from_pm, to_pm, energy)>\n"
    formatted_vms = legend + "\nvirtual_machines = {\n"
    for vm in vms.values():
        formatted_vms += f"  <{vm['id']}, <{vm['requested']['cpu']}, {vm['requested']['memory']}>, <{vm['allocation']['current_time']}, {vm['allocation']['total_time']}, {vm['allocation']['pm']}>, <{vm['run']['current_time']}, {vm['run']['total_time']}, {vm['run']['pm']}>, <{vm['migration']['current_time']}, {vm['migration']['total_time']}, {vm['migration']['down_time']}, {vm['migration']['from_pm']}, {vm['migration']['to_pm']}, {vm['migration']['energy']}>>,\n"
    formatted_vms = formatted_vms.rstrip(",\n") + "\n};"
    return formatted_vms


def convert_pms_to_model_input_format(pms):
    legend = "// <id, capacity (cpu, memory), s (time_to_turn_on, time_to_turn_off, load (cpu_load, memory_load), state), type>\n"
    formatted_pms = legend + "\nphysical_machines = {\n"
    for pm in pms.values():
        formatted_pms += f"  <{pm['id']}, <{pm['capacity']['cpu']}, {pm['capacity']['memory']}>, <{pm['s']['time_to_turn_on']}, {pm['s']['time_to_turn_off']}, <{pm['s']['load']['cpu']}, {pm['s']['load']['memory']}>, {pm['s']['state']}>, {pm['type']}>, \n"
    formatted_pms = formatted_pms.rstrip(",\n") + "\n};"
    return formatted_pms


def save_model_input_format(
    vms, pms, step, model_input_folder_path, specific_power_function_database, nb_points
):
    # Ensure the directory exists
    os.makedirs(model_input_folder_path, exist_ok=True)

    # Construct file paths
    base_filename = f"_t{step}.dat"
    vm_filename = "virtual_machines" + base_filename
    pm_filename = "physical_machines" + base_filename
    vm_model_input_file_path = os.path.join(model_input_folder_path, vm_filename)
    pm_model_input_file_path = os.path.join(model_input_folder_path, pm_filename)

    # Convert data to the required format
    formatted_vms = convert_vms_to_model_input_format(vms)
    formatted_pms = convert_pms_to_model_input_format(pms)
    formatted_specific_power_function = (
        convert_specific_power_function_to_model_input_format(
            pms, specific_power_function_database, nb_points
        )
    )

    # Write formatted VMs to file
    with open(vm_model_input_file_path, "w", encoding="utf-8") as vm_file:
        vm_file.write(formatted_vms)

    # Write formatted PMs and power function to file
    with open(pm_model_input_file_path, "w", encoding="utf-8") as pm_file:
        pm_file.write(formatted_pms)
        pm_file.write(formatted_specific_power_function)

    return vm_model_input_file_path, pm_model_input_file_path


def parse_opl_output(output):
    parsed_data = {}

    patterns = {
        "has_to_be_on": re.compile(r"has_to_be_on = \[(.*?)\];", re.DOTALL),
        "new_allocation": re.compile(r"new_allocation = \[\[(.*?)\]\];", re.DOTALL),
        "is_migrating_from": re.compile(
            r"is_migrating_from = \[\[(.*?)\]\];", re.DOTALL
        ),
        "vm_ids": re.compile(r"Virtual Machines IDs: \[(.*?)\]"),
        "pm_ids": re.compile(r"Physical Machines IDs: \[(.*?)\]"),
        "is_allocation": re.compile(r"is_allocation = \[(.*?)\];", re.DOTALL),
        "is_migration": re.compile(r"is_migration = \[(.*?)\];", re.DOTALL),
    }

    for key, pattern in patterns.items():
        match = pattern.search(output)
        if match:
            if key in ["new_allocation"] or key in ["is_migrating_from"]:
                parsed_data[key] = parse_matrix(match.group(1))
            else:
                parsed_data[key] = [
                    int(num) if num.isdigit() else float(num)
                    for num in match.group(1).strip().split()
                ]

    return parsed_data


def get_opl_return_code(output):
    pattern = r"main returns\s+([-+]?\d+)"

    # Search for the pattern in the input string
    match = re.search(pattern, output)

    if match:
        return int(match.group(1))
    else:
        return None


def is_opl_output_valid(output, return_code):
    if return_code != 0:
        return False

    output_lower = output.lower()
    time_limit_exceeded_keyword = "time limit exceeded"
    no_solution_keyword = "no solution"

    if (
        time_limit_exceeded_keyword in output_lower
        or no_solution_keyword in output_lower
    ):
        return False
    return True


def parse_matrix(matrix_str):
    return [
        [int(num) if num.isdigit() else float(num) for num in row.strip().split()]
        for row in matrix_str.strip().split("]\n             [")
    ]


# Define a function to apply color only if colors are enabled
def color_text(text, color):
    if NO_COLOR:
        return text
    return f"{color}{text}{Style.RESET_ALL}"


def evaluate_piecewise_linear_function(piecewise_function, x_value):
    """
    Evaluate a piecewise linear function at a given x_value.
    """
    if not isinstance(x_value, (int, float)):
        raise TypeError("Input x must be a numeric type.")

    if not 0.0 <= x_value <= 1.0:
        raise ValueError(f"x = {x_value} must be between 0.0 and 1.0 inclusive.")

    x_points = list(piecewise_function.keys())
    y_points = [piecewise_function[xi] for xi in x_points]

    y = np.interp(x_value, x_points, y_points)

    return y


def round_down(value):
    return math.floor(value * 1000000) / 1000000


def clean_up_model_input_files():
    try:
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, "virtual_machines.dat"))
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, "physical_machines.dat"))
    except FileNotFoundError:
        pass
