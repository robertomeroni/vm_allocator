import pandas as pd
import matplotlib.pyplot as plt

# Load the CSV file
file_name = 'main_scalability_test_results.csv'
file_path = 'results/main_scalability_test_results.csv'
data = pd.read_csv(file_path)

# Plot the results
plt.figure(figsize=(20, 12))
for physical_machines in data['Physical Machines'].unique():
    subset = data[data['Physical Machines'] == physical_machines]
    plt.plot(subset['Virtual Machines'], subset['Time (s)'], label=f'{physical_machines} Physical Machines')

plt.xlabel('Virtual Machines')
plt.ylabel('Time (s)')
plt.title('Main Model Scalability Test Results')
plt.legend()
plt.grid(True)
plt.show()