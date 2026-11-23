# 5" VGA monitor survey (2026-11-23)

Collected by a research agent; AliExpress item pages hit reCAPTCHA after the first and Amazon
blocked automated access, so many figures come from AliExpress search results and listing
images (saved under `~/github/TinyTapeout/tmp/monitor-research/`). AliExpress prices were shown
in AUD (session geolocated to Australia); US$ at ~0.65.

No cased 5" VGA monitor was confirmed under US$30. The in-budget options are bare panel +
driver-board kits.

| # | Model / brands | Type | Size, res | Inputs | Power (5 V?) | Body W x H x D mm | Connectors | Mounting | Price seen |
|---|---|---|---|---|---|---|---|---|---|
| A | Eyoyo S501H | cased, metal | 5", 800x480 TN | DE-15 VGA, HDMI, AV | 12 V DC or micro-USB 5 V/2 A: yes | 124 x 79 x 18 (drawing: 4.88 / 3.11 / 0.7 in); active 108 x 64.8 | rear face, row along bottom edge | 1/4" thread in bottom edge; keyhole + 2 back holes (spacing unknown) | AliExpress AU$52.69 (item 1005005302099073); Amazon B07B8JNKT3 |
| B | Miktver 5" | cased, metal | 5", 800x480 IPS | HDMI, AV, VGA via proprietary USB-A-shaped socket + breakout | 12 V | "4.48 x 3.11 in" (~114 x 79, maybe typo for 4.88) | right side edge | 2 back screw holes | Amazon B0C77MXQCY |
| C | generic 5" metal touch | cased, metal | 5" | mini-HDMI, VGA via small port | 5 V/2 A | 126 x 96 x 17 (listing drawing) | one short side | 2 back holes 75 apart | AliExpress 1005013375562729, AU$74.77 |
| D | "800050" 5" VGA/CVBS kit | bare kit | 5", 800x480 | VGA on DE-15 pigtail, CVBS | 12 V 5521 jack; DC-to-USB 5 V cable included | panel 120.7 x 76.3, FPC 47; board 89 x 58 | board + keypad on ribbons | none | AliExpress 1005006173454033, AU$41.19 |
| E | ZJ050NA-08C / AT050TN22 640x480 kit | bare kit | 5", 640x480 4:3 | VGA, HDMI, AV on board | 12 V (5 V unconfirmed) | panel 117.65 x 88.43 x 5.9, active 101.76 x 76.32; board size unknown | board-mounted | none | AliExpress AU$25-31 (1005001705520738, 1005006038628520) |
| F | Adafruit 1678 | bare kit | 5", 800x480 | HDMI, VGA, composite | 5-12 V | panel 121 x 76 x 3.1, visible 108 x 65 | driver board on 4" FPC | none | US$64.95, out of stock |
| G | EastRising ER-TFTV050-3 | bare kit | 5", 800x480 | VGA, AV | ? | panel 120.9 x 75.95 x 2.9, active 108 x 64.8 | driver board | none | ? |
| H | 7" plastic car-style TFT monitor | cased | 7", 1024x600 | VGA, HDMI, AV | 12 V (one: 5-24 V) | 173 x 113 x 20 at rim + rear hump | right side of hump | U-bracket | AliExpress 1005004614276566, AU$39.79 |
| I | 7" metal IPS (LESOWN 7, Eyoyo EM07A, Miktver 7) | cased | 7", 1024x600 | VGA, HDMI, AV | 12 V | unverified | side/back | some VESA 75 | AU$46+ |
| J | AT070TN92 + PCB800099 | bare kit | 7", 800x480 | HDMI, VGA, 2xAV | 12 V | board 90.6 x 65.7 | board-mounted | 4 board holes | AliExpress 1005006369001145, AU$22.79 |

Excluded: LESOWN 5" "VESA metal shell" B0B1LPN3BT (HDMI only; 122.8 x 78.6 x 12.1, active
108 x 64.8); car rear-view 4.3"/5" (AV only); Waveshare 5"/7" HDMI (VGA only via external
adapter); 4.3" 480x272 kits (possible small fallback); CCTV testers (US$70+).

Envelope: every 5" 800x480 option shares a 108 x 64.8 active area; the 4:3 ZJ050 panel is
101.8 x 76.3. Cased 5" bodies max 126 x 96 x 20. Connectors: rear-facing (A), side (B, C, H),
pigtail (D), board (E, J). VESA 75 is not found on any 5" VGA unit.

Recommended references: Eyoyo S501H (cased, real DE-15, 5 V micro-USB, drawing confirmed);
ZJ050NA-08C kit (cheapest, native 640x480); "800050" kit (in-budget 800x480, 5 V cable included).

Not verified: Tim's Taobao unit; Miktver width; S501H back-hole spacing; ZJ050 board size and
holes; 7" metal dimensions; live US prices.
