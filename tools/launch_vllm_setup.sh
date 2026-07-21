#!/bin/bash
source $HOME/.local/bin/env
nohup bash /mnt/c/Users/31163/setup_vllm.sh > /tmp/vllm_setup.log 2>&1 &
echo "PID: $!"
