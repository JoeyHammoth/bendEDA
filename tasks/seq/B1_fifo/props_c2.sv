// SPDX-License-Identifier: Apache-2.0
// B1 FIFO: control pack C2, written from spec.md alone. It names no model
// symbol (no head_q, no second_q, no level): the shadow occupancy and ghost
// queue below are maintained from the interface only, which is what makes this
// pack independent of the Bend laws' vocabulary.
//
// STATUS: provisional. The specification says the pack must be authored by a
// different run than the law set; this package's C2 was written in the same
// session, so LC(C2) versus LC(C3) parity from this file would be confounded and
// must not be reported (LA6). It exists so the PA role has a starting point and
// so the shape of the disagreement is visible.
//
// Not compiled in this repository yet: no SystemVerilog toolchain is available
// locally, and the OSS CAD image has not been asked to elaborate this file.
`default_nettype none

module b1_fifo_c2_props #(
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
  input logic empty
);

  // Shadow state, derived from the interface only.
  int unsigned occ;
  logic [W-1:0] ghost[$];

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      occ <= 0;
      ghost.delete();
    end else begin
      unique case ({push, pop})
        2'b10: if (occ < D) begin
                 occ <= occ + 1;
                 ghost.push_back(din);
               end
        2'b01: if (occ > 0) begin
                 occ <= occ - 1;
                 void'(ghost.pop_front());
               end
        2'b11: if (occ == 0) begin
                 occ <= 1;
                 ghost.push_back(din);
               end else if (occ == D) begin
                 occ <= D - 1;
                 void'(ghost.pop_front());
               end else begin
                 void'(ghost.pop_front());
                 ghost.push_back(din);
               end
        default: ;
      endcase
    end
  end

  // R1: the design's own occupancy indication never contradicts the shadow.
  property c2_occ_bounds;
    @(posedge clk) disable iff (!rst_n) occ <= D;
  endproperty
  a2_occ_bounds: assert property (c2_occ_bounds);

  // R6 and R7: flags agree with the shadow occupancy.
  property c2_full_iff;
    @(posedge clk) disable iff (!rst_n) full == (occ == D);
  endproperty
  a2_full_iff: assert property (c2_full_iff);

  property c2_empty_iff;
    @(posedge clk) disable iff (!rst_n) empty == (occ == 0);
  endproperty
  a2_empty_iff: assert property (c2_empty_iff);

  // R9 and R5: while non-empty, dout is the oldest element the interface saw.
  property c2_head_visible;
    @(posedge clk) disable iff (!rst_n) (occ > 0) |-> dout == ghost[0];
  endproperty
  a2_head_visible: assert property (c2_head_visible);

  // R2 and R3: a request at the boundary does not change occupancy.
  property c2_push_full_noop;
    @(posedge clk) disable iff (!rst_n) (push && !pop && full) |=> full && $stable(dout);
  endproperty
  a2_push_full_noop: assert property (c2_push_full_noop);

  property c2_pop_empty_noop;
    @(posedge clk) disable iff (!rst_n) (pop && !push && empty) |=> empty;
  endproperty
  a2_pop_empty_noop: assert property (c2_pop_empty_noop);

  // R4: both requests at mid occupancy leave occupancy unchanged.
  property c2_pushpop_mid;
    @(posedge clk) disable iff (!rst_n)
      (push && pop && !full && !empty) |=> !full && !empty;
  endproperty
  a2_pushpop_mid: assert property (c2_pushpop_mid);

  // R8: reset clears both flags.
  property c2_reset_clears;
    @(posedge clk) !rst_n |=> empty && !full;
  endproperty
  a2_reset_clears: assert property (c2_reset_clears);

  c2_reaches_full: cover property (@(posedge clk) disable iff (!rst_n) full);
  c2_reaches_empty: cover property (@(posedge clk) disable iff (!rst_n) empty);
  c2_pushpop_same_cycle: cover property (@(posedge clk) disable iff (!rst_n) push && pop);

endmodule

`default_nettype wire
