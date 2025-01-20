# VM Allocator

Simulate the allocation and execution of Virtual Machines on Physical Machines to test the efficacy of algorithms. Developed proprietary algorithms combine mathematical programming models for optimal allocation in an efficient and scalable manner.

## Prerequisites

- **IBM ILOG CPLEX Optimization Studio**: This project requires IBM ILOG CPLEX Optimization Studio for solving VM allocation with proprietary algorithms.

## Setup Instructions

1. **Clone the Repository**

   Clone the repository to your local machine using the following command:

   ```bash
   git clone https://github.com/robertomeroni/vm_allocator.git
   cd vm_allocator
   ```

2. **Create a Virtual Environment**

   Create a virtual environment to manage dependencies:

   ```bash
   python -m venv .venv
   ```

3. **Activate the Virtual Environment**

   Activate the virtual environment:

   - On **Windows**:
     ```bash
     .venv\Scripts\activate
     ```
   - On **macOS/Linux**:
     ```bash
     source .venv/bin/activate
     ```

4. **Install Dependencies**

   Install the required packages using the `requirements.txt` file:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

- **Run a Simulation**: To run a simulation with the settings in `config.py`, execute the following command:

  ```bash
  ./run.sh
  ```

- **Run Tests with Multiple Algorithms**: To run a test with multiple algorithms, use:

  ```bash
  ./test.sh
  ```

- **Test Scalability**: To test the scalability of the algorithms, execute:

  ```bash
  ./test_scalability.sh
  ```

