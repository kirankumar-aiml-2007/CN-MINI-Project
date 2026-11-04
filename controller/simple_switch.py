
from collections import deque

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet, ethernet
from os_ken.topology import event


class SimpleSwitch13(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.switches = set()
        self.links = set()
        self.hosts = {}
        self.datapaths = {}

    def get_graph(self):
        graph = {}

        for src, src_port, dst, dst_port in self.links:
            graph.setdefault(src, {})[dst] = src_port
            graph.setdefault(dst, {})[src] = dst_port

        return graph

    def find_path(self, start, end):
        graph = self.get_graph()
        queue = deque([[start]])
        visited = {start}

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == end:
                return path

            for neighbour in sorted(graph.get(current, {})):
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(path + [neighbour])

        return None

    def get_port(self, src_dpid, dst_dpid):
        return self.get_graph().get(src_dpid, {}).get(dst_dpid)

    def is_switch_port(self, dpid, port_no):
        return port_no in self.get_graph().get(dpid, {}).values()

    def learn_host(self, mac, dpid, port_no):
        if not mac or dpid not in self.datapaths:
            return False

        ofp = self.datapaths[dpid].ofproto

        if port_no >= ofp.OFPP_MAX:
            return False

        if self.is_switch_port(dpid, port_no):
            return False

        first_octet = int(mac.split(":")[0], 16)

        if first_octet & 1:
            return False

        host_info = (dpid, port_no)

        if self.hosts.get(mac) == host_info:
            return False

        self.hosts[mac] = host_info

        self.logger.info(
            "Host learned: %s on switch %s port %s",
            mac,
            dpid,
            port_no
        )

        return True

    def get_broadcast_tree(self):
        graph = self.get_graph()
        nodes = set(graph)

        if not nodes:
            return set()

        root = min(nodes)
        visited = {root}
        queue = deque([root])
        tree_edges = set()

        while queue:
            current = queue.popleft()

            for neighbour in sorted(graph.get(current, {})):
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)
                    tree_edges.add(frozenset((current, neighbour)))

        return tree_edges

    def flood_broadcast(self, msg, dp, in_port):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        dpid = dp.id

        graph = self.get_graph()
        tree_edges = self.get_broadcast_tree()

        switch_ports = set(graph.get(dpid, {}).values())
        output_ports = set()

        for neighbour, port_no in graph.get(dpid, {}).items():
            edge = frozenset((dpid, neighbour))

            if edge in tree_edges:
                output_ports.add(port_no)

        host_ports = set(getattr(dp, "ports", {}).keys()) - switch_ports

        output_ports.update(host_ports)
        output_ports.discard(in_port)

        actions = [
            parser.OFPActionOutput(port_no)
            for port_no in sorted(output_ports)
            if port_no < ofp.OFPP_MAX
        ]

        if not actions:
            return

        data = (
            msg.data
            if msg.buffer_id == ofp.OFP_NO_BUFFER
            else None
        )

        dp.send_msg(
            parser.OFPPacketOut(
                datapath=dp,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data
            )
        )

    def add_flow(self, dp, priority, match, actions):
        parser = dp.ofproto_parser
        ofp = dp.ofproto

        instructions = [
            parser.OFPInstructionActions(
                ofp.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        cookie = 1 if priority == 10 else 0

        dp.send_msg(
            parser.OFPFlowMod(
                datapath=dp,
                cookie=cookie,
                priority=priority,
                match=match,
                instructions=instructions
            )
        )

    def install_host_path(self, src, dst, src_info, dst_info, path):
        if not path:
            return None

        dst_switch, dst_port = dst_info

        for index, current_switch in enumerate(path):
            dp = self.datapaths.get(current_switch)

            if dp is None:
                return None

            if index == len(path) - 1:
                out_port = dst_port
            else:
                out_port = self.get_port(
                    current_switch,
                    path[index + 1]
                )

            if out_port is None:
                return None

            parser = dp.ofproto_parser

            match = parser.OFPMatch(
                eth_src=src,
                eth_dst=dst
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(dp, 10, match, actions)

        return True

    def delete_forwarding_flows(self):
        for dp in self.datapaths.values():
            parser = dp.ofproto_parser
            ofp = dp.ofproto

            dp.send_msg(
                parser.OFPFlowMod(
                    datapath=dp,
                    cookie=1,
                    cookie_mask=0xffffffffffffffff,
                    command=ofp.OFPFC_DELETE,
                    table_id=ofp.OFPTT_ALL,
                    out_port=ofp.OFPP_ANY,
                    out_group=ofp.OFPG_ANY,
                    match=parser.OFPMatch(),
                    instructions=[]
                )
            )

    def reroute_hosts(self):
        self.logger.info("Recalculating routes")

        self.delete_forwarding_flows()

        for src, src_info in list(self.hosts.items()):
            for dst, dst_info in list(self.hosts.items()):

                if src == dst:
                    continue

                path = self.find_path(
                    src_info[0],
                    dst_info[0]
                )

                if path is None:
                    self.logger.warning(
                        "No route between %s and %s",
                        src,
                        dst
                    )
                    continue

                result = self.install_host_path(
                    src,
                    dst,
                    src_info,
                    dst_info,
                    path
                )

                if result:
                    self.logger.info(
                        "Route %s -> %s: %s",
                        src,
                        dst,
                        path
                    )

        self.logger.info("Route recalculation completed")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        self.switches.add(dp.id)

        parser = dp.ofproto_parser
        ofp = dp.ofproto

        match = parser.OFPMatch()

        actions = [
            parser.OFPActionOutput(
                ofp.OFPP_CONTROLLER,
                ofp.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(dp, 0, match, actions)

        self.logger.info("Switch connected: %s", dp.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        parser = dp.ofproto_parser
        ofp = dp.ofproto

        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        if eth.ethertype == 0x88cc:
            return

        src = eth.src
        dst = eth.dst

        if self.learn_host(src, dp.id, in_port):
            self.reroute_hosts()

        first_octet = int(dst.split(":")[0], 16)

        if first_octet & 1:
            self.flood_broadcast(msg, dp, in_port)
            return

        if src not in self.hosts or dst not in self.hosts:
            return

        src_info = self.hosts[src]
        dst_info = self.hosts[dst]

        path = self.find_path(
            src_info[0],
            dst_info[0]
        )

        if not path:
            self.logger.warning(
                "No path between %s and %s",
                src,
                dst
            )
            return

        self.install_host_path(
            src,
            dst,
            src_info,
            dst_info,
            path
        )

        if dp.id not in path:
            return

        index = path.index(dp.id)

        if index == len(path) - 1:
            out_port = dst_info[1]
        else:
            out_port = self.get_port(
                dp.id,
                path[index + 1]
            )

        if out_port is None or out_port == in_port:
            return

        actions = [
            parser.OFPActionOutput(out_port)
        ]

        data = (
            msg.data
            if msg.buffer_id == ofp.OFP_NO_BUFFER
            else None
        )

        dp.send_msg(
            parser.OFPPacketOut(
                datapath=dp,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data
            )
        )

    @set_ev_cls(event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        dp = ev.switch.dp
        self.switches.add(dp.id)
        self.logger.info("Switch discovered: %s", dp.id)

    @set_ev_cls(event.EventSwitchLeave)
    def switch_leave_handler(self, ev):
        dpid = ev.switch.dp.id

        self.switches.discard(dpid)
        self.datapaths.pop(dpid, None)

        self.links = {
            link for link in self.links
            if link[0] != dpid and link[2] != dpid
        }

        self.hosts = {
            mac: info
            for mac, info in self.hosts.items()
            if info[0] != dpid
        }

        self.logger.warning("Switch disconnected: %s", dpid)
        self.reroute_hosts()

    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        link = ev.link

        src = link.src.dpid
        src_port = link.src.port_no
        dst = link.dst.dpid
        dst_port = link.dst.port_no

        link_info = (src, src_port, dst, dst_port)
        reverse = (dst, dst_port, src, src_port)

        changed = link_info not in self.links

        self.links.add(link_info)
        self.links.add(reverse)

        if changed:
            self.logger.info(
                "LINK RESTORED: %s <-> %s",
                src,
                dst
            )
            self.reroute_hosts()

    @set_ev_cls(event.EventLinkDelete)
    def link_delete_handler(self, ev):
        link = ev.link

        src = link.src.dpid
        src_port = link.src.port_no
        dst = link.dst.dpid
        dst_port = link.dst.port_no

        link_info = (src, src_port, dst, dst_port)
        reverse = (dst, dst_port, src, src_port)

        if link_info not in self.links and reverse not in self.links:
            return

        self.links.discard(link_info)
        self.links.discard(reverse)

        self.logger.warning(
            "LINK FAILURE: %s <-> %s",
            src,
            dst
        )

        path = self.find_path(src, dst)

        if path:
            self.logger.info("Alternate path found: %s", path)
        else:
            self.logger.warning("No alternate path available")

        self.reroute_hosts()

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto

        port_no = msg.desc.port_no

        is_down = (
            msg.reason == ofp.OFPPR_DELETE
            or bool(msg.desc.state & ofp.OFPPS_LINK_DOWN)
        )

        if not is_down:
            return

        removed = {
            link for link in self.links
            if (
                link[0] == dp.id and link[1] == port_no
            ) or (
                link[2] == dp.id and link[3] == port_no
            )
        }

        if not removed:
            return

        self.links.difference_update(removed)

        self.logger.warning(
            "PORT DOWN: switch %s port %s",
            dp.id,
            port_no
        )

        self.reroute_hosts()

    @set_ev_cls(event.EventHostAdd)
    def host_add_handler(self, ev):
        host = ev.host

        if self.learn_host(
            host.mac,
            host.port.dpid,
            host.port.port_no
        ):
            self.reroute_hosts()
