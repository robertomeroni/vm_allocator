import pandas as pd
import matplotlib.pyplot as plt
import argparse

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Analyze simulation results from a log file.')
parser.add_argument('--file', required=True, help='Path to the log file containing simulation results.')
args = parser.parse_args()

# Initialize variables
data = []
record = None
start_parsing = False
time_step = -1
num_time_steps = -1

# Read and parse the data
with open(args.file, 'r') as f:
    for line in f:
        line = line.strip()
        if line.startswith('WORKLOAD_NAME'):
            # Start parsing a new record
            start_parsing = True
            if record:
                data.append(record)
            record = {}
            key, value = line.split('=')
            record[key.strip()] = value.strip()
        elif not start_parsing:
            continue  # Skip lines until 'WORKLOAD_NAME' is found
        elif line.startswith('MASTER_MODEL'):
            key, value = line.split('=')
            record[key.strip()] = value.strip()
        elif line.startswith('TIME_STEP'):
            key, value = line.split('=')
            if time_step == -1:
                time_step = value.strip()
            elif time_step != value.strip():
                time_step = None
        elif line.startswith('NUM_TIME_STEPS'):
            key, value = line.split('=')
            if num_time_steps == -1:
                num_time_steps = value.strip()
            elif num_time_steps != value.strip():
                num_time_steps = None
        elif line.startswith('Completed migrations:'):
            key, value = line.split(':', 1)
            record['Completed Migrations'] = int(value.strip())
        elif line.startswith('Removed VMs:'):
            key, value = line.split(':', 1)
            record['Removed VMs'] = int(value.strip())
        elif line.startswith('Max percentage of PMs on:'):
            key, value = line.split(':', 1)
            record['Max % PMs On'] = float(value.strip())
        elif line.startswith('Average number of PMs on:'):
            key, value = line.split(':', 1)
            parts = value.strip().split('/')
            record['Avg PMs On'] = float(parts[0])
            record['Total PMs'] = int(parts[1])
        elif line.startswith('Average PM loads:'):
            key, value = line.split(':', 1)
            parts = value.strip().split(',')
            for part in parts:
                metric, metric_value = part.strip().split(' ')
                record[f'Avg PM {metric} Load'] = float(metric_value)
        elif line.startswith('Total Revenue:'):
            key, value = line.split(':', 1)
            value = value.strip().replace('$', '')
            record['Revenue'] = float(value)
        elif line.startswith('Total PM Energy Cost:'):
            key, value = line.split(':', 1)
            record['PM Energy Cost'] = float(value.strip())
        elif line.startswith('Total Migration Energy Cost:'):
            key, value = line.split(':', 1)
            record['Migration Energy Cost'] = float(value.strip())
        elif line.startswith('Total Costs:'):
            key, value = line.split(':', 1)
            value = value.strip().replace('$', '')
            record['Costs'] = float(value)
        elif line.startswith('Final Net Profit:'):
            key, value = line.split(':', 1)
            value = value.strip().replace('$', '')
            record['Net Profit'] = float(value)
        elif line.startswith('============================'):
            # End of current record
            if record:
                data.append(record)
                record = None
                start_parsing = False
        else:
            continue  # Ignore other lines

# Add the last record if it exists
if record:
    data.append(record)

# Create a DataFrame from the parsed data
df = pd.DataFrame(data)

# Calculate additional metrics
df['Profit Margin (%)'] = (df['Net Profit'] / df['Revenue']) * 100



# Display analysis for each workload
for workload in df['WORKLOAD_NAME'].unique():
    print(f"\nAnalysis for Workload: {workload}")
    df_workload = df[df['WORKLOAD_NAME'] == workload].set_index('MASTER_MODEL')
    if df_workload['Total PMs'].nunique() == 1:
        print(f"Total PMs: {df_workload['Total PMs'].iloc[0]}")
    if time_step and num_time_steps:
        print(f"Time Step: {time_step}, Number of Time Steps: {num_time_steps}")
    display_columns = [
        'Revenue', 'Costs', 'Net Profit',
        'PM Energy Cost', 'Migration Energy Cost',
        'Completed Migrations', 
        # 'Removed VMs',
        'Max % PMs On', 'Avg PMs On', 
        'Avg PM CPU Load', 'Avg PM Memory Load',
        'Profit Margin (%)'
    ]
    print(df_workload[display_columns])

    # Identify the best model based on Net Profit
    best_model = df_workload['Net Profit'].idxmax()
    best_profit = df_workload['Net Profit'].max()
    print(f"\nBest Model for {workload}: {best_model} with Net Profit of ${best_profit:.2f}")

    # Plot Total Costs for each model
    plot_data = df_workload[['Costs']]
    plot_data.plot(kind='bar', figsize=(10, 6))
    plt.title(f"Total Costs for {workload}")
    plt.xlabel('Model')
    plt.ylabel('Amount ($)')
    plt.xticks(rotation=0)
    plt.tight_layout()
    # plt.show()
