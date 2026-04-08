#!/usr/bin/env python3

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet
import time
from collections import defaultdict


class BroadcastController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(BroadcastController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.broadcast_history = defaultdict(list)
        self.THRESHOLD = 10
        self.TIME_WINDOW = 5
        self.total_packets = 0
        self.broadcasts_allowed = 0
        self.broadcasts_blocked = 0
        self.unicast_flows = 0

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                         ofproto.OFPCML_NO_BUFFER)]

        self.add_flow(datapath, 0, match, actions)
        self.logger.info("[+] Switch connected: dpid=%s", datapath.id)

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]

        mod = parser.OFPFlowMod(datapath=datapath,
                               priority=priority,
                               match=match,
                               instructions=inst,
                               idle_timeout=idle_timeout)

        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        dst = eth.dst
        src = eth.src

        self.total_packets += 1
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        is_broadcast = (dst == 'ff:ff:ff:ff:ff:ff') or dst.startswith('33:33')

        if is_broadcast:
            now = time.time()
            history = self.broadcast_history[src]
            history.append(now)
            history[:] = [t for t in history if now - t <= self.TIME_WINDOW]

            if len(history) > self.THRESHOLD:
                self.broadcasts_blocked += 1
                self.logger.info("[BLOCK] Broadcast rate exceeded: dpid=%s src=%s", dpid, src)

                match = parser.OFPMatch(eth_src=src)
                actions = []

                self.add_flow(datapath, 20, match, actions)
                self.logger.info("[DROP-RULE] Installed drop rule for src=%s on dpid=%s", src, dpid)
                return
            else:
                self.broadcasts_allowed += 1
                out_port = ofproto.OFPP_FLOOD

        else:
            if dst in self.mac_to_port[dpid]:
                out_port = self.mac_to_port[dpid][dst]

                match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
                actions = [parser.OFPActionOutput(out_port)]

                self.add_flow(datapath, 10, match, actions, idle_timeout=30)
                self.unicast_flows += 1

                self.logger.info("[UNICAST] dpid=%s src=%s -> dst=%s out_port=%s (installing flow)",
                                 dpid, src, dst, out_port)
            else:
                out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath,
                                 buffer_id=msg.buffer_id,
                                 in_port=in_port,
                                 actions=actions,
                                 data=data)

        datapath.send_msg(out)
