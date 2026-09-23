# Samsung Controller

Python client for 18 Samsung VM55B-U panels (LH55VMBUBGBXGO) over Multiple Display Control. The protocol is plain TCP on port 1515. This package does not add a PIN or TLS layer.

The touch UI and the separate Windows window-layout tool are not in this repository yet. Window layouts stay on the desk PC and do not send MDC.

## Assumption

The earlier design named the protocol and the room, and it did not choose a language. This package is Python 3.11+ from the standard library so the frames can be tested without a panel.

## Room

Two walls are 2×4. Wall division is `0x24`. Screen index is 1–8 inside each wall, left to right, top to bottom. Panel 09 is index 1 on wall 2. Panels 17 and 18 have addresses and no wall cell.

Hosts are local configuration. Panel N uses `{network_prefix}.{N + host_offset}`. Copy the example and set the prefix for the network that can reach the panels:

```bash
cp config/panels.example.json config/panels.json
```

`config/panels.json` is gitignored. The checked-in example uses the documentation prefix `192.0.2`.

## Commands

Desk commands implemented here:

| Action | Command |
| --- | --- |
| Status | `0x00` |
| Power | `0x11` |
| Volume | `0x12` |
| Input | `0x14` |
| Screen size | `0x19` |
| Backlight (Manual Lamp, 0–100) | `0x58` |
| Video-wall mode | `0x5C` |
| Safety lock | `0x5D` |
| Video wall on | `0x84` |
| Model name | `0x8A` |
| Video-wall layout | `0x89` |
| Panel on/off (fast blank) | `0xF9` |

Allowed inputs are DVI `0x18`, HDMI1 `0x21`, HDMI2 `0x23`, and DisplayPort `0x25`. HDMI-PC source codes are rejected before they are sent.

On connect, the client probes power for device ids 0–10 and keeps the first id that ACKs. It does not send broadcast id `0xFE`.

A timeout or a closed socket marks that panel offline and leaves the others running. A NAK is not retried. After a successful power command (`0x11`), the session refuses another command to that panel for 60 seconds. Power-on times for a group are staggered with `stagger_times`; the default gap of 5 seconds is a starting assumption.

Picture brightness `0x25` is not the backlight control. White balance, gamma, MagicInfo, ticker, the virtual remote, and Tizen apps are out of the first screen.

## Check

```bash
python3 -m unittest discover -s tests -v
```

No formatter or linter is configured in this repository yet.
