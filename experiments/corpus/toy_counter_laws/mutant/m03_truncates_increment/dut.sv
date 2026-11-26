// SPDX-License-Identifier: Apache-2.0
// Mutant: one edit, the increment lost its top two bits.
//
// It dropped only bit 3 at first, which the plan cannot see: no increment in
// `plan.json` exceeds 4, so the mutant was equivalent and no gate could reject it.
// The calibration said so (`GS 0.833`) instead of reporting a clean corpus.
`default_nettype none
module toy_counter (
  input  wire       clk,
  input  wire       rst,
  input  wire       en,
  input  wire [3:0] inc,
  output reg  [3:0] c
);
  wire [4:0] sum = {1'b0, c} + {1'b0, inc[1:0]};

  always @(posedge clk)
    if (rst)
      c <= 4'd0;
    else if (en)
      c <= sum[4] ? 4'd15 : sum[3:0];
endmodule
`default_nettype wire
