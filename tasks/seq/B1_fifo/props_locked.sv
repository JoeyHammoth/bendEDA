// SPDX-License-Identifier: Apache-2.0
// B1 FIFO: the locked SVA pack, translated from the Bend laws through the
// abstraction map (abs.yaml). One property per law, named as the manifest's
// `translation.sva`. Two laws (FIFO-F-07, FIFO-F-10) are ordering laws and are
// translated as a reference miter against the model as well; the assertions
// here are the RTL-side half of that miter, using the second-element register
// the abstraction map names.
//
// Not compiled in this repository yet: no SystemVerilog toolchain is available
// locally, and the OSS CAD image has not been asked to elaborate this file.
// The first `sby` run is part of #12, not of this draft.
`default_nettype none

module b1_fifo_props #(
  parameter int W = 32,
  parameter int D = 2
) (
  input logic clk,
  input logic rst_n,
  input logic push,
  input logic pop,
  input logic [W-1:0] din,
  input logic [W-1:0] dout,
  input logic full,
  input logic empty,
  input logic [1:0] count_q,
  input logic [W-1:0] head_q,
  input logic [W-1:0] second_q
);

  `define B1_RST (!rst_n)
  `define B1_PUSH_ONLY  (push && !pop)
  `define B1_POP_ONLY   (pop && !push)
  `define B1_BOTH       (push && pop)
  `define B1_NEITHER    (!push && !pop)

  // FIFO-S-01
  property p_count_within_depth;
    @(posedge clk) disable iff (`B1_RST) count_q <= D;
  endproperty
  a_count_within_depth: assert property (p_count_within_depth);

  // FIFO-S-02
  property p_full_iff_depth;
    @(posedge clk) disable iff (`B1_RST) full == (count_q == D);
  endproperty
  a_full_iff_depth: assert property (p_full_iff_depth);

  // FIFO-S-03
  property p_empty_iff_zero;
    @(posedge clk) disable iff (`B1_RST) empty == (count_q == 0);
  endproperty
  a_empty_iff_zero: assert property (p_empty_iff_zero);

  // FIFO-F-01
  property p_push_empty_count;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_PUSH_ONLY && count_q == 0) |=> count_q == 1;
  endproperty
  a_push_empty_count: assert property (p_push_empty_count);

  // FIFO-F-02
  property p_push_empty_head;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_PUSH_ONLY && count_q == 0) |=> dout == $past(din);
  endproperty
  a_push_empty_head: assert property (p_push_empty_head);

  // FIFO-F-03
  property p_push_half_full;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_PUSH_ONLY && count_q == 1) |=> full;
  endproperty
  a_push_half_full: assert property (p_push_half_full);

  // FIFO-F-04
  property p_push_full_noop;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_PUSH_ONLY && count_q == D) |=> count_q == D;
  endproperty
  a_push_full_noop: assert property (p_push_full_noop);

  // FIFO-F-05
  property p_pop_empty_noop;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_POP_ONLY && count_q == 0) |=> count_q == 0;
  endproperty
  a_pop_empty_noop: assert property (p_pop_empty_noop);

  // FIFO-F-06
  property p_pop_full_count;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_POP_ONLY && count_q == D) |=> count_q == D - 1;
  endproperty
  a_pop_full_count: assert property (p_pop_full_count);

  // FIFO-F-07: the second element becomes the head.
  property p_pop_full_next_head;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_POP_ONLY && count_q == D) |=> dout == $past(second_q);
  endproperty
  a_pop_full_next_head: assert property (p_pop_full_next_head);

  // FIFO-F-08
  property p_pushpop_half_count;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_BOTH && count_q == 1) |=> count_q == 1;
  endproperty
  a_pushpop_half_count: assert property (p_pushpop_half_count);

  // FIFO-F-09
  property p_pushpop_half_head;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_BOTH && count_q == 1) |=> dout == $past(din);
  endproperty
  a_pushpop_half_head: assert property (p_pushpop_half_head);

  // FIFO-F-10: the pop wins and the push is ignored.
  property p_pushpop_full_head;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_BOTH && count_q == D) |=> dout == $past(second_q);
  endproperty
  a_pushpop_full_head: assert property (p_pushpop_full_head);

  // FIFO-F-13: the push wins and the pop is ignored.
  property p_pushpop_empty_head;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_BOTH && count_q == 0) |=> dout == $past(din);
  endproperty
  a_pushpop_empty_head: assert property (p_pushpop_empty_head);

  // FIFO-F-11
  property p_reset_empty;
    @(posedge clk) !rst_n |=> empty && count_q == 0;
  endproperty
  a_reset_empty: assert property (p_reset_empty);

  // FIFO-F-12
  property p_idle_preserves_head;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_NEITHER && count_q > 0) |=> $stable(dout);
  endproperty
  a_idle_preserves_head: assert property (p_idle_preserves_head);

  // FIFO-F-14: idle leaves the occupancy alone.
  property p_idle_preserves_count;
    @(posedge clk) disable iff (`B1_RST) `B1_NEITHER |=> count_q == $past(count_q);
  endproperty
  a_idle_preserves_count: assert property (p_idle_preserves_count);

  // FIFO-F-15: at occupancy 0 the push wins, so occupancy becomes 1.
  property p_pushpop_empty_count;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_BOTH && count_q == 0) |=> count_q == 1;
  endproperty
  a_pushpop_empty_count: assert property (p_pushpop_empty_count);

  // FIFO-F-16: at occupancy D the pop wins, so occupancy becomes D-1.
  property p_pushpop_full_count;
    @(posedge clk) disable iff (`B1_RST)
      (`B1_BOTH && count_q == D) |=> count_q == D - 1;
  endproperty
  a_pushpop_full_count: assert property (p_pushpop_full_count);

  // Covers: the witnesses in LAWS.bend, as reachability on the RTL.
  c_reaches_full: cover property (@(posedge clk) disable iff (!rst_n) full);
  c_reaches_empty: cover property (@(posedge clk) disable iff (!rst_n) empty && $past(!empty));
  c_reaches_half: cover property (@(posedge clk) disable iff (!rst_n) count_q == 1);

  `undef B1_RST
  `undef B1_PUSH_ONLY
  `undef B1_POP_ONLY
  `undef B1_BOTH
  `undef B1_NEITHER

endmodule

`default_nettype wire
