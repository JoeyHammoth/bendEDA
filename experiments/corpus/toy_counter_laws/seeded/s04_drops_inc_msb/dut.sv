// SPDX-License-Identifier: Apache-2.0
// Seeded defect: the increment lost bit 3, and only bit 3.
//
// Every value in `plan.json` is 4 or less, so `inc[2:0]` carries the same number
// and `trace` sees a counter that agrees with the model on every simulated
// cycle. The SVA pack asks for `inc == 8` from zero, which this DUT drops, so
// `formal` rejects what the bounded window could not.
`default_nettype none
module toy_counter (
  input  wire       clk,
  input  wire       rst,
  input  wire       en,
  input  wire [3:0] inc,
  output reg  [3:0] c
);
  wire [4:0] sum = {1'b0, c} + {1'b0, inc[2:0]};

  always @(posedge clk)
    if (rst)
      c <= 4'd0;
    else if (en)
      c <= sum[4] ? 4'd15 : sum[3:0];
endmodule
`default_nettype wire
