# Output at start: [0]  (must be [0]; abort if not)

## Documented register dump
0x0001  Output on/off        = [0]
0x0002  Protect status       = [0]
0x0003  Specification/type   = [3010]
0x0004  Tail classification  = [19280]
0x0005  Decimal capacity     = [563]
0x0010  V display            = [0]
0x0011  I display            = [0]
0x0012  P display high       = [0]
0x0013  P display low        = [0]
0x0020  OVP                  = [1000]
0x0021  OCP                  = [1000]
0x0022  OPP high             = [0]
0x0023  OPP low              = [30000]
0x0030  Set V                = [600]
0x0031  Set I                = [2000]
0x9999  Comm address         = [1]

## Identity
0x0003 specification = [3010]  (expect [3010] = 30 V / 10 A)
0x0004 tail class    = [19280]  (record; semantics undocumented)
0x0005 decimals      = [563]  (expect [563] = 0x0233)

## Scaling (write setpoint, read raw; output stays off)
wrote Set V 2.00 -> raw 0x0030 = [200]  (expect [200])

## Byte order (asymmetric OPP, read both words)
wrote OPP 200.0 -> 0x0022 = [0] (expect [0])
                  0x0023 = [20000] (expect [20000])

## FC16 effective? (write a different value, read back)
wrote OPP 100.0 via FC16 -> read back [0, 10000]
  Effective if the read shows [0, 10000] (restored below).

## Error semantics (read an undocumented address)
0x00FF -> isError=False  (flags bad reads, or returns junk?)

## Read-only sweep 0x0000-0x0040 (flag undocumented responders)
  UNDOCUMENTED 0x0000 = [0]  <- check against the doc
  UNDOCUMENTED 0x0006 = [0]  <- check against the doc
  UNDOCUMENTED 0x0007 = [0]  <- check against the doc
  UNDOCUMENTED 0x0008 = [0]  <- check against the doc
  UNDOCUMENTED 0x0009 = [0]  <- check against the doc
  UNDOCUMENTED 0x000A = [0]  <- check against the doc
  UNDOCUMENTED 0x000B = [0]  <- check against the doc
  UNDOCUMENTED 0x000C = [0]  <- check against the doc
  UNDOCUMENTED 0x000D = [0]  <- check against the doc
  UNDOCUMENTED 0x000E = [0]  <- check against the doc
  UNDOCUMENTED 0x000F = [0]  <- check against the doc
  UNDOCUMENTED 0x0014 = [0]  <- check against the doc
  UNDOCUMENTED 0x0015 = [0]  <- check against the doc
  UNDOCUMENTED 0x0016 = [0]  <- check against the doc
  UNDOCUMENTED 0x0017 = [0]  <- check against the doc
  UNDOCUMENTED 0x0018 = [0]  <- check against the doc
  UNDOCUMENTED 0x0019 = [0]  <- check against the doc
  UNDOCUMENTED 0x001A = [0]  <- check against the doc
  UNDOCUMENTED 0x001B = [0]  <- check against the doc
  UNDOCUMENTED 0x001C = [0]  <- check against the doc
  UNDOCUMENTED 0x001D = [0]  <- check against the doc
  UNDOCUMENTED 0x001E = [0]  <- check against the doc
  UNDOCUMENTED 0x001F = [0]  <- check against the doc
  UNDOCUMENTED 0x0024 = [0]  <- check against the doc
  UNDOCUMENTED 0x0025 = [0]  <- check against the doc
  UNDOCUMENTED 0x0026 = [0]  <- check against the doc
  UNDOCUMENTED 0x0027 = [0]  <- check against the doc
  UNDOCUMENTED 0x0028 = [0]  <- check against the doc
  UNDOCUMENTED 0x0029 = [0]  <- check against the doc
  UNDOCUMENTED 0x002A = [0]  <- check against the doc
  UNDOCUMENTED 0x002B = [0]  <- check against the doc
  UNDOCUMENTED 0x002C = [0]  <- check against the doc
  UNDOCUMENTED 0x002D = [0]  <- check against the doc
  UNDOCUMENTED 0x002E = [0]  <- check against the doc
  UNDOCUMENTED 0x002F = [0]  <- check against the doc
  UNDOCUMENTED 0x0032 = [10]  <- check against the doc
  UNDOCUMENTED 0x0033 = [0]  <- check against the doc
  UNDOCUMENTED 0x0034 = [0]  <- check against the doc
  UNDOCUMENTED 0x0035 = [0]  <- check against the doc
  UNDOCUMENTED 0x0036 = [0]  <- check against the doc
  UNDOCUMENTED 0x0037 = [0]  <- check against the doc
  UNDOCUMENTED 0x0038 = [0]  <- check against the doc
  UNDOCUMENTED 0x0039 = [0]  <- check against the doc
  UNDOCUMENTED 0x003A = [0]  <- check against the doc
  UNDOCUMENTED 0x003B = [0]  <- check against the doc
  UNDOCUMENTED 0x003C = [0]  <- check against the doc
  UNDOCUMENTED 0x003D = [0]  <- check against the doc
  UNDOCUMENTED 0x003E = [0]  <- check against the doc
  UNDOCUMENTED 0x003F = [0]  <- check against the doc
  UNDOCUMENTED 0x0040 = [3200]  <- check against the doc

## Reconciliation against registers.py (2026-07-09, /dev/ttyUSB0, pymodbus 3.2.2)

Gate result: **PASS** — no contradictions with `registers.py`. Proceed to Task 1.

- [x] **Completeness:** every documented register (0x0001–0x0005, 0x0010–0x0013,
      0x0020–0x0023, 0x0030, 0x0031, 0x9999) responds with a sane value. The sweep's only
      non-zero undocumented responders are `0x0032 = [10]` and `0x0040 = [3200]`; per spec
      they are NOT mapped without doc semantics (recorded here). Every other 0x0000–0x0040
      address returns [0] with no error — see the error-semantics note.
- [x] **Decimals:** 0x0005 = 563 = 0x0233 (V 2dp / A 3dp / W 3dp). Confirmed.
- [x] **Rating:** 0x0003 = 3010 (30 V / 10 A). `EXPECTED_SPECIFICATION = 3010` is correct.
- [x] **Scaling:** Set V 2.00 → raw 200 (×100). Confirmed.
- [x] **Byte order:** OPP 200.0 → 0x0022 = 0, 0x0023 = 20000 (**high-word-first**). Confirmed —
      the non-symmetric proof a write/read roundtrip cannot give.
- [x] **FC16:** write [0, 10000] → read back [0, 10000]. Effective. Confirmed.
- [x] **OCP decimals:** the device's default OCP (0x0021 = 1000) reads as 10.00 A at 2dp
      (full-scale, the sensible default), consistent with the bug-#5 fix (OCP is 2dp).
- [!] **Error semantics:** reading undefined addresses (0x00FF and most of 0x0000–0x0040)
      returns `isError=False` with value [0] — the device does NOT reject bad-address reads.
      No impact on the library (it reads only mapped registers), but the transport cannot
      rely on the device to flag a wrong address; its `isError()`/exception handling still
      covers genuine error responses and IO failures. Informational.
- [x] **Tail classification:** 0x0004 = 19280 (0x4B50). Recorded; stays raw-only.

Device left as found: output OFF, Set V 6.00 V, OPP 300.00 W (verified by a post-run read).
