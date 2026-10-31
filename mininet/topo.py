
#!/usr/bin/env python3
"""
Topology:

              s1
             /  \
            /    \
           s2----s3
          /        \
         h2         h3

h1 (client) connects to s1.

There are two paths between s1 and s2:
    1. s1 -> s2
    2. s1 -> s3 -> s2

Run the controller first:
    python controller/run_controller.py controller/simple_switch.py

Then:
    sudo mn -c
    sudo python3 mininet/topo.py
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel


def build():
    net = Mininet(controller=None, switch=OVSSwitch, autoSetMacs=True)

    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653
    )

    # Hosts
    h1 = net.addHost("h1", ip="10.0.0.1/24")
    h2 = net.addHost("h2", ip="10.0.0.2/24")
    h3 = net.addHost("h3", ip="10.0.0.3/24")

    # Switches
    s1 = net.addSwitch("s1", protocols="OpenFlow13")
    s2 = net.addSwitch("s2", protocols="OpenFlow13")
    s3 = net.addSwitch("s3", protocols="OpenFlow13")

    # Host connections
    net.addLink(h1, s1)
    net.addLink(s2, h2)
    net.addLink(s2, h3)

    # Primary path
    net.addLink(s1, s2)

    # Redundant path
    net.addLink(s1, s3)
    net.addLink(s3, s2)

    return net


if __name__ == "__main__":
    setLogLevel("info")

    net = build()
    net.start()

    CLI(net)

    net.stop()
