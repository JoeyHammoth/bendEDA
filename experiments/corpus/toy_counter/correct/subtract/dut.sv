// SPDX-License-Identifier: Apache-2.0
// Correct, and different again: it asks, before adding, whether the addition would
// pass the ceiling. No widened sum, no overflow bit.
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
      if (c > 4'd15 - inc)
        c <= 4'd15;
      else
        c <= c + inc;
endmodule
`default_nettype wire
