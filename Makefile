
PYTHON = python3

FILE ?= tests/test_small.txt
SERVER_IP ?= 10.0.0.2
PORT ?= 5000

.PHONY: help client server controller network clean

help:
	@echo "SDN TCP Backup Project"
	@echo ""
	@echo "Available commands:"
	@echo "  make server      - Start the TCP backup server"
	@echo "  make client      - Send a file to a backup server"
	@echo "  make controller  - Start the OS-Ken SDN controller"
	@echo "  make network     - Start the Mininet topology"
	@echo "  make clean       - Clean up Mininet state"

server:
	$(PYTHON) -m server.server

client:
	$(PYTHON) -m client.client $(FILE) $(SERVER_IP):$(PORT)

controller:
	$(PYTHON) controller/run_controller.py controller/simple_switch.py

network:
	sudo $(PYTHON) mininet/topo.py

clean:
	sudo mn -c
