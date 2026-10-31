# TCP-Based File Backup System Using Mininet and SDN

## 1. Project Overview

This project implements a TCP-based file backup system in which a client transfers a file to two backup servers over a Software-Defined Network (SDN).

The application uses TCP socket programming to transfer files reliably. The receiving servers store the files and verify their integrity using SHA-256 checksums.

The network is emulated using Mininet, with Open vSwitch (OVS) switches managed by an SDN controller running OS-Ken. The controller uses OpenFlow 1.3 to manage packet forwarding, discover network topology, calculate paths using Breadth-First Search (BFS), and automatically reroute traffic when a network link fails.

## 2. Objectives

* Implement file transfer using TCP sockets.
* Replicate a file across multiple backup servers.
* Verify file integrity using SHA-256 checksums.
* Deploy and test the application in a Mininet network.
* Use an SDN controller to manage packet forwarding through OpenFlow switches.
* Discover network topology and calculate forwarding paths using BFS.
* Detect network link failures and automatically reroute traffic through alternate paths.
* Demonstrate end-to-end communication between the client and both backup servers.

## 3. System Architecture

The system consists of one client, two backup servers, three OpenFlow switches, and an SDN controller.

### Network topology

The Mininet topology connects client h1 to switch S1. Switches S1 and S2 have a direct connection, while S1 and S2 are also connected through S3, providing an alternate path in case the direct link fails.

The two backup servers, h2 and h3, connect to S2.

The SDN controller manages all three switches through OpenFlow 1.3.

```text
                  SDN Controller
                       OS-Ken
                         |
                   OpenFlow 1.3
                         |
              +----------+----------+
              |                     |
             S1 ------------------- S2
              |       Direct        |
              |                     |
             S3 --------------------+
              |
          (Alternate path)
              
              S1                    S2
              |                  /    \
             h1                 h2     h3
           Client           Backup 1  Backup 2
           10.0.0.1         10.0.0.2  10.0.0.3
```

The network provides two possible paths between S1 and S2:

* Direct path: S1 → S2
* Alternate path: S1 → S3 → S2

When the direct link between S1 and S2 fails, the controller detects the failure, recalculates routes using BFS, and installs forwarding rules through the alternate path.

| Component | Description | IP address |
|---|---|---|
| h1 | TCP client | 10.0.0.1 |
| h2 | Backup server 1 | 10.0.0.2 |
| h3 | Backup server 2 | 10.0.0.3 |
| s1 | OpenFlow switch 1 | N/A |
| s2 | OpenFlow switch 2 | N/A |
| s3 | OpenFlow switch 3 | N/A |
| c0 | OS-Ken SDN controller | 127.0.0.1:6653 |

## 4. Technologies Used

* Python 3
* TCP socket programming
* SHA-256 checksum verification
* Mininet
* Open vSwitch (OVS)
* OS-Ken SDN controller
* OpenFlow 1.3
* Breadth-First Search (BFS)
* Linux / Ubuntu
* Make

## 5. Project Structure

```text
CN-MINI-Project/
├── client/
│   └── client.py
├── server/
│   └── server.py
├── controller/
│   ├── run_controller.py
│   └── simple_switch.py
├── mininet/
│   └── topo.py
├── protocol/
│   └── protocol.py
├── utils/
│   └── checksum.py
├── tests/
│   ├── test_small.txt
│   └── test_10mb.bin
├── Makefile
├── requirements.txt
└── README.md
```

## 6. Setup and Installation

### Prerequisites

Install or configure the following in an Ubuntu environment:

* Python 3
* Mininet
* Open vSwitch
* Git

Clone the repository:

```bash
git clone https://github.com/kirankumar-aiml-2007/CN-MINI-Project.git
cd CN-MINI-Project
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

Ensure that Mininet and Open vSwitch are installed and available on the system.

## 7. Running the Application

Run the components in the following order.

### Step 1: Start the SDN controller

Open a terminal in the project directory:

```bash
source .venv/bin/activate
make controller
```

Alternatively, run:

```bash
python controller/run_controller.py controller/simple_switch.py
```

Keep the controller running. It listens for OpenFlow connections on port 6653.

### Step 2: Start the Mininet topology

Open a second terminal:

```bash
make clean
make network
```

Wait for the `mininet>` prompt.

The topology creates three switches and three hosts. The switches connect to the running SDN controller.

### Step 3: Verify network connectivity

At the Mininet prompt, run:

```text
pingall
```

The expected result after initial host discovery is:

```text
*** Results: 0% dropped (6/6 received)
```

### Step 4: Start the backup servers

Start one TCP server in host h2 and another in host h3.

Run the following commands at the Mininet prompt:

```text
h2 sh -c 'cd <PROJECT_PATH> && python3 -m server.server 10.0.0.2 5000 backup/h2' &
```

```text
h3 sh -c 'cd <PROJECT_PATH> && python3 -m server.server 10.0.0.3 5000 backup/h3' &
```

Replace `<PROJECT_PATH>` with the absolute path of the project directory on your system.

Wait until both servers report that they are listening for client connections.

### Step 5: Run the client

At the Mininet prompt, run:

```text
h1 python3 -m client.client tests/test_small.txt 10.0.0.2:5000 10.0.0.3:5000
```

The client sends the selected file to both backup servers and reports the outcome of each transfer.

## 8. Testing and Verification

The project can be demonstrated through the following tests.

### 1. Network connectivity

Use:

```text
pingall
```

This checks connectivity between the three Mininet hosts.

### 2. Controller connectivity

Use:

```bash
sudo ovs-vsctl show
```

Verify that the Open vSwitch instances are connected to the SDN controller.

### 3. OpenFlow forwarding rules

Inspect the flow tables using:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
sudo ovs-ofctl -O OpenFlow13 dump-flows s2
sudo ovs-ofctl -O OpenFlow13 dump-flows s3
```

The flow tables contain controller-installed forwarding rules and table-miss rules.

### 4. File backup

Transfer `tests/test_small.txt` to both backup servers using the client.

Verify that the file is stored at both destinations.

### 5. Integrity verification

Check that the client reports successful storage and checksum verification for each server.

### 6. Link failure and automatic rerouting

The SDN controller can be tested by bringing down the direct link between S1 and S2.

At the Mininet prompt, run:

```text
link s1 s2 down
```

The controller detects the link failure, updates its network topology, calculates an alternate path using BFS, and installs new forwarding rules.

The alternate route is:

```text
S1 → S3 → S2
```

Test connectivity again:

```text
pingall
```

Restore the direct link:

```text
link s1 s2 up
```

The controller detects the restored link and recalculates the forwarding paths.

This demonstrates dynamic path recalculation and automatic rerouting.

### Expected file transfer result

For a successful transfer to both servers, the client should report:

```text
SUMMARY
10.0.0.2:5000   OK    stored and verified
10.0.0.3:5000   OK    stored and verified

2/2 backups verified
```

The exact output may vary depending on the file, environment, and server responses.

## 9. SDN Integration

The network uses OpenFlow 1.3 switches managed by the OS-Ken SDN controller.

The controller implements the following functionalities:

* **Switch discovery:** Detects switches connecting to the controller.
* **Topology discovery:** Tracks switches and links using topology events.
* **Host discovery:** Maintains host MAC addresses and their corresponding switch ports.
* **Path calculation:** Uses Breadth-First Search (BFS) to calculate routes between switches.
* **Flow installation:** Installs OpenFlow forwarding rules for known source and destination MAC-address pairs.
* **Link failure detection:** Detects when a network link goes down and updates the stored topology.
* **Automatic rerouting:** Calculates alternate paths and installs updated forwarding rules when a link fails.
* **Link restoration:** Detects restored links and recalculates routes using the updated topology.

When a packet arrives, the controller checks the destination MAC address. Unknown destinations are flooded, while known destinations are forwarded using calculated paths and installed flow rules.

The TCP client-server application operates over this SDN-managed network. The controller handles Ethernet packet forwarding and network path management, while the client and backup servers handle file transfer and checksum verification.

## 10. Limitations and Future Work

Possible extensions include:

* Dynamic backup-server selection based on server availability.
* Recovery from interrupted file transfers.
* Concurrent client handling.
* Performance evaluation using transfer time and throughput.
* Testing with larger files and more complex network topologies.
* More advanced routing strategies based on network performance and link conditions.

## 11. Conclusion

This project demonstrates TCP socket-based file replication across two backup servers in a Mininet-emulated network managed by an SDN controller.

It combines application-level file integrity verification with OpenFlow-based packet forwarding, topology discovery, BFS-based path calculation, link failure detection, and automatic rerouting.

The implementation demonstrates how SDN can provide dynamic network management and fault recovery while supporting a reliable file backup application.
