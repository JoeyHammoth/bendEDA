// SPDX-License-Identifier: Apache-2.0
// SAT_counter: the SVA pack behind `counter.sby`.
//
// This wrapper instantiates the submitted `toy_counter` and translates the five
// transferable laws, one assertion each. It sees the DUT through its ports, so a
// corpus entry that replaces `dut.sv` is judged by these properties without
// editing them: an entry cannot make the proof vacuous by dropping the
// assertions, because the assertions are not in its file.
//
// The assertions are immediate assertions in a clocked block, not named
// `property` blocks and not `assert property (@(posedge clk) ...)`. Both of the
// latter are rejected by the pinned Yosys front end — `syntax error, unexpected
// TOK_PROPERTY` and `syntax error, unexpected '@'` respectively — and the pack
// has to be written in the subset the prover actually parses. This is the
// translation-fidelity constraint the design's L3 rung records; writing SVA that
// the solver refuses is not a translation.
//
// A transition is judged one edge later: `prev_*` hold the state and inputs
// sampled at the previous edge, and `c` at the current edge is that transition's
// result. The `prev_rst` guard keeps a reset edge out of the transition claims.
//
// `a_eight_from_zero` is not a law translation. It is the part of requirement R2
// that `plan.json` cannot reach (no increment above 4 is ever applied), and it
// exists so a design that keeps only the low three bits of `inc` is rejected by
// something. The laws are closed over literals, so R2 as a law is `step(3, 4)`.
`default_nettype none

module toy_counter_props (
  input  wire       clk,
  input  wire       rst,
  input  wire       en,
  input  wire [3:0] inc
);
  wire [3:0] c;

  toy_counter dut (
    .clk(clk),
    .rst(rst),
    .en(en),
    .inc(inc),
    .c(c)
  );

  reg [3:0] prev_c;
  reg [3:0] prev_inc;
  reg       prev_en;
  reg       prev_rst;
  // Without this, the first cycle has a fabricated history: `prev_*` are
  // unconstrained, so the solver can claim a transition that never happened and
  // refute a correct design. The initial value makes the transition claims start
  // at the second edge, when a real previous edge exists.
  reg       started = 1'b0;

  // counter_s01_never_above_ceiling / R1: the count never exceeds its ceiling.
  //
  // On a 4-bit register this is true by construction — no value of `c` can exceed
  // 15 — so it can never fire. It is kept because it is the translation of the
  // law, and the corpus records that the transition assertions, not this one, are
  // what reject a wrapping implementation.
  always @(posedge clk)
    if (!rst)
      a_never_above_ceiling: assert (c <= 4'd15);

  always @(posedge clk) begin
    if (started && !prev_rst && prev_en) begin
      // counter_s02_ceiling_holds_under_max_increment.
      if (prev_c == 4'd15 && prev_inc == 4'd15)
        a_ceiling_under_max_increment: assert (c == 4'd15);

      // counter_f01_sum_when_it_fits: below the ceiling, the sum is exact.
      if (prev_c == 4'd3 && prev_inc == 4'd4)
        a_sum_when_it_fits: assert (c == 4'd7);

      // counter_f02_exact_fit_reaches_ceiling.
      if (prev_c == 4'd14 && prev_inc == 4'd1)
        a_exact_fit: assert (c == 4'd15);

      // counter_f03_zero_increment_preserves_count.
      if (prev_c == 4'd7 && prev_inc == 4'd0)
        a_zero_increment: assert (c == 4'd7);

      // R2, at an increment the stimulus plan never applies.
      if (prev_c == 4'd0 && prev_inc == 4'd8)
        a_eight_from_zero: assert (c == 4'd8);
    end

    prev_c <= c;
    prev_inc <= inc;
    prev_en <= en;
    prev_rst <= rst;
    started <= 1'b1;
  end

endmodule

`default_nettype wire
