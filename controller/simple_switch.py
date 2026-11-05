
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet, ethernet
from os_ken.topology import event


class SimpleSwitch13(app_manager.OSKenApp):
    # Specify that this controller application uses OpenFlow 1.3
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Stores MAC addresses and their corresponding switch ports
        self.mac_to_port = {}

        # Store discovered network topology information
        self.switches = set()
        self.links = set()
        self.hosts = {}
        self.datapaths = {}

    # Calculate the shortest path between two switches using BFS
    def find_path(self, start, end):
        graph = {}

        # Build an adjacency list using the discovered network links
        # Each switch is connected to its neighbouring switches
        for src, src_port, dst, dst_port in self.links:
            graph.setdefault(src, []).append(dst)

        # BFS starts with a path containing only the source switch
        queue = [[start]]
        visited = set()

        while queue:
            # Remove the first path from the queue
            path = queue.pop(0)
            current = path[-1]

            # If the destination is reached, return the complete path
            if current == end:
                return path

            if current not in visited:
                visited.add(current)

                # Explore all unvisited neighbouring switches
                for neighbour in graph.get(current, []):
                    if neighbour not in visited:
                        new_path = path + [neighbour]
                        queue.append(new_path)

        # Return None if no path exists
        return None

    # Find the output port connecting two neighbouring switches
    def get_port(self, src_dpid, dst_dpid):
        for src, src_port, dst, dst_port in self.links:
            # Find the link from the source switch to the destination switch
            if src == src_dpid and dst == dst_dpid:
                return src_port

        return None

    # Install forwarding rules along a path between two hosts
    def install_host_path(self, src, dst, src_info, dst_info, path):
        # Extract the switch IDs and host-connected ports
        src_switch, src_port = src_info
        dst_switch, dst_port = dst_info

        first_out_port = None

        # Visit every switch in the calculated path
        for i in range(len(path)):
            current_switch = path[i]
            current_dp = self.datapaths.get(current_switch)

            # Skip if the switch datapath is not available
            if current_dp is None:
                continue

            # The last switch forwards the packet directly to the destination host
            if i == len(path) - 1:
                out_port = dst_port
            else:
                # Intermediate switches forward towards the next switch
                next_switch = path[i + 1]
                out_port = self.get_port(current_switch, next_switch)

            # Stop if the required output port cannot be found
            if out_port is None:
                self.logger.warning(
                    "Output port not found for switch %s",
                    current_switch
                )
                return None

            # Save the first switch's output port to forward the current packet
            if i == 0:
                first_out_port = out_port

            parser = current_dp.ofproto_parser

            # Match packets based on source and destination MAC addresses
            match = parser.OFPMatch(
                eth_src=src,
                eth_dst=dst
            )

            # Define the action of sending the packet through the selected port
            actions = [
                parser.OFPActionOutput(out_port)
            ]

            # Install the forwarding rule with priority 10
            self.add_flow(current_dp, 10, match, actions)

        return first_out_port

    # Delete existing priority-10 forwarding rules from all switches
    def delete_forwarding_flows(self):
        for dp in self.datapaths.values():
            parser, ofp = dp.ofproto_parser, dp.ofproto

            # Send a FlowMod DELETE message to remove old forwarding rules
            dp.send_msg(parser.OFPFlowMod(
                datapath=dp,
                cookie=1,
                cookie_mask=0xffffffffffffffff,
                command=ofp.OFPFC_DELETE,
                table_id=ofp.OFPTT_ALL,
                out_port=ofp.OFPP_ANY,
                out_group=ofp.OFPG_ANY,
                match=parser.OFPMatch(),
                instructions=[]
            ))

        self.logger.info("Deleted old forwarding rules")

    # Recalculate and install routes for all discovered host pairs
    def reroute_hosts(self):
        self.logger.info("Recalculating routes for all hosts")

        # Remove old forwarding rules that might use a failed link
        self.delete_forwarding_flows()

        # Consider every discovered host as a source
        for src, src_info in list(self.hosts.items()):

            # Consider every discovered host as a destination
            for dst, dst_info in list(self.hosts.items()):

                # A host does not need a route to itself
                if src == dst:
                    continue

                # Identify the switches to which both hosts are connected
                src_switch = src_info[0]
                dst_switch = dst_info[0]

                # Calculate a new shortest path between their switches
                path = self.find_path(src_switch, dst_switch)

                if path is None:
                    self.logger.warning(
                        "No available path between %s and %s",
                        src, dst
                    )
                    continue

                self.logger.info(
                    "New route from %s to %s: %s",
                    src, dst, path
                )

                # Install new forwarding rules along the calculated path
                self.install_host_path(
                    src, dst, src_info, dst_info, path
                )

        self.logger.info("Route recalculation completed")

    # Handle a switch's initial connection to the controller
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath

        # Store the switch datapath using its unique ID
        self.datapaths[dp.id] = dp

        parser, ofp = dp.ofproto_parser, dp.ofproto

        # Create a match that matches every packet
        match = parser.OFPMatch()

        # Send unmatched packets to the controller
        actions = [
            parser.OFPActionOutput(
                ofp.OFPP_CONTROLLER,
                ofp.OFPCML_NO_BUFFER
            )
        ]

        # Install a table-miss flow with priority 0
        self.add_flow(dp, 0, match, actions)

    # Create and install a flow entry in a switch's flow table
    def add_flow(self, dp, priority, match, actions):
        parser, ofp = dp.ofproto_parser, dp.ofproto

        # Convert the forwarding actions into OpenFlow instructions
        inst = [
            parser.OFPInstructionActions(
                ofp.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        # Cookie 1 identifies forwarding rules; cookie 0 identifies the table-miss rule
        cookie = 1 if priority == 10 else 0

        # Send a FlowMod message to install the flow entry
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp,
            cookie=cookie,
            priority=priority,
            match=match,
            instructions=inst
        ))

    # Handle packets sent from a switch to the controller
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        parser, ofp = dp.ofproto_parser, dp.ofproto

        # Identify the switch port on which the packet arrived
        in_port = msg.match['in_port']

        # Extract the Ethernet header from the received packet
        eth = packet.Packet(msg.data).get_protocol(ethernet.ethernet)

        if eth is None:
            return

        # Ignore LLDP packets because they are used for topology discovery
        if eth.ethertype == 0x88cc:
            return

        # Extract the source and destination MAC addresses
        src, dst = eth.src, eth.dst

        # If the destination host is unknown, flood the packet
        if dst not in self.hosts:
            actions = [
                parser.OFPActionOutput(ofp.OFPP_FLOOD)
            ]

            # Include packet data only if the switch has not buffered it
            data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None

            # Send the packet out through all eligible switch ports
            dp.send_msg(parser.OFPPacketOut(
                datapath=dp,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data
            ))
            return

        # Stop processing if the source host is not known
        if src not in self.hosts:
            self.logger.warning("Source host %s is not known", src)
            return

        # Retrieve the switch and port information of both hosts
        src_info = self.hosts[src]
        dst_info = self.hosts[dst]

        src_switch = src_info[0]
        dst_switch = dst_info[0]

        # Calculate the shortest path between the switches connected to the hosts
        path = self.find_path(src_switch, dst_switch)

        if path is None:
            self.logger.warning("No path found between hosts")
            return

        self.logger.info(
            "Host path from %s to %s: %s",
            src, dst, path
        )

        # Install forwarding rules on every switch along the calculated path
        out_port = self.install_host_path(
            src, dst, src_info, dst_info, path
        )

        if out_port is None:
            return

        # Only the first switch should forward this PacketIn packet
        if path[0] != dp.id:
            return

        actions = [
            parser.OFPActionOutput(out_port)
        ]

        # Include packet data only if it is not already buffered
        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None

        # Send the current packet through the calculated output port
        dp.send_msg(parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        ))

    # Detect a switch joining the network
    @set_ev_cls(event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        switch = ev.switch
        dpid = switch.dp.id

        # Add the newly discovered switch to the switch set
        self.switches.add(dpid)
        self.logger.info("Switch discovered: %s", dpid)

    # Detect a switch leaving the network
    @set_ev_cls(event.EventSwitchLeave)
    def switch_leave_handler(self, ev):
        switch = ev.switch
        dpid = switch.dp.id

        # Remove the departed switch from the discovered switch set
        self.switches.discard(dpid)

        # Remove all links connected to the departed switch
        self.links = {
            link for link in self.links
            if link[0] != dpid and link[2] != dpid
        }

        self.logger.info("Switch left: %s", dpid)

        # Recalculate routes because the network topology has changed
        self.reroute_hosts()

    # Detect a link being added
    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        link = ev.link

        # Extract the source and destination switch IDs and port numbers
        src_dpid = link.src.dpid
        src_port = link.src.port_no
        dst_dpid = link.dst.dpid
        dst_port = link.dst.port_no

        # Store link information as (source switch, source port, destination switch, destination port)
        link_info = (src_dpid, src_port, dst_dpid, dst_port)

        # Ignore duplicate link events
        if link_info in self.links:
            return

        # Add the newly discovered link to the topology
        self.links.add(link_info)

        self.logger.info(
            "LINK RESTORED: switch %s port %s -> switch %s port %s",
            src_dpid, src_port, dst_dpid, dst_port
        )

        self.logger.info("Updated network links: %s", self.links)

        # Recalculate routes using the updated network topology
        self.reroute_hosts()

    # Detect a link being removed
    @set_ev_cls(event.EventLinkDelete)
    def link_delete_handler(self, ev):
        link = ev.link

        # Extract the source and destination switch IDs and port numbers
        src_dpid = link.src.dpid
        src_port = link.src.port_no
        dst_dpid = link.dst.dpid
        dst_port = link.dst.port_no

        # Represent the link in both directions
        link_info = (src_dpid, src_port, dst_dpid, dst_port)
        reverse_link = (dst_dpid, dst_port, src_dpid, src_port)

        # Avoid processing the same link failure more than once
        if link_info not in self.links and reverse_link not in self.links:
            return

        # Remove both directions of the failed link from the topology
        self.links.discard(link_info)
        self.links.discard(reverse_link)

        self.logger.warning(
            "LINK FAILURE: switch %s port %s -> switch %s port %s",
            src_dpid, src_port, dst_dpid, dst_port
        )

        self.logger.info("Updated network links: %s", self.links)

        # Check whether another path exists between the affected switches
        path = self.find_path(src_dpid, dst_dpid)

        if path:
            self.logger.info("Alternate path found: %s", path)
        else:
            self.logger.warning(
                "No alternate path between switch %s and switch %s",
                src_dpid, dst_dpid
            )

        # Automatically recalculate and install forwarding rules
        self.reroute_hosts()

    # Detect a host joining the network
    @set_ev_cls(event.EventHostAdd)
    def host_add_handler(self, ev):
        host = ev.host

        # Extract the host's MAC address and its connected switch and port
        mac = host.mac
        switch = host.port.dpid
        port = host.port.port_no

        # Store the host's location in the host dictionary
        self.hosts[mac] = (switch, port)

        self.logger.info(
            "Host discovered: %s connected to switch %s port %s",
            mac, switch, port
        )
