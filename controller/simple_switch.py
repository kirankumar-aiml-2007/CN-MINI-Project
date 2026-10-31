
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet, ethernet
from os_ken.topology import event


class SimpleSwitch13(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}

        # Store discovered network topology
        self.switches = set()
        self.links = set()
        self.hosts = {}
        self.datapaths = {}

    # Calculate the shortest path between two switches using BFS
    def find_path(self, start, end):
        graph = {}

        # Build the network graph using discovered links
        for src, src_port, dst, dst_port in self.links:
            graph.setdefault(src, []).append(dst)

        queue = [[start]]
        visited = set()

        while queue:
            path = queue.pop(0)
            current = path[-1]

            if current == end:
                return path

            if current not in visited:
                visited.add(current)

                for neighbour in graph.get(current, []):
                    if neighbour not in visited:
                        new_path = path + [neighbour]
                        queue.append(new_path)

        return None

    # Find the output port connecting two neighbouring switches
    def get_port(self, src_dpid, dst_dpid):
        for src, src_port, dst, dst_port in self.links:
            if src == src_dpid and dst == dst_dpid:
                return src_port

        return None

    # Install forwarding rules along a path between two hosts
    def install_host_path(self, src, dst, src_info, dst_info, path):
        src_switch, src_port = src_info
        dst_switch, dst_port = dst_info

        first_out_port = None

        for i in range(len(path)):
            current_switch = path[i]
            current_dp = self.datapaths.get(current_switch)

            if current_dp is None:
                continue

            # Last switch sends packet to destination host
            if i == len(path) - 1:
                out_port = dst_port
            else:
                next_switch = path[i + 1]
                out_port = self.get_port(current_switch, next_switch)

            if out_port is None:
                self.logger.warning(
                    "Output port not found for switch %s",
                    current_switch
                )
                return None

            if i == 0:
                first_out_port = out_port

            parser = current_dp.ofproto_parser

            match = parser.OFPMatch(
                eth_src=src,
                eth_dst=dst
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(current_dp, 10, match, actions)

        return first_out_port

    # Delete existing priority-10 forwarding rules from all switches
    def delete_forwarding_flows(self):
        for dp in self.datapaths.values():
            parser, ofp = dp.ofproto_parser, dp.ofproto

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

        # Remove forwarding rules that may use the failed link
        self.delete_forwarding_flows()

        for src, src_info in list(self.hosts.items()):
            for dst, dst_info in list(self.hosts.items()):

                if src == dst:
                    continue

                src_switch = src_info[0]
                dst_switch = dst_info[0]

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

                self.install_host_path(
                    src, dst, src_info, dst_info, path
                )

        self.logger.info("Route recalculation completed")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp

        parser, ofp = dp.ofproto_parser, dp.ofproto
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofp.OFPP_CONTROLLER,
                ofp.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(dp, 0, match, actions)

    def add_flow(self, dp, priority, match, actions):
        parser, ofp = dp.ofproto_parser, dp.ofproto

        inst = [
            parser.OFPInstructionActions(
                ofp.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        cookie = 1 if priority == 10 else 0

        dp.send_msg(parser.OFPFlowMod(
            datapath=dp,
            cookie=cookie,
            priority=priority,
            match=match,
            instructions=inst
        ))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        parser, ofp = dp.ofproto_parser, dp.ofproto
        in_port = msg.match['in_port']

        eth = packet.Packet(msg.data).get_protocol(ethernet.ethernet)

        if eth is None:
            return

        # Ignore LLDP packets used for topology discovery
        if eth.ethertype == 0x88cc:
            return

        src, dst = eth.src, eth.dst

        # Check whether the destination host is known
        if dst not in self.hosts:
            actions = [
                parser.OFPActionOutput(ofp.OFPP_FLOOD)
            ]

            data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None

            dp.send_msg(parser.OFPPacketOut(
                datapath=dp,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data
            ))
            return

        if src not in self.hosts:
            self.logger.warning("Source host %s is not known", src)
            return

        src_info = self.hosts[src]
        dst_info = self.hosts[dst]

        src_switch = src_info[0]
        dst_switch = dst_info[0]

        # Calculate the path between the host switches
        path = self.find_path(src_switch, dst_switch)

        if path is None:
            self.logger.warning("No path found between hosts")
            return

        self.logger.info(
            "Host path from %s to %s: %s",
            src, dst, path
        )

        # Install forwarding rules along the calculated path
        out_port = self.install_host_path(
            src, dst, src_info, dst_info, path
        )

        if out_port is None:
            return

        # Send the current packet from the first switch
        if path[0] != dp.id:
            return

        actions = [
            parser.OFPActionOutput(out_port)
        ]

        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None

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

        self.switches.add(dpid)
        self.logger.info("Switch discovered: %s", dpid)

    # Detect a switch leaving the network
    @set_ev_cls(event.EventSwitchLeave)
    def switch_leave_handler(self, ev):
        switch = ev.switch
        dpid = switch.dp.id

        self.switches.discard(dpid)

        # Remove links connected to the departed switch
        self.links = {
            link for link in self.links
            if link[0] != dpid and link[2] != dpid
        }

        self.logger.info("Switch left: %s", dpid)

        self.reroute_hosts()

    # Detect a link being added
    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        link = ev.link

        src_dpid = link.src.dpid
        src_port = link.src.port_no
        dst_dpid = link.dst.dpid
        dst_port = link.dst.port_no

        link_info = (src_dpid, src_port, dst_dpid, dst_port)

        # Ignore duplicate link events
        if link_info in self.links:
            return

        self.links.add(link_info)

        self.logger.info(
            "LINK RESTORED: switch %s port %s -> switch %s port %s",
            src_dpid, src_port, dst_dpid, dst_port
        )

        self.logger.info("Updated network links: %s", self.links)

        # Recalculate routes using the updated topology
        self.reroute_hosts()

    # Detect a link being removed
    @set_ev_cls(event.EventLinkDelete)
    def link_delete_handler(self, ev):
        link = ev.link

        src_dpid = link.src.dpid
        src_port = link.src.port_no
        dst_dpid = link.dst.dpid
        dst_port = link.dst.port_no

        link_info = (src_dpid, src_port, dst_dpid, dst_port)
        reverse_link = (dst_dpid, dst_port, src_dpid, src_port)

        # Avoid processing the same link failure twice
        if link_info not in self.links and reverse_link not in self.links:
            return

        self.links.discard(link_info)
        self.links.discard(reverse_link)

        self.logger.warning(
            "LINK FAILURE: switch %s port %s -> switch %s port %s",
            src_dpid, src_port, dst_dpid, dst_port
        )

        self.logger.info("Updated network links: %s", self.links)

        # Check whether an alternate path still exists
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

        mac = host.mac
        switch = host.port.dpid
        port = host.port.port_no

        self.hosts[mac] = (switch, port)

        self.logger.info(
            "Host discovered: %s connected to switch %s port %s",
            mac, switch, port
        )
