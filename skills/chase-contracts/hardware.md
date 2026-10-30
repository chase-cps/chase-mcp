# Hardware: SystemVerilog Assertions and RTL

The meaning is that of the SVA standard (IEEE 1800-2017), not of a tool;
when a tool disagrees in a corner case, the user checks with that tool.
`parse_sva` reads the assertions of a design or a bind file as a contract:
`assume property` gives assumptions, `assert property` guarantees, one cycle
of the clock per step. Look at `skipped` first and tell the user which
properties were not read and why (local variables, `[->n]`, several clocks,
hierarchical names...); the contract says nothing about them. Signals in
`undeclared` were read as 1 bit: give their types (`inputs`/`outputs` with
types, or the declarations) when they are vectors. A property with `$past`
is checked from cycle `from_cycle`. The widths are those of Verilog:
`count == $past(count) + 1` does not wrap around (the constant has 32 bits).
`a |-> ##[1:$] b` is not read: in an assert it never fails; it means
`a |-> s_eventually b` when liveness is meant. `to_sva` gives the
checker module to run in a formal tool or a simulator; it does not run them.

## RTL

`is_implementation`, `is_environment`, and `is_receptive` take a Verilog or
SystemVerilog module (`rtl`: `top`, and `files` or `sources`). Call
`rtl_ports` first: the contract uses its port names and types (a 1-bit port
is a Boolean, a wider one a word; `names` renames ports). With `reset`, the
reset is not an input, and the contracts are checked from the step after the
reset. The checks are those of nuXmv: they suit small and medium modules.
