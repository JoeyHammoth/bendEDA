// SPDX-License-Identifier: Apache-2.0
// Seeded defect: saturation exists, but one short of the contract's ceiling.
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
      c <= (sum > 5'd13) ? 4'd13 : sum[3:0];
endmodule
`default_nettype wire
