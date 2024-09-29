import pandas as pd
import matplotlib.pyplot as plt

# Initialize variables
data = []
record = None
start_parsing = False

# Read and parse the data
with open('results/simulation_results.ini', 'r') as f:
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
        elif line.startswith('Completed migrations:'):
            key, value = line.split(':', 1)
            record['Completed Migrations'] = int(value.strip())
        elif line.startswith('Removed VMs:'):
            key, value = line.split(':', 1)
            record['Removed VMs'] = int(value.strip())
        elif line.startswith('Max percentage of PMs on:'):
            key, value = line.split(':', 1)
            record['Max % PMs On'] = float(value.strip())
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
    display_columns = [
        'Revenue', 'Costs', 'Net Profit',
        'PM Energy Cost', 'Migration Energy Cost',
        'Completed Migrations', 'Removed VMs', 'Profit Margin (%)'
    ]
    print(df_workload[display_columns])

    # Identify the best model based on Net Profit
    best_model = df_workload['Net Profit'].idxmax()
    best_profit = df_workload['Net Profit'].max()
    print(f"\nBest Model for {workload}: {best_model} with Net Profit of ${best_profit:.2f}")

    # Plot Total Costs and Net Profit for each model
    plot_data = df_workload[['Costs']]
    plot_data.plot(kind='bar', figsize=(10, 6))
    plt.title(f"Total Costs for {workload}")
    plt.xlabel('Model')
    plt.ylabel('Amount ($)')
    plt.xticks(rotation=0)
    plt.tight_layout()
    # plt.show()
