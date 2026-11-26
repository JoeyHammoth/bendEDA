// SPDX-License-Identifier: Apache-2.0
// The fixture's DUT: a 4-bit saturating counter, written as RTL rather than as
// Python so the conformance comparator can judge a real simulation.
//
// The sum is five bits wide on purpose. `c + inc` alone is four bits and wraps
// before the comparison, which is exactly the bug dut_wrap.sv contains.
`default_nettype none
module toy_counter (
  input  wire       clk,
  input  wire       rst,
  input  wire       en,
  input  wire [3:0] inc,
  output reg  [3:0] c
);
  wire [4:0] sum = {1'b0, c} + {1'b0, inc};

  always @(posedge clk)
    if (rst)
      c <= 4'd0;
    else if (en)
      c <= sum[4] ? 4'd15 : sum[3:0];
endmodule
`default_nettype wire
