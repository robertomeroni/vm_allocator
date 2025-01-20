#!/usr/bin/env python3

import re
import matplotlib.pyplot as plt
import sys

def parse_report_file(filename):
    """
    Reads the report file and returns a structure of data in the form:
    {
      'algorithm_name1': [(pms_1, runtime_1), (pms_2, runtime_2), ...],
      'algorithm_name2': [...],
      ...
    }
    """
    # Regex patterns to match fields of interest
    pms_pattern = re.compile(r'PMS\s*=\s*(\d+)')
    algorithm_pattern     = re.compile(r'ALGORITHM\s*=\s*(\w+)')
    allocation_runtime_pattern = re.compile(r'Allocation Runtime:\s*([\d\.]+)')
    
    data = {}
    
    current_algorithm = None
    current_pms = None
    
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # Check if there's a pms value in this line
            pms_match = pms_pattern.search(line)
            if pms_match:
                current_pms = float(pms_match.group(1))
            
            # Check for ALGORITHM
            algorithm_match = algorithm_pattern.search(line)
            if algorithm_match:
                current_algorithm = algorithm_match.group(1)
            
            # Check for total runtime
            runtime_match = allocation_runtime_pattern.search(line)
            if runtime_match and current_algorithm is not None and current_pms is not None:
                runtime = float(runtime_match.group(1))
                
                # Initialize dictionary list if not existing
                if current_algorithm not in data:
                    data[current_algorithm] = []
                
                # Store the pair
                data[current_algorithm].append((current_pms, runtime))
                
                # Reset these so we only record once per block
                current_algorithm = None
                current_pms = None
    return data

def plot_data(data):
    """
    Plots a line for each ALGORITHM, 
    where X = PMs, Y = Total Algorithm Runtime.
    """
    plt.figure(figsize=(24, 18))
    
    line_styles = ['-', '--', '-.', ':']
    markers = ['o', 's', 'D', '^']
    
    for i, (algorithm, points) in enumerate(data.items()):
        # Sort points by X just to ensure a clean line plot
        points.sort(key=lambda x: x[0])
        
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        
        # Print x and y values for each algorithm
        print(f"Algorithm: {algorithm}")
        print(f"X values (PMs): {xs}")
        print(f"Y values (Total Algorithm Runtime): {ys}\n")
        
        # Use different line styles and markers for each model
        plt.plot(xs, ys, linestyle=line_styles[i % len(line_styles)], 
                 marker=markers[i % len(markers)], label=algorithm)
    
    plt.xlabel('Datacenter size')
    plt.ylabel('Total Algorithm Runtime (seconds)')
    plt.title('Total Algorithm Runtime vs PMs by ALGORITHM')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <report_file>")
        sys.exit(1)
    
    filename = sys.argv[1]
    data = parse_report_file(filename)
    plot_data(data)

if __name__ == '__main__':
    main()
