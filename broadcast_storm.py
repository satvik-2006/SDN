#!/usr/bin/env python3

import argparse
import time
from scapy.all import Ether, sendp, get_if_hwaddr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iface", required=True)
    args = parser.parse_args()

    iface = args.iface
    src_mac = get_if_hwaddr(iface)

    print(f"[*] Sending 60 broadcast frames on {iface} (src={src_mac})")
    print("[*] Delay between frames: 0.05s  → rate ≈ 20.0 pkt/s")
    print("[*] Expected: controller blocks after 10 broadcasts in 5s window\n")

    for i in range(60):
        pkt = Ether(src=src_mac, dst="ff:ff:ff:ff:ff:ff")
        sendp(pkt, iface=iface, verbose=False)
        time.sleep(0.05)
        print(f"\r  Sent frame {i+1:2d}/60", end="")

    print("\n[+] Done. Check controller logs for [BLOCK] messages.")


if __name__ == "__main__":
    main()
