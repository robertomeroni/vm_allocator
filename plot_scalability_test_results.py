#!/usr/bin/env python3

import re
import matplotlib.pyplot as plt
import sys

def parse_report_file(filename):
    """
    Reads the report file and returns a structure of data in the form:
    {
      'master_model_name1': [(pms_1, runtime_1), (pms_2, runtime_2), ...],
      'master_model_name2': [...],
      ...
    }
    """
    # Regex patterns to match fields of interest
    pms_pattern = re.compile(r'PMS\s*=\s*(\d+)')
    master_model_pattern     = re.compile(r'MASTER_MODEL\s*=\s*(\w+)')
    allocation_runtime_pattern = re.compile(r'Allocation Runtime:\s*([\d\.]+)')
    
    data = {}
    
    current_master_model = None
    current_pms = None
    
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # Check if there's a pms value in this line
            pms_match = pms_pattern.search(line)
            if pms_match:
                current_pms = float(pms_match.group(1))
            
            # Check for MASTER_MODEL
            master_model_match = master_model_pattern.search(line)
            if master_model_match:
                current_master_model = master_model_match.group(1)
            
            # Check for total runtime
            runtime_match = allocation_runtime_pattern.search(line)
            if runtime_match and current_master_model is not None and current_pms is not None:
                runtime = float(runtime_match.group(1))
                
                # Initialize dictionary list if not existing
                if current_master_model not in data:
                    data[current_master_model] = []
                
                # Store the pair
                data[current_master_model].append((current_pms, runtime))
                
                # Reset these so we only record once per block
                current_master_model = None
                current_pms = None
    return data

def plot_data(data):
    """
    Plots a line for each MASTER_MODEL, 
    where X = PMs, Y = Total Model Runtime.
    """
    plt.figure(figsize=(24, 18))
    
    line_styles = ['-', '--', '-.', ':']
    markers = ['o', 's', 'D', '^']
    
    for i, (master_model, points) in enumerate(data.items()):
        # Sort points by X just to ensure a clean line plot
        points.sort(key=lambda x: x[0])
        
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        
        # Print x and y values for each algorithm
        print(f"Algorithm: {master_model}")
        print(f"X values (PMs): {xs}")
        print(f"Y values (Total Model Runtime): {ys}\n")
        
        # Use different line styles and markers for each model
        plt.plot(xs, ys, linestyle=line_styles[i % len(line_styles)], 
                 marker=markers[i % len(markers)], label=master_model)
    
    plt.xlabel('Datacenter size')
    plt.ylabel('Total Model Runtime (seconds)')
    plt.title('Total Model Runtime vs PMs by MASTER_MODEL')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def main():
    # Replace 'results.txt' with the path to your file 
    # or take from command-line argument
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <report_file>")
        sys.exit(1)
    
    filename = sys.argv[1]
    data = parse_report_file(filename)
    plot_data(data)

if __name__ == '__main__':
    main()
