// SPDX-License-Identifier: Apache-2.0
// Deliberately wrong DUT: it wraps at 16 instead of saturating.
//
// It exists so the gate has an RTL-level negative control. A comparator that
// calls this a pass is agreeing with a bug, and printing version numbers would
// never reveal that.
`default_nettype none
module toy_counter (
  input  wire       clk,
  input  wire       rst,
  input  wire       en,
  input  wire [3:0] inc,
  output reg  [3:0] c
);
  always @(posedge clk)
    if (rst)
      c <= 4'd0;
    else if (en)
      c <= c + inc;
endmodule
`default_nettype wire
