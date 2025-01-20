import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
from jinja2 import Environment, FileSystemLoader
import plotly.express as px
import plotly.io as pio


from src.weights import pue, price, kWh_to_J
# Set Plotly default template
pio.templates.default = "plotly_dark"

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Analyze simulation results from a log file.')
parser.add_argument('file', help='Path to the log file containing simulation results.')
parser.add_argument('--groupby', nargs='+', default=['MASTER_MODEL'], help='Parameters to group results by.')
parser.add_argument('--synthetic', action='store_true', help='Analyze synthetic workload results.')
args = parser.parse_args()
grouping_vars = args.groupby
groupby_workload = 'WORKLOAD_NAME' if not args.synthetic else 'NEW_VMS_PATTERN'
output_folder = os.path.dirname(args.file)
output_filename = os.path.basename(args.file).replace('.txt', '.html')


# Initialize variables
data = []
record = {}
start_parsing = False
config_parsing = True  # Flag to indicate we're parsing config parameters
time_step = -1
num_time_steps = -1

# Read and parse the data
with open(args.file, 'r') as f:
    for line in f:
        line = line.strip()
        if line.startswith('WORKLOAD_NAME'):
            # Start parsing a new record
            start_parsing = True
            config_parsing = False  # Stop parsing config parameters
            key, value = line.split('=')
            record[key.strip()] = value.strip()
        elif config_parsing:
            # Parse configuration parameters
            if line.startswith('Config Parameters and Results:'):
                continue  # Skip this line
            elif line.startswith('------------------------------------------'):
                continue  # Skip separator lines
            else:
                # Handle multiple parameters in a single line
                params = line.split(',')
                for param in params:
                    if '=' in param:
                        key, value = param.strip().split('=')
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
                time_step = None
        elif line.startswith('Total Model Runtime:'):
            key, value = line.split(':', 1)
            # Remove the 'seconds' text and any extra spaces
            time_value = value.replace('seconds', '').strip()
            record['Time Taken (s)'] = float(time_value)
        elif line.startswith('Completed migrations:'):
            key, value = line.split(':', 1)
            record['Completed Migrations'] = int(value.strip())
        elif line.startswith('Max percentage of PMs on:'):
            key, value = line.split(':', 1)
            record['Max % PMs On'] = float(value.strip().replace('%', ''))
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
                record[f'Avg PM {metric} Load'] = float(metric_value.strip().replace('%', ''))
        elif line.startswith('Average wait time:'):
            key, value = line.split(':', 1)
            record['Avg Wait Time (steps)'] = float(value.strip())
        elif line.startswith('Runtime efficiency:'):
            key, value = line.split(':', 1)
            record['Runtime Efficiency'] = float(value.strip())
        elif line.startswith('Overall time efficiency:'):
            key, value = line.split(':', 1)
            record['Overall Time Efficiency'] = float(value.strip())
        elif line.startswith('Total Revenue:'):
            key, value = line.split(':', 1)
            value = value.strip().replace('$', '')
            record['Revenue'] = float(value)
        elif line.startswith('Total PM Load Cost:'):
            key, value = line.split(':', 1)
            record['PM Load Cost'] = float(value.strip().replace('$', ''))
        elif line.startswith('Total PM Switch Cost:'):
            key, value = line.split(':', 1)
            record['PM Switch Cost'] = float(value.strip().replace('$', ''))
        elif line.startswith('Total Migration Energy Cost:'):
            key, value = line.split(':', 1)
            record['Migration Energy Cost'] = float(value.strip().replace('$', ''))
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
                record = {}
                start_parsing = False
                config_parsing = True  # Start parsing config parameters for the next record
        else:
            continue  # Ignore other lines

# Add the last record if it exists
if record:
    data.append(record)

# Create a DataFrame from the parsed data
df = pd.DataFrame(data)
df['Total Energy Consumption (kWh)'] = df['Costs'] / ( pue * price["energy"] ) / kWh_to_J
df['Energy Efficiency'] = df['Revenue'] / df['Costs']

# Convert numeric columns to appropriate data types
numeric_columns = [
    'Revenue', 'Costs', 'Net Profit',
    'PM Load Cost', 'PM Switch Cost', 'Migration Energy Cost',
    'Completed Migrations',
    'Max % PMs On', 'Avg PMs On', 'Total PMs',
    'Avg PM CPU Load', 'Avg PM Memory Load',
    'Profit Margin (%)', 'Energy Efficiency',
    'Total Energy Consumption Ratio',
    'Avg Wait Time (steps)', 'Runtime Efficiency', 'Overall Time Efficiency',
    'SEED_NUMBER', 'NEW_VMS_PER_STEP', 'MACRO_MODEL_PERIOD', 'MICRO_MODEL_PERIOD',
    'safety_margin', 'step_window_for_online_prediction', 'step_window_for_weights_accuracy',
    'w_concurrent_migrations', 'CPLEX_TIME_LIMIT_MACRO', 'CPLEX_OPTIMALITY_GAP_MACRO',
    'CPLEX_TIME_LIMIT_MICRO', 'CPLEX_OPTIMALITY_GAP_MICRO',
]

for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Ensure seaborn styles are applied
sns.set_theme(style='whitegrid')

# Collect data for the HTML report
workloads_data = []

for workload in df[groupby_workload].unique():
    print(f"\nProcessing {groupby_workload}: {workload}")
    df_workload = df[df[groupby_workload] == workload].copy()

    # Calculate metrics for each workload
    max_net_profit = df_workload['Net Profit'].max()
    min_total_energy_consumption = df_workload['Total Energy Consumption (kWh)'].min()
    df_workload['Profit Margin (%)'] = (df_workload['Net Profit'] / max_net_profit) * 100
    df_workload['Total Energy Consumption Ratio'] = df_workload['Total Energy Consumption (kWh)'] / min_total_energy_consumption

    # Combine grouping variables into a single 'Group' column in df_workload
    df_workload['Group'] = df_workload[grouping_vars].astype(str).agg(' | '.join, axis=1)

    # Get the unique 'Group' values in the order they appear
    group_order = df_workload['Group'].unique().tolist()

    # Group by 'Group' and aggregate data without sorting
    aggregation_functions = {
        'Revenue': 'mean',
        'Costs': 'mean',
        'Net Profit': 'mean',
        'PM Load Cost': 'mean',
        'PM Switch Cost': 'mean',
        'Migration Energy Cost': 'mean',
        'Completed Migrations': 'mean',
        'Max % PMs On': 'mean',
        'Avg PMs On': 'mean',
        'Avg PM CPU Load': 'mean',
        'Avg PM Memory Load': 'mean',
        'Total Energy Consumption (kWh)': 'mean',
        'Energy Efficiency': 'mean',
        'Avg Wait Time (steps)': 'mean',
        'Runtime Efficiency': 'mean',
        'Overall Time Efficiency': 'mean',
        'Time Taken (s)': 'mean',
        'Profit Margin (%)': 'mean',
        'Total Energy Consumption Ratio': 'mean'
    }
    df_grouped = df_workload.groupby('Group', sort=False).agg(aggregation_functions).reset_index()

    # Convert 'Group' to categorical with the specified order
    df_grouped['Group'] = pd.Categorical(df_grouped['Group'], categories=group_order, ordered=True)
    df_grouped = df_grouped.sort_values('Group')

    # Prepare display DataFrame
    df_display = df_grouped.set_index('Group')[list(aggregation_functions.keys())]

    # Format and style the DataFrame
    styled_df = df_display.style\
        .format({
            'Revenue': '${:,.2f}',
            'Costs': '${:,.2f}',
            'Net Profit': '${:,.2f}',
            'PM Load Cost': '${:,.2f}',
            'PM Switch Cost': '${:,.2f}',
            'Migration Energy Cost': '${:,.2f}',
            'Completed Migrations': '{:,.0f}',
            'Max % PMs On': '{:.2f}%',
            'Avg PMs On': '{:.2f}',
            'Avg PM CPU Load': '{:.2f}%',
            'Avg PM Memory Load': '{:.2f}%',
            'Profit Margin (%)': '{:.2f}%',
            'Total Energy Consumption (kWh)': '{:.2f} kWh',
            'Energy Efficiency': '{:.2f}',
            'Avg Wait Time (steps)': '{:.2f}',
            'Runtime Efficiency': '{:.2f}',
            'Overall Time Efficiency': '{:.2f}',
            'Time Taken (s)': '{:,.0f} s'
        })\
        .background_gradient(cmap='RdYlGn', subset=['Net Profit'])\
        .bar(subset=['Completed Migrations'], color='lightgreen')\
        .set_table_attributes('class="table table-striped table-hover"')\
        .set_caption(f'Analysis for {groupby_workload}: {workload}')

    # Get the HTML representation of the styled DataFrame
    html_table = styled_df.to_html()

    # Generate interactive Plotly plots and get their HTML
    plots_html = []

    # Total Costs Plot with narrower bars
    fig = px.bar(
        df_grouped,
        x='Group',
        y='Costs',
        title=f"Total Costs for {groupby_workload}: {workload}",
        labels={'Costs': 'Total Costs ($)', 'Group': 'Group'},
        width=800,  # Adjust the width of the plot
        height=400  # Adjust the height of the plot
    )
    fig.update_traces(width=0.4)  # Set the width of the bars
    fig.update_xaxes(categoryorder='array', categoryarray=group_order)
    plots_html.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # Completed Migrations Plot with narrower bars
    fig = px.bar(
        df_grouped,
        x='Group',
        y='Completed Migrations',
        title=f"Completed Migrations for {groupby_workload}: {workload}",
        labels={'Completed Migrations': 'Number of Migrations', 'Group': 'Group'},
        width=800,  # Adjust the width of the plot
        height=400  # Adjust the height of the plot
    )
    fig.update_traces(width=0.4)  # Set the width of the bars
    fig.update_xaxes(categoryorder='array', categoryarray=group_order)
    plots_html.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # Average Loads Plot with narrower bars
    fig = px.bar(
        df_grouped,
        x='Group',
        y=['Avg PM CPU Load', 'Avg PM Memory Load'],
        title=f"Average PM Loads for {groupby_workload}: {workload}",
        barmode='group',
        labels={'value': 'Load (%)', 'variable': 'Load Type', 'Group': 'Group'},
        width=800,  # Adjust the width of the plot
        height=400  # Adjust the height of the plot
    )
    fig.update_traces(width=0.2)  # Set the width of the bars
    fig.update_xaxes(categoryorder='array', categoryarray=group_order)
    plots_html.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # Average Number of PMs On Plot with narrower bars
    fig = px.bar(
        df_grouped,
        x='Group',
        y='Avg PMs On',
        title=f"Average Number of PMs On for {groupby_workload}: {workload}",
        labels={'Avg PMs On': 'Average PMs On', 'Group': 'Group'},
        width=800,  # Adjust the width of the plot
        height=400  # Adjust the height of the plot
    )
    fig.update_traces(width=0.4)  # Set the width of the bars
    fig.update_xaxes(categoryorder='array', categoryarray=group_order)
    plots_html.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # Add the workload data to the list
    workloads_data.append({
        'name': workload,
        'table': html_table,
        'plots': plots_html
    })

    # Performance Metrics Plot
    fig = px.bar(
        df_grouped,
        x='Group',
        y=['Avg Wait Time (steps)', 'Runtime Efficiency', 'Overall Time Efficiency'],
        title=f"Performance Metrics for {groupby_workload}: {workload}",
        labels={'value': 'Metric', 'variable': 'Metric Type', 'Group': 'Group'},
        width=800,  # Adjust the width of the plot
        height=400  # Adjust the height of the plot
    )

# Set up Jinja2 environment
env = Environment(loader=FileSystemLoader('.'))
template = env.get_template('report_template.html')

# Render the template
html_out = template.render(workloads=workloads_data)

# Save the HTML report
os.makedirs(output_folder, exist_ok=True)
with open(os.path.join(output_folder, output_filename), 'w') as f:
    f.write(html_out)

print(f"HTML report generated: {output_filename}")


