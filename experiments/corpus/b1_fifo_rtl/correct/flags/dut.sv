// SPDX-License-Identifier: Apache-2.0
// Correct, and structurally different: the occupancy is two presence flags, not a
// count. `full` is `have_second` and `empty` is `!have_head`; the count the pack
// reads is derived from the flags, and no transition table is indexed by it.
`default_nettype none
module b1_fifo #(
  parameter int W = 32,
  parameter int D = 2
) (
  input  wire         clk,
  input  wire         rst_n,
  input  wire         push,
  input  wire         pop,
  input  wire [W-1:0] din,
  output wire [W-1:0] dout,
  output wire         full,
  output wire         empty
);
  reg         have_head;
  reg         have_second;
  reg [W-1:0] head_q;
  reg [W-1:0] second_q;

  assign dout  = head_q;
  assign full  = have_second;
  assign empty = !have_head;

  // The abstraction map names a count; it is the flags added, not a register.
  // (Concatenating them would encode one-hot, and both flags set would read as 3.)
  wire [1:0] count_q = {1'b0, have_head} + {1'b0, have_second};

  always @(posedge clk) begin
    if (!rst_n) begin
      have_head   <= 1'b0;
      have_second <= 1'b0;
      head_q      <= {W{1'b0}};
      second_q    <= {W{1'b0}};
    end else if (!have_head) begin
      if (push) begin
        head_q    <= din;
        have_head <= 1'b1;
      end
    end else if (!have_second) begin
      if (push && pop) begin
        head_q <= din;
      end else if (push) begin
        second_q    <= din;
        have_second <= 1'b1;
      end else if (pop) begin
        have_head <= 1'b0;
      end
    end else if (pop) begin
      head_q      <= second_q;
      have_second <= 1'b0;
    end
  end

`ifdef FORMAL
  b1_fifo_props #(.W(W), .D(D)) u_props (
    .clk(clk),
    .rst_n(rst_n),
    .push(push),
    .pop(pop),
    .din(din),
    .dout(dout),
    .full(full),
    .empty(empty),
    .count_q(count_q),
    .head_q(head_q),
    .second_q(second_q)
  );
`endif

endmodule
`default_nettype wire
