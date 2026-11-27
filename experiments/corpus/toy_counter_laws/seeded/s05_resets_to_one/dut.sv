// SPDX-License-Identifier: Apache-2.0
// Seeded defect: reset loads 1 instead of 0.
//
// `trace` rejects it at the first compared cycle: the reset edge is not a sample,
// so the DUT's first sample is 2 (reset to 1, then `inc = 1`) where the model's
// first step from 0 gives 1. The SVA pack does not mention reset at all — the model
// has no reset state, so there is no law to translate — and every transition
// property still holds from an arbitrary state, so `formal` accepts it. That is the
// division of labour between a trace compared with the model and properties
// translated from it.
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
      c <= 4'd1;
    else if (en)
      c <= sum[4] ? 4'd15 : sum[3:0];
endmodule
`default_nettype wire
