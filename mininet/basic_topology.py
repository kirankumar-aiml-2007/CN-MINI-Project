from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def create_topology():

    # Create Mininet without an external controller.
    # OVS will operate as a standalone Layer-2 switch.
    net = Mininet(
        controller=None,
        switch=OVSSwitch
    )

    info("*** Adding hosts\n")

    # h1 = TCP Client
    h1 = net.addHost(
        "h1",
        ip="10.0.0.1/24"
    )

    # h2 = TCP Server
    h2 = net.addHost(
        "h2",
        ip="10.0.0.2/24"
    )

    info("*** Adding switch\n")

    # Standalone OVS switch
    s1 = net.addSwitch(
        "s1",
        failMode="standalone"
    )

    info("*** Adding links\n")

    net.addLink(h1, s1)
    net.addLink(h2, s1)

    info("*** Starting network\n")

    net.start()

    info("*** Testing connectivity\n")

    result = h1.cmd("ping -c 2 10.0.0.2")

    print(result)

    info("*** Starting Mininet CLI\n")

    CLI(net)

    info("*** Stopping network\n")

    net.stop()


if __name__ == "__main__":

    setLogLevel("info")

    create_topology()
