// SPDX-License-Identifier: Apache-2.0
// Seeded defect: no saturation at all, so the counter wraps at 16.
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
