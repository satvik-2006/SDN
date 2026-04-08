# Broadcast Traffic Control using SDN (Mininet + Ryu)

## Problem Statement

In a normal Ethernet network, broadcast traffic gets flooded out of every switch port — that's just how it works. ARP requests, unknown unicast, all of it. The problem is when this gets out of hand. A single host spamming broadcast frames can kill network performance pretty quickly, and traditional switches have no real way to stop it since they don't have any application-level intelligence.

This project builds an SDN-based fix for that using Mininet and a Ryu OpenFlow controller. The idea is:
- The controller intercepts every unmatched packet via `packet_in`
- It learns MAC-to-port mappings on the fly
- If a host starts sending too many broadcasts (more than 10 in 5 seconds), the controller pushes a DROP rule to the switch directly
- For normal traffic, it installs efficient unicast forwarding rules so packets stop going through the controller every time

The interesting part is watching the flow table change in real time — you can literally see the controller respond to a broadcast storm and shut it down.

---

## Topology

```
  h1 (10.0.0.1) ──┐
  h2 (10.0.0.2) ──┤
                   s1 ──── Ryu Controller (127.0.0.1:6653)
  h3 (10.0.0.3) ──┤
  h4 (10.0.0.4) ──┘
```

One OVS switch (`s1`) running OpenFlow 1.3, four hosts, one remote Ryu controller. Simple star topology — easy to observe what the switch is actually doing.

---

## SDN Logic

### How packet_in Works

Every packet that doesn't match an existing flow rule gets sent to the controller. Here's what the controller does with it:

1. Learns the source MAC and which port it came in on (MAC learning table)
2. Checks if the destination is a broadcast address (`ff:ff:ff:ff:ff:ff` or starts with `33:33`)
3. If it's a broadcast, checks whether that source has exceeded the rate limit — more than 10 broadcasts in a 5 second sliding window
4. If the rate is exceeded: installs a DROP rule at priority 20 for that source MAC, returns immediately
5. If the broadcast is fine: floods it out all ports (`OFPP_FLOOD`)
6. If it's a known unicast destination: installs a specific forwarding rule (priority 10) so future packets skip the controller entirely

### Flow Rule Table

| Priority | Match | Action | Timeout |
|----------|-------|--------|---------|
| 0 | everything (table-miss) | Send to controller | permanent |
| 10 | `eth_src` + `eth_dst` | Output to learned port | idle=30s |
| 20 | `eth_src` (flooder) | DROP | idle=5s |

The priority ordering matters here — the drop rule at 20 overrides the table-miss rule at 0, so blocked hosts get dropped at the switch without ever reaching the controller again.

---

## Setup

### Prerequisites

```bash
sudo apt-get install mininet
pip install ryu
sudo apt-get install iperf arping
```

### Step 1 — Start the Ryu Controller

```bash
ryu-manager broadcast_controller.py --verbose --observe-links
```

Keep this terminal open. All the interesting logs show up here.

### Step 2 — Start the Mininet Topology

Open a new terminal:

```bash
sudo python3 topology.py
```

This builds the network and drops you into the Mininet CLI. The controller and switch should connect automatically — you'll see `[+] Switch connected: dpid=1` in the Ryu terminal.

---

## Test Scenarios

### Scenario 1 — Normal Operation

```bash
mininet> pingall
```

First ping triggers ARP (broadcast) which gets flooded and the MACs get learned. After that, the controller installs unicast rules and packets go directly host-to-host without involving the controller.

Expected: 0% packet loss, and you should see `[UNICAST]` entries appearing in the controller logs as flow rules get installed.

```bash
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

After `pingall`, the flow table should have priority=10 unicast rules in addition to the default table-miss rule.

---

### Scenario 2 — Broadcast Storm

From an xterm on h3 (or a separate terminal):

```bash
mininet> xterm h3
# In the h3 xterm:
python3 broadcast_storm_test.py --iface h3-eth0
```

This sends 60 broadcast frames at 20 packets/second. The first 10 go through fine, then the controller fires:

```
[BLOCK] Broadcast rate exceeded: dpid=1 src=ce:58:e3:f3:d6:16
[DROP-RULE] Installed drop rule for src=ce:58:e3:f3:d6:16 on dpid=1
```

After that, the switch drops everything from h3 locally without any controller involvement. You can verify with:

```bash
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

Look for `priority=20, actions=drop`.

---

### Scenario 3 — Throughput Test

```bash
mininet> h2 iperf -s &
mininet> h1 iperf -c 10.0.0.2 -t 10
```

Once unicast flow rules are in place, throughput between h1 and h2 should be close to the link capacity.

---

## Proof of Execution

### Screenshot 1 — pingall (0% packet loss)
All 4 hosts can reach each other. 12/12 pings received.

<img width="320" height="94" alt="Screenshot_2" src="https://github.com/user-attachments/assets/d106a760-f3fc-453b-ae1e-71affb7b1c0b" />


### Screenshot 2 — Controller Logs: MAC Learning + Unicast Flows + Stats
Shows the `[LEARN]`, `[FLOOD]`, and `[UNICAST]` log entries as the controller builds its MAC table and installs forwarding rules. Stats at the bottom confirm packet counts.

<img width="1258" height="670" alt="Screenshot_3" src="https://github.com/user-attachments/assets/5d1deca0-47c9-4f7f-83e6-3415c49cb1dd" />


### Screenshot 3 — Broadcast Storm Test Running
The `broadcast_storm_test.py` script running on h3, sending all 60 frames.!

<img width="465" height="85" alt="Screenshot_4" src="https://github.com/user-attachments/assets/ecb88978-501d-4d5f-be3c-731ec862063b" />


### Screenshot 4 — Controller Detects and Blocks the Storm
First 10 broadcasts get `[FLOOD]`, then the controller fires `[BLOCK]` and installs the drop rule. This is the core SDN logic working.

<img width="1225" height="626" alt="Screenshot_5" src="https://github.com/user-attachments/assets/71af4f12-0534-44ca-9c68-f1da42161915" />


### Screenshot 5 — Flow Table with Drop Rule
`ovs-ofctl dump-flows s1` showing the `priority=20, actions=drop` rule installed by the controller.

<img width="627" height="54" alt="Screenshot_6" src="https://github.com/user-attachments/assets/0e18864b-381c-414d-890c-9867227f3832" />

### Screenshot 6 — Controller Startup and Initial Packet Processing
Shows the switch connecting to the controller and the first few `[LEARN]` + `[FLOOD]` events.

<img width="525" height="325" alt="Screenshot_1" src="https://github.com/user-attachments/assets/68b46fe6-0566-47d1-8980-8e945c2e379c" />



---

