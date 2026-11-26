// SPDX-License-Identifier: Apache-2.0
// Mutant: one edit, adding one to every unsaturated result.
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
      c <= sum[4] ? 4'd15 : sum[3:0] + 4'd1;
endmodule
`default_nettype wire
