# TCP-Based File Backup System Using Mininet and SDN

## 1. Project Overview

This project implements a TCP-based file backup system in which one client transfers a file to two backup servers over a Software-Defined Network (SDN).

The client uses TCP socket programming to transfer files. Each backup server receives and stores the file, verifies its integrity using a SHA-256 checksum, and reports the result to the client. The client reports whether the backup was successfully stored and verified by each destination.

The network is emulated using Mininet and Open vSwitch (OVS). An OS-Ken SDN controller manages the switches using OpenFlow 1.3. The controller discovers the network topology, learns hosts, calculates switch paths using Breadth-First Search (BFS), installs forwarding rules, and recalculates routes when links are added or fail.

The project also includes a web dashboard for starting and monitoring the backup workflow, controlling servers and links, uploading files, and viewing transfer status.

## 2. Objectives

- Implement file transfer using TCP sockets.
- Replicate a file across two backup servers.
- Verify file integrity using SHA-256 checksums.
- Deploy and test the application in a Mininet network.
- Use an OS-Ken SDN controller to manage OpenFlow 1.3 switches.
- Discover the network topology and calculate forwarding paths using BFS.
- Detect network link failures and reroute traffic through an available alternate path.
- Provide a dashboard to monitor the network and operate the backup workflow.
- Test large-file transfer, integrity rejection, network failover, and transfer performance.

## 3. System Architecture

The system contains one client host (`h1`), two backup-server hosts (`h2` and `h3`), three OpenFlow switches (`s1`, `s2`, and `s3`), and an OS-Ken SDN controller.

### Network Topology

- Client `h1` is connected to switch `s1`.
- Backup servers `h2` and `h3` are connected to switch `s2`.
- Switches `s1` and `s2` have a direct link.
- Switches `s1` and `s2` also have an alternate path through `s3` (`s1`–`s3`–`s2`).
- The SDN controller manages all three switches using OpenFlow 1.3.

```text
                    Direct Link
h1 -- s1 ------------------------------- s2 --+-- h2
        \                                 /   +-- h3
         \                               /
          +------------ s3 -------------+
                    Alternate Path
```

The two paths between `s1` and `s2` are:

- **Direct path:** `s1` → `s2`
- **Alternate path:** `s1` → `s3` → `s2`

When the direct link is disabled, the controller removes the affected forwarding paths, recalculates routes using the updated topology, and installs forwarding rules through the alternate path when it is available.

| Component | Role | IP Address |
|---|---|---|
| h1 | TCP client | 10.0.0.1 |
| h2 | Backup server 1 | 10.0.0.2 |
| h3 | Backup server 2 | 10.0.0.3 |
| s1 | OpenFlow switch 1 | N/A |
| s2 | OpenFlow switch 2 | N/A |
| s3 | OpenFlow switch 3 | N/A |
| c0 | Mininet controller label, when shown | 127.0.0.1:6653 |

## 4. Technologies Used

- Python 3
- TCP socket programming
- SHA-256 checksum verification
- Mininet
- Open vSwitch (OVS)
- OS-Ken SDN controller
- OpenFlow 1.3
- Breadth-First Search (BFS)
- Ubuntu / Linux
- HTML, CSS, and JavaScript dashboard served by the Python application
- Make

## 5. Project Structure

The repository contains the following main files and directories:

```text
CN-MINI-Project-demo/
├── client/
│   └── client.py
├── server/
│   └── server.py
├── controller/
│   ├── run_controller.py
│   └── simple_switch.py
├── gui/
│   └── dashboard.py
├── mininet/
│   └── topo.py
├── protocol/
│   └── protocol.py
├── utils/
│   └── checksum.py
├── tests/
│   ├── test_small.txt
│   ├── test_10mb.bin
│   ├── test_large_transfer.py
│   ├── test_integrity_failure.py
│   └── run_benchmarks.py
├── results/
│   └── benchmarks.csv
├── Makefile
├── requirements.txt
├── .gitignore
└── README.md
```

Runtime folders such as `backup/` and `uploads/` are created when the application is used. They are not required to be present in a fresh clone.

## 6. Setup and Installation

### Prerequisites

Use an Ubuntu environment with the following available:

- Python 3 and `venv`
- Mininet
- Open vSwitch
- Git

Mininet and Open vSwitch are system-level dependencies. Install and verify them for your Ubuntu distribution before running the network. The Python dependencies are listed in `requirements.txt`.

### Clone the Repository

```bash
git clone https://github.com/kirankumar-aiml-2007/CN-MINI-Project.git
cd CN-MINI-Project
```

If the project is already cloned, change into the existing repository directory instead.

The commands in the following sections use this working directory:

```bash
cd ~/CN-MINI-Project-demo
```

If your repository is stored under a different directory name, use that directory instead.

### Create and Activate the Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install Python Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Make sure that Mininet and Open vSwitch are installed and working independently of the Python virtual environment.

## 7. Running the Application

The application can be run in either **CLI mode** or **dashboard mode**.

Both modes use the same SDN controller and Mininet topology. Do not start the CLI topology and dashboard topology at the same time because each mode manages its own Mininet network.

### Option A: Run Using the Mininet CLI

#### Step 1: Start the SDN Controller

Open the first Ubuntu terminal:

```bash
cd ~/CN-MINI-Project-demo
source .venv/bin/activate
python controller/run_controller.py controller/simple_switch.py
```

Keep this terminal open.

The controller must be running before the Mininet switches connect to it. It listens for OpenFlow connections on port `6653`.

#### Step 2: Start the Mininet Topology

Open a second Ubuntu terminal:

```bash
cd ~/CN-MINI-Project-demo
sudo mn -c
sudo python3 mininet/topo.py
```

Wait until the `mininet>` prompt appears.

The topology creates three hosts and three switches.

#### Step 3: Verify Network Connectivity

At the `mininet>` prompt, run:

```text
pingall
```

The expected final result after host discovery is:

```text
*** Results: 0% dropped (6/6 received)
```

If the first test is sent while hosts are still being discovered, run `pingall` again after discovery.

If packets continue to be lost, check that the controller is running and that the switches have connected to it before continuing.

#### Step 4: Start the Two Backup Servers

At the `mininet>` prompt, start one server on `h2` and one on `h3`.

The following commands use the current project path:

```text
h2 sh -c 'cd /home/kiran_kumar/CN-MINI-Project-demo && mkdir -p backup/h2 && python3 -m server.server 10.0.0.2 5000 backup/h2' &
```

```text
h3 sh -c 'cd /home/kiran_kumar/CN-MINI-Project-demo && mkdir -p backup/h3 && python3 -m server.server 10.0.0.3 5000 backup/h3' &
```

Keep both servers running while testing.

If another team member uses this project, replace the absolute project path with their own Ubuntu project path.

#### Step 5: Transfer a File From the Client

At the `mininet>` prompt, send a small test file to both servers:

```text
h1 python3 -m client.client tests/test_small.txt 10.0.0.2:5000 10.0.0.3:5000
```

To transfer the 10 MB test file instead:

```text
h1 python3 -m client.client tests/test_10mb.bin 10.0.0.2:5000 10.0.0.3:5000
```

The client reports the result for each destination.

A successful transfer should report:

```text
2/2 backups verified
```

### Option B: Run Using the Web Dashboard

The dashboard starts and manages its own Mininet topology.

Do not run `mininet/topo.py` separately while the dashboard is active.

#### Step 1: Start the SDN Controller

In the first Ubuntu terminal:

```bash
cd ~/CN-MINI-Project-demo
source .venv/bin/activate
python controller/run_controller.py controller/simple_switch.py
```

Keep the controller running.

#### Step 2: Start the Dashboard

Open a second Ubuntu terminal:

```bash
cd ~/CN-MINI-Project-demo
sudo mn -c
sudo python3 gui/dashboard.py
```

The dashboard server is available at:

```text
http://localhost:8080
```

Open that address in a web browser on Windows or Ubuntu.

The dashboard provides:

- Network and host status monitoring.
- Backup server start and stop controls.
- File upload functionality.
- File transfer to selected backup servers.
- Network link control for failure simulation.
- Network discovery and connectivity monitoring.
- Backup transfer status and logs.

Keep the dashboard terminal open while using the application.

Stop the dashboard with `Ctrl+C` when finished.

The dashboard controls its own Mininet instance.

## 8. Testing and Verification

Run the tests below in the relevant environment.

Tests that use `h1`, `h2`, or `h3` are entered at the Mininet prompt.

Local Python test scripts are run from a normal Ubuntu terminal with the virtual environment activated.

### 8.1 Network Connectivity

At the Mininet prompt:

```text
pingall
```

The expected result after host discovery is:

```text
*** Results: 0% dropped (6/6 received)
```

### 8.2 Controller and Switch Connectivity

From a normal Ubuntu terminal:

```bash
sudo ovs-vsctl show
```

Check that the OVS bridges exist and that their controller configuration points to the running controller endpoint.

The controller terminal should also show the switches connecting.

### 8.3 OpenFlow Forwarding Rules

From a normal Ubuntu terminal:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
sudo ovs-ofctl -O OpenFlow13 dump-flows s2
sudo ovs-ofctl -O OpenFlow13 dump-flows s3
```

Inspect the flow tables for controller-installed forwarding rules and table-miss rules.

### 8.4 File Backup and Checksum Verification

At the Mininet prompt, send a file to both backup servers:

```text
h1 python3 -m client.client tests/test_10mb.bin 10.0.0.2:5000 10.0.0.3:5000
```

A successful transfer reports that both destinations stored and verified the file, ending with:

```text
2/2 backups verified
```

The client and servers use SHA-256 checksums to verify file integrity.

### 8.5 Large-File Transfer Test

From a normal Ubuntu terminal, with the virtual environment activated:

```bash
python tests/test_large_transfer.py
```

This test starts a local test server, transfers the 10 MB test file, and verifies the received file.

A successful test reports:

```text
SUCCESS: Large file transfer verified.
```

This is a local client/server test and does not require the Mininet topology to be running.

### 8.6 Integrity-Failure Test

From a normal Ubuntu terminal, with the virtual environment activated:

```bash
python tests/test_integrity_failure.py
```

This test supplies an invalid checksum and verifies that the server rejects the transfer and removes the temporary file.

A successful test reports:

```text
SUCCESS: Invalid file rejected.
SUCCESS: Temporary file deleted.
```

This is a local test and does not require Mininet to be running.

### 8.7 Link Failure and Automatic Rerouting

Run this test in CLI mode with the controller, Mininet topology, and both backup servers already running.

At the `mininet>` prompt, disable the direct link between `s1` and `s2`:

```text
link s1 s2 down
```

The controller receives the topology change, removes the affected forwarding flows, recalculates the paths, and uses the alternate route when it is available:

```text
s1 -> s3 -> s2
```

Check connectivity:

```text
pingall
```

Then test a file transfer while the direct link is down:

```text
h1 python3 -m client.client tests/test_10mb.bin 10.0.0.2:5000 10.0.0.3:5000
```

Both backup servers should still be reachable and verify the file if the alternate path is operational.

Restore the direct link:

```text
link s1 s2 up
```

Run `pingall` again and verify that the controller detects the restored link and recalculates paths using the updated topology.

### 8.8 Performance Benchmarking

Run the benchmark in CLI mode after the controller is running, Mininet is active, `pingall` succeeds, and both backup servers are listening.

At the `mininet>` prompt, run:

```text
h1 python3 tests/run_benchmarks.py tests/test_10mb.bin D2 10.0.0.2:5000 10.0.0.3:5000
```

The script performs three transfer runs for the specified mode and destinations.

It records the date, mode, file, file size, run number, elapsed time, aggregate throughput, and status in:

```text
results/benchmarks.csv
```

Use the same file, destinations, and benchmark procedure when collecting results for different project stages.

Only successful runs should be included in the successful-run performance comparison.

Failed setup or connectivity attempts remain visible in the raw CSV for traceability but should not be treated as successful performance measurements.

Because Mininet is commonly started with `sudo`, the CSV may be created with root ownership when the benchmark is launched through `h1`.

After exiting Mininet, if your normal Ubuntu user cannot edit the CSV, restore ownership with:

```bash
sudo chown "$USER":"$USER" results/benchmarks.csv
```

## 9. SDN Controller Functionality

The OS-Ken controller uses OpenFlow 1.3 to manage the three OVS switches.

Its main responsibilities include:

- **Switch discovery:** Tracks switches as they connect to or leave the controller.
- **Topology discovery:** Tracks switch-to-switch links using topology events.
- **Host learning:** Learns host MAC addresses and the switch ports where hosts are connected. Host information is updated from packet-in traffic and host-discovery events.
- **Path calculation:** Uses BFS over the current switch-link graph to calculate a path between the source and destination switches.
- **Flow installation:** Installs forwarding rules for known source and destination MAC-address pairs along the selected path.
- **Broadcast and multicast forwarding:** Uses a spanning tree to avoid forwarding loops when sending broadcast or multicast traffic.
- **Link failure handling:** Removes failed links from the topology and deletes the controller's forwarding flows so that routes can be recalculated.
- **Port and switch status handling:** Reacts to link-down port events and switch disconnections.
- **Automatic rerouting:** Recalculates routes and installs forwarding rules over an available alternate path.
- **Link restoration:** Adds restored links to the topology and recalculates routes.

For unicast traffic, the controller learns the source host.

If the destination host is not yet known, the unicast packet is not forwarded; forwarding can occur after the destination is learned.

Broadcast and multicast traffic is handled separately using the spanning tree.

The SDN controller manages Ethernet forwarding and network paths.

The TCP client and backup servers handle file transfer, storage, acknowledgements, and checksum verification.

## 10. Performance Evaluation

The recorded benchmark data compares the D1 baseline with the D2 implementation using the 10 MB test file and two backup-server destinations.

The comparison below uses the median of successful benchmark records in `results/benchmarks.csv`.

| Metric | D1 | D2 |
|---|---:|---:|
| Successful benchmark runs | 3 | 6 |
| Median elapsed time | 0.143 s | 0.1045 s |
| Median aggregate throughput | 140.132 MB/s | 191.362 MB/s |

The recorded median aggregate throughput in D2 is approximately **36.6% higher** than the D1 median in this test environment.

D2 also has a lower median elapsed time in these recorded runs.

One D2 attempt in the raw CSV is marked `FAILED` because the controller was not available when Mininet was first started.

That record is retained for traceability and is excluded from the successful-run median calculations.

The six successful D2 records are used in the table above.

These figures describe the measured Mininet environment and the recorded benchmark runs. They should not be interpreted as guaranteed throughput on physical networks or under different system loads.

## 11. Limitations and Future Work

Possible future improvements include:

- Dynamic backup-server selection based on server availability or load.
- Recovery and resumption of interrupted file transfers.
- Concurrent handling of multiple clients and transfers.
- Additional benchmark sizes and repeated tests under controlled conditions.
- Testing larger and more complex network topologies, including multiple simultaneous link failures.
- Routing decisions that consider link capacity, delay, or congestion in addition to hop count.
- Authentication and access control for dashboard operations.

## 12. Conclusion

This project demonstrates TCP-based file replication from one client to two backup servers in a Mininet-emulated network managed by an OS-Ken SDN controller.

It combines TCP socket programming and SHA-256 integrity verification with OpenFlow-based forwarding, topology discovery, BFS path calculation, link-failure detection, and automatic rerouting through an alternate path.

The web dashboard provides an additional interface for operating and monitoring the system.

The recorded tests demonstrate successful file backup and integrity verification, large-file transfer, rejection of an invalid checksum, and connectivity and backup operation through the tested alternate network path.

The benchmark records provide a measured D1/D2 performance comparison for the configured Mininet environment.