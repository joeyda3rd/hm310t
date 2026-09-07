# Mutation testing

The initial mutation-testing campaign protects the safety-critical package
boundary in `src/hm310t/client.py` and `src/hm310t/transport.py`. It runs only
the hardware-free client and transport tests, with hardware markers explicitly
excluded by the checked-in Mutmut configuration.

Install the development dependencies, including Mutmut, then run:

```bash
mutmut run
mutmut results
```

Mutmut creates its temporary mutated checkout under `mutants/`, which is ignored.
It must not be run against the hardware contract suite. Review surviving mutants:
add a behavior-focused test for meaningful gaps, and document equivalent or
nonessential mutations instead of asserting private implementation details.

The pytest configuration excludes `mutants/` from normal test discovery, so a
completed mutation campaign cannot be collected as a second copy of the suite.

The initial campaign is intentionally manual. A scheduled or manually dispatched
CI integration can be considered once runtime and survivor triage are stable.

## Baseline result

The initial campaign was run on 2026-09-07 with Mutmut 3.7.0, Python 3.10, and
two workers. It generated 224 mutations: 179 were killed and 45 survived; there
were no timeouts, suspicious results, or untested mutations. It completed in
about six seconds after setup.

Survivors were reviewed. They fall into two categories:

- Error-message-only changes, where the exception type and control flow remain
  unchanged. Tests deliberately assert the typed failure contract rather than
  incidental wording.
- Equivalent changes in the HM310T's bounded 32-bit OPP representation. OPP is
  capped at 300.00 W, so its high 16-bit word is always zero; mutations to that
  word cannot change an observable valid device value.

The campaign initially exposed missing tests for constructor and setpoint
boundaries, connection argument forwarding, and independent protection status
bits. Those tests were added. No safety-critical control-flow mutation survives
the final run.
