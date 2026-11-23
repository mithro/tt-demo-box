# USB-C power bank survey (2026-11-23)

Collected by a research agent from manufacturer spec pages, ChargerLAB teardowns and retailers
(Amazon blocks automated access). The Xiaomi P16ZM datasheet was checked directly.

## Key finding

Single-converter banks (nearly every 10K-20K bank) offer 12 V PD on one port at a time; with two
outputs in use every port falls back to 5 V. Xiaomi P16ZM datasheet: "(USB-C) 5V⎓3A 9V⎓2.23A
12V⎓1.67A 10V⎓2.25A MAX ... (3 ports) 5V⎓3A" (verified in the PDF). Similar statements: INIU
P512 "USB-C OUT1+USB-A OUT3: 5V⎓3A 15W(MAX)"; Anker Nano A1259 "Total: 24W Max ... 5V⎓4.8A";
Anker Zolo 10K "total output of 15W"; UGREEN PB550's IP5385 "two or more output ports
simultaneously only supports 5V". Plugging/unplugging a port also renegotiates all ports.
Only dual-converter banks (CUKTECH No.15, UGREEN PB723) keep 12 V on one port with another busy.

Hence the design runs everything at 5 V; a 12 V monitor uses a USB to 12 V DC cable with its own
boost converter.

## Candidates

| # | Model | Cap / Wh | L x W x H mm | Weight | Ports | 12 V PDO | Multi-port | Price seen |
|---|---|---|---|---|---|---|---|---|
| 1 | Xiaomi 10000 22.5W Lite P16ZM | 10000 / 37 | 148.4 x 73 x 15 | 227 g | C + 2A | yes | 5V⎓3A | - |
| 2 | INIU P512 | 20000 / 74 | 104 x 70 x 29 | 314 g | 2C + A | yes | 5V⎓3A 15W | AU$49.73 |
| 3 | UGREEN PB505 (built-in cable) | 20000 / 74 | 116.22 x 70.55 x 30.03 | 338 g | built-in C + C + A, all on top face | yes | 5V 3A | - |
| 4 | Xiaomi 20000 integrated cable PB2020 | 20000 / 74 | 128 x 73 x 32 | 342 g | built-in C + C + A | yes | 5V⎓3A | - |
| 5 | Anker Zolo 20K A1689 | 20000 | 119.9 x 73.4 x 31.5 | 318 g | built-in C + C + A | yes | likely 5 V | EUR36.99; 2025 recall list (some batches) |
| 6 | Anker Nano 10K A1259 | 10000 | 104 x 52.3 x 26 | 215 g | built-in C + C + A | yes | 24 W 5 V | US$49.99 |
| 7 | Anker Zolo 10K A1688 | 10000 | 109.9 x 65.5 x 25 | ~200 g | built-in C + C + A | yes | 15 W | EUR29.99 |
| 8 | CUKTECH 10 PB100 | 10000 / 36.5 | 80 x 58 x 28 | 196 g | C, A on opposite ends | yes | likely 5 V | - |
| 9 | UGREEN PB550 | 20000 / 72 | 139.11 x 80.42 x 26.92 | 394 g | built-in C + C + A | yes | 5 V only | - |
| 10 | Baseus Bipow PPBD20K | 20000 / 74 | 153 x 68.8 x 29.5 (listings conflict) | 452 g | C + 2A | yes | 5V/3A | - |
| 11 | CUKTECH No.15 PB200P | 20000 / 71.5 | 163 x 57 x 39.9 | 452 g | 2C + A | yes | independent C1 + C2 | AU$118.16 |
| 12 | UGREEN PB723 | 20000 / 72 | 131.1 x 54.5 x 50 | 482 g | built-in C + C + A | yes | independent 100 W + 30 W | - |

Rejected: Anker 737 A1289 (no 12 V on USB-C); INIU BI-B41 (5 V only, CPSC recall).

Run time: a 10K bank delivers ~27-30 Wh at 5 V (~5.5 h at 5 W); 20K ~55-62 Wh (~11-12 h).

Low-current: Anker banks need ~30-90 mA to stay on; trickle modes (Anker, Xiaomi) time out
after 2 h, so don't rely on them. The combined load (~1.3 A) is far above any threshold.
Pass-through charging: unconfirmed for every model.

Drawer envelope: bay ~158 x 82 x 34 inside + ~35 mm cable bay; fits 1-10. Per-model end-stop and
packing insert.

Sources: anker.com (A1259, A1289, A1688, A1689, rc2506 recall), chargerlab.com teardowns (PB505,
PB723, PB550, PB100, No.15), iniushop.com (P512), cpsc.gov (INIU recall), getic.com (Xiaomi
P16ZM datasheet), mi.com (PB2020 specs, low-current FAQ), wasserman.eu (Baseus), jacobsparts.com
(TRIGCAB-D trigger cable).
