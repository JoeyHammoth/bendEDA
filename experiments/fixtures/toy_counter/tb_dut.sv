// SPDX-License-Identifier: Apache-2.0
// Testbench for the toy counter, driven by `+cycles=` and `stim.hex`.
//
// It writes one decimal sample per cycle, after the clock edge has settled, so
// the file is directly comparable with the model's per-cycle output. Timing
// models, not hierarchical pokes: the point is to run the design the way a
// simulator would.
`timescale 1ns/1ps
`default_nettype none
module tb_dut;
  reg        clk = 1'b0;
  reg        rst = 1'b1;
  reg        en  = 1'b1;
  reg  [3:0] inc = 4'd0;
  wire [3:0] c;
  reg  [3:0] stim [0:1023];
  integer    cycles;
  integer    i;
  integer    fd;

  toy_counter dut (.clk(clk), .rst(rst), .en(en), .inc(inc), .c(c));

  always #5 clk = ~clk;

  initial begin
    if (!$value$plusargs("cycles=%d", cycles))
      cycles = 16;
    $readmemh("stim.hex", stim);
    fd = $fopen("dut_trace.txt", "w");
    if (fd == 0) begin
      $display("tb_dut: cannot open dut_trace.txt");
      $finish;
    end

    // One edge in reset to load zero, then release and sample every cycle.
    @(posedge clk);
    #1 rst = 1'b0;
    for (i = 0; i < cycles; i = i + 1) begin
      inc = stim[i];
      @(posedge clk);
      #1;
      $fdisplay(fd, "%0d", c);
    end
    $fclose(fd);
    $finish;
  end
endmodule
`default_nettype wire
