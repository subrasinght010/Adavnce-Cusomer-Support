#!/bin/bash

# Define the base directory
BASE_DIR="Multi-Agent-System"

# Create directory structure
mkdir -p $BASE_DIR/state
mkdir -p $BASE_DIR/nodes/core
mkdir -p $BASE_DIR/graph_workflows

# Create files
touch $BASE_DIR/state/optimized_workflow_state.py
touch $BASE_DIR/nodes/core/base_node.py
touch $BASE_DIR/nodes/optimized_incoming_listener.py
touch $BASE_DIR/nodes/unified_intelligence_agent.py
touch $BASE_DIR/nodes/parallel_execution_agents.py
touch $BASE_DIR/nodes/background_agents.py
touch $BASE_DIR/graph_workflows/optimized_workflow.py
touch $BASE_DIR/main.py

# Optional: print confirmation
echo "✅ Project structure created successfully:"
tree $BASE_DIR
