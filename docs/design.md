# VM55B-U control design

This note records the decisions brought over from the Samsung API design. Nothing here was checked against a live panel.

## Protocol

Use Samsung Multiple Display Control. Each panel has its own TCP socket on port 1515. Frames are `AA CMD ID LEN DATA… CHECKSUM`. The checksum is the low byte of every byte after `0xAA`.

An ACK is `AA FF ID LEN 'A' CMD DATA… CHECKSUM`. A NAK is `'N'` plus an error byte. The parser also accepts the longer form `'N' CMD ERR`. There is no login on this install. Do not add TLS or a PIN unless a panel refuses cleartext.

The packet id is the panel’s MDC device id. The scan range 0–10 is the probe list, not the assigned id. `0xFE` is a serial broadcast and is not used as a per-socket id.

## Desk commands

Commands named for this model: power `0x11`, volume `0x12`, input `0x14`, screen size `0x19`, video-wall mode `0x5C`, safety lock `0x5D`, video wall on `0x84`, video-wall layout `0x89`. Backlight is Manual Lamp `0x58` (0–100). Fast blank is panel on/off `0xF9`. Status is `0x00`. Model name is `0x8A`.

Any command outside that list stays off the first screen until one panel ACKs it. Video-wall mode values `0x00` (natural) and `0x01` (full) come from the general MDC spec and still need an ACK from a VM55B-U.

## Walls

Both drawn walls are 2×4, so wall division is `0x24` (row nibble, then column nibble). Index 1 is the top-left cell.

| Panels | Role |
| --- | --- |
| 01–08 | Wall 1, indexes 1–8 |
| 09–16 | Wall 2, indexes 1–8 |
| 17–18 | Addressed, no cell |

Do not invent a 2×5 wall for panels 17 and 18.

## Addressing

The map is static and lives in `config/panels.json`, which is not committed. Panel N is `{network_prefix}.{N + host_offset}`. The client does not scan the subnet.

## Failures

- Timeout or a closed socket: that panel is offline.
- NAK: the command or the value is unsupported. Do not retry it in a loop.
- Checksum or truncated frame: a bad frame, not a panel fault.
- After power `0x11` succeeds, wait 60 seconds before the next command to that set. Fast blank `0xF9` does not start that wait.
- Stagger power-on across the sets. The default gap is 5 seconds until a live run measures a better one.

## Separate from the panels

Saved window arrangements belong to a Windows desktop tool on the 55-inch desk PC (`EnumWindows`, `GetWindowRect`, `ShowWindow`, `SetWindowPos`). Recalling an arrangement must not change power, backlight, or wall division. That tool is not started.

MDC cannot draw the room map or the dashboards. Those come from the PCs feeding HDMI or DisplayPort.

## Still open

- A touch UI.
- A probe of one live panel for device id, backlight `0x58`, blank `0xF9`, and status `0x00`.
- Proof that the dev machine can open TCP 1515 to the panels.
- Where brightness presets and window layouts are stored.
- A recorded MDC fixture from a real panel. Current tests use constructed frames.
