#!/bin/bash

# Clean up
rm -rf ./simulation/model_input        \
       ./simulation/model_output       \
       ./simulation/simulation_output  \
       ./simulation/overload
clear

python3 src/simulation.py
