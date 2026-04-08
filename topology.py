#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.link import TCLink
import time


def run_topology():
    net = Mininet(controller=RemoteController, switch=OVSSwitch, link=TCLink)

    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    h1 = net.addHost('h1')
    h2 = net.addHost('h2')
    h3 = net.addHost('h3')
    h4 = net.addHost('h4')

    s1 = net.addSwitch('s1')

    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(h4, s1)

    net.build()
    c0.start()
    s1.start([c0])

    time.sleep(1)

    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run_topology()
