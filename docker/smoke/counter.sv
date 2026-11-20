// SPDX-License-Identifier: Apache-2.0
// Smoke fixture for the OSS CAD image: a 4-bit counter that must never exceed
// 15, which BMC can prove in eight steps. It exists so `sby` has to reach a
// solver, not merely load a design.
module counter (
  input  wire       clk,
  input  wire       rst,
  output reg  [3:0]  c
);
  always @(posedge clk)
    if (rst) c <= 4'd0;
    else     c <= c + 4'd1;

`ifdef FORMAL
  always @(posedge clk)
    if (!rst) assert (c <= 4'd15);
`endif
endmodule
