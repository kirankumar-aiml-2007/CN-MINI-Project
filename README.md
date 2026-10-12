# TCP-Based File Backup System Using Mininet and SDN

## 1. Project Overview

This project implements a TCP-based file backup system in which a client transfers a file to two backup servers over a software-defined network (SDN).

The application uses TCP socket programming to transfer files reliably. The receiving servers store the files and verify their integrity using SHA-256 checksums.

The network is emulated using Mininet, with Open vSwitch (OVS) switches managed by an SDN controller running OS-Ken. The controller implements learning-switch forwarding using OpenFlow 1.3.

## 2. Objectives

* Implement file transfer using TCP sockets.
* Replicate a file across multiple backup servers.
* Verify file integrity using SHA-256 checksums.
* Deploy and test the application in a Mininet network.
* Use an SDN controller to manage packet forwarding through OpenFlow switches.
* Demonstrate end-to-end communication between the client and both backup servers.

## 3. System Architecture

The system consists of one client, two backup servers, two OpenFlow switches, and an SDN controller.

```text
                 SDN Controller
                      OS-Ken
                        |
                  OpenFlow 1.3
                        |
                     Switch S1
                        |
                     Switch S2
                    /        \
             Switch port   Switch port
                 |              |
          Backup Server 1  Backup Server 2
              (h2)             (h3)
           10.0.0.2          10.0.0.3
                    \        /
                     Switch S2
                        |
                  Switch S1
                        |
                  Client (h1)
                   10.0.0.1
```

### Network topology

The Mininet topology connects the client host h1 to switch S1, which connects to switch S2. The two backup servers, h2 and h3, connect to S2.

| Component | Description           | IP address     |
| --------- | --------------------- | -------------- |
| h1        | TCP client            | 10.0.0.1       |
| h2        | Backup server 1       | 10.0.0.2       |
| h3        | Backup server 2       | 10.0.0.3       |
| s1        | OpenFlow switch       | N/A            |
| s2        | OpenFlow switch       | N/A            |
| c0        | OS-Ken SDN controller | 127.0.0.1:6653 |

## 4. Technologies Used

* Python 3
* TCP socket programming
* SHA-256 checksum verification
* Mininet
* Open vSwitch (OVS)
* OS-Ken SDN controller
* OpenFlow 1.3
* Linux / Ubuntu

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

Run the following components in the order described below.

### Step 1: Start the SDN controller

Open a terminal in the project directory:

```bash
source .venv/bin/activate
python controller/run_controller.py controller/simple_switch.py
```

Keep the controller running. It listens for OpenFlow connections on port 6653.

### Step 2: Start the Mininet topology

Open a second terminal:

```bash
sudo mn -c
sudo /usr/bin/python3 mininet/topo.py
```

Wait for the `mininet>` prompt.

### Step 3: Verify network connectivity

At the Mininet prompt, run:

```text
pingall
```

The expected result for a successful connectivity test is:

```text
*** Results: 0% dropped (6/6 received)
```

### Step 4: Start the backup servers

Start one TCP server in host h2 and another in host h3. Run these commands at the Mininet prompt:

```text
h2 sh -c 'cd /home/keerthanavijunair/Downloads/CN-MINI-Project-clean && python3 -m server.server 10.0.0.2 5000 backup/h2' &
```

```text
h3 sh -c 'cd /home/keerthanavijunair/Downloads/CN-MINI-Project-clean && python3 -m server.server 10.0.0.3 5000 backup/h3' &
```

Wait until both servers report that they are listening for client connections.

**Note:** Replace `/home/keerthanavijunair/Downloads/CN-MINI-Project-clean` with the absolute path of your cloned repository on your own system.

### Step 5: Run the client

At the Mininet prompt, run:

```text
h1 python3 -m client.client tests/test_small.txt 10.0.0.2:5000 10.0.0.3:5000
```

The client sends the selected file to both backup servers and reports the outcome of each transfer.

## 8. Testing and Verification

The project can be demonstrated through the following tests:

1. **Network connectivity:** Use `pingall` to check connectivity between the three Mininet hosts.

2. **Controller connectivity:** Use `sudo ovs-vsctl show` to verify that both switches are connected to the controller.

3. **OpenFlow forwarding rules:** Inspect the flow tables using:

   ```bash
   sudo ovs-ofctl -O OpenFlow13 dump-flows s1
   sudo ovs-ofctl -O OpenFlow13 dump-flows s2
   ```

4. **File backup:** Transfer `tests/test_small.txt` to both backup servers.

5. **Integrity verification:** Check that the client reports successful storage and checksum verification for each server.

### Expected result

For a successful transfer to both servers, the client should report:

```text
SUMMARY
10.0.0.2:5000   OK    stored and verified
10.0.0.3:5000   OK    stored and verified

2/2 backups verified
```

The exact output may vary depending on the file, environment, and server responses.

## 9. SDN Integration

The network uses OpenFlow 1.3 switches managed by the OS-Ken controller.

The controller implements learning-switch behavior by learning source MAC addresses and their corresponding switch ports. Unknown destination addresses are flooded, while forwarding rules are installed for known source and destination MAC-address pairs.

The TCP client-server application operates over this SDN-managed network. The controller manages Ethernet packet forwarding, while the client and servers handle file transfer and checksum verification.

The current implementation uses learning-switch forwarding. Dynamic backup-server selection, controller-driven failover, and performance comparisons are not claimed as implemented features.

## 10. Limitations and Future Work

Possible extensions include:

* Dynamic backup-server selection based on server availability.
* SDN-driven failover and path management.
* Recovery from interrupted transfers.
* Concurrent client handling and larger-scale testing.
* Performance evaluation using transfer time, throughput, and failure scenarios.

## 11. Conclusion

This project demonstrates TCP socket-based file replication across two backup servers in a Mininet-emulated network managed by an SDN controller. It combines application-level file integrity verification with OpenFlow-based packet forwarding and provides a reproducible environment for further experiments in networked applications and SDN.
