// SPDX-License-Identifier: Apache-2.0
// B1 FIFO: the locked SVA pack, translated from the Bend laws through the
// abstraction map (abs.yaml). One assertion per law, named as the manifest's
// `translation.sva`.
//
// Two laws (FIFO-F-07, FIFO-F-10) are ordering laws and their manifest template is
// `miter_ref_model_v1`, so the pack carries a transcription of `model.bend`'s `step`
// as a shadow (`m_a`, `m_b`, `m_level`) and asserts that a pop leaves the *model's*
// second element at the head. The shadow is the difference between a miter and a
// tautology. An earlier pack compared `dout` with the implementation's own `second_q`
// — the register `abs.yaml` names as `b` — so a design that accepted a push into a
// full queue, or that promoted the newest element to the head, satisfied its own law
// while disagreeing with the model about what the queue holds. The state map is an
// assumption a reviewer checks; the laws are the claims, and a claim about the queue's
// order has to name the queue's order, not the register the design chose to keep it in.
// `second_q` therefore stays in the port list as the abstraction map's interface (as
// `head_q` already does) and no assertion reads it.
//
// The assertions are immediate assertions in a clocked block, not named `property`
// blocks and not `assert property (@(posedge clk) ...)`. The pinned Yosys front end
// rejects the first with `unexpected TOK_PROPERTY` and the second with
// `unexpected '@'`; a pack the prover cannot parse is not a translation.
//
// A transition is judged one edge later: the `*_d` registers hold the state and
// inputs sampled at the previous edge, and the current `count_q`/`dout` are that
// transition's result. `started` keeps the first cycle out of the claims (its
// history would be fabricated), and `assume (!rst_n)` at that first cycle is the
// abstraction map's assumption that reset precedes the first operation: a 2-bit
// occupancy can otherwise start at 3, a state the design may never reach but the
// prover may choose. `rst_n` is unconstrained after that first cycle, so a reset that
// arrives mid-run is exercised too: `p_reset_empty` states what the edge after it
// must leave behind.
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

  reg [1:0] count_d;
  reg [W-1:0] din_d;
  reg [W-1:0] dout_d;
  reg push_d;
  reg pop_d;
  reg rst_n_d;
  reg empty_d;
  reg started = 1'b0;

  wire push_only_d = push_d && !pop_d;
  wire pop_only_d = pop_d && !push_d;
  wire both_d = push_d && pop_d;
  wire neither_d = !push_d && !pop_d;

  // The reference model, transcribed from `model.bend` at this package's reduced
  // instance: `m_a` is the head, `m_b` the second element, `m_level` the occupancy
  // (0 = Empty, 1 = Half, 2 = Full). One line of the model's `match` per arm, and
  // reset is the model's `reset` (all zero, Empty). It runs on the same edge and the
  // same decoded operation as the design, so at an assertion it holds the state the
  // previous edge produced, which is the state `dout` and `count_q` are compared to.
  reg [W-1:0] m_a;
  reg [W-1:0] m_b;
  reg [1:0] m_level;

  always @(posedge clk) begin
    if (!rst_n) begin
      m_a     <= {W{1'b0}};
      m_b     <= {W{1'b0}};
      m_level <= 2'd0;
    end else begin
      case (m_level)
        2'd0: begin
          // Empty: Push and PushPop both put din at the head; Pop and Idle are no-ops.
          if (push) begin
            m_a     <= din;
            m_level <= 2'd1;
          end
        end
        2'd1: begin
          // Half: PushPop keeps the level and replaces the head; Push fills the
          // second element; Pop empties the queue and leaves the data registers.
          if (push && pop) begin
            m_a <= din;
          end else if (push) begin
            m_b     <= din;
            m_level <= 2'd2;
          end else if (pop) begin
            m_level <= 2'd0;
          end
        end
        2'd2: begin
          // Full: the pop wins over a simultaneous push and promotes the second
          // element; a push alone is ignored, which is the worth of the model here.
          if (pop) begin
            m_a     <= m_b;
            m_level <= 2'd1;
          end
        end
        default: m_level <= 2'd0;
      endcase
    end
  end

  always @(posedge clk) begin
    if (!started)
      assume (!rst_n);

    if (started && rst_n) begin
      // FIFO-S-01
      p_count_within_depth: assert (count_q <= D);
      // FIFO-S-02
      p_full_iff_depth: assert (full == (count_q == D));
      // FIFO-S-03
      p_empty_iff_zero: assert (empty == (count_q == 0));
    end

    if (started) begin
      if (!rst_n_d) begin
        // FIFO-F-11: the cycle after reset.
        p_reset_empty: assert (empty && count_q == 0);
      end else begin
        // FIFO-F-01, FIFO-F-02
        if (push_only_d && count_d == 0) begin
          p_push_empty_count: assert (count_q == 1);
          p_push_empty_head: assert (dout == din_d);
        end
        // FIFO-F-03
        if (push_only_d && count_d == 1)
          p_push_half_full: assert (full);
        // FIFO-F-04
        if (push_only_d && count_d == D)
          p_push_full_noop: assert (count_q == D);
        // FIFO-F-05
        if (pop_only_d && count_d == 0)
          p_pop_empty_noop: assert (count_q == 0);
        // FIFO-F-06, FIFO-F-07
        if (pop_only_d && count_d == D) begin
          p_pop_full_count: assert (count_q == D - 1);
          p_pop_full_next_head: assert (dout == m_b);
        end
        // FIFO-F-08, FIFO-F-09
        if (both_d && count_d == 1) begin
          p_pushpop_half_count: assert (count_q == 1);
          p_pushpop_half_head: assert (dout == din_d);
        end
        // FIFO-F-15, FIFO-F-13
        if (both_d && count_d == 0) begin
          p_pushpop_empty_count: assert (count_q == 1);
          p_pushpop_empty_head: assert (dout == din_d);
        end
        // FIFO-F-16, FIFO-F-10
        if (both_d && count_d == D) begin
          p_pushpop_full_count: assert (count_q == D - 1);
          p_pushpop_full_head: assert (dout == m_b);
        end
        // FIFO-F-12
        if (neither_d && count_d > 0)
          p_idle_preserves_head: assert (dout == dout_d);
        // FIFO-F-14
        if (neither_d)
          p_idle_preserves_count: assert (count_q == count_d);
      end
    end

    count_d <= count_q;
    din_d <= din;
    dout_d <= dout;
    push_d <= push;
    pop_d <= pop;
    rst_n_d <= rst_n;
    started <= 1'b1;
  end

  // Covers: the witnesses in LAWS.bend, as reachability on the RTL.
  always @(posedge clk) begin
    if (started && rst_n) begin
      c_reaches_full: cover (full);
      c_reaches_empty: cover (empty && !empty_d);
      c_reaches_half: cover (count_q == 1);
    end
    empty_d <= empty;
  end

endmodule

`default_nettype wire
