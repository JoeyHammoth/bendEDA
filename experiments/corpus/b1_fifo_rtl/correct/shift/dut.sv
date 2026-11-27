// SPDX-License-Identifier: Apache-2.0
// Correct, and structurally different: the queue is a shift register rather than
// a head and a second register. A push shifts the new datum in behind the head;
// a pop shifts the second element down into the head. The occupancy is still a
// count because the pack's state map names `count_q`.
`default_nettype none
module b1_fifo #(
  parameter int W = 32,
  parameter int D = 2
) (
  input  wire         clk,
  input  wire         rst_n,
  input  wire         push,
  input  wire         pop,
  input  wire [W-1:0] din,
  output wire [W-1:0] dout,
  output wire         full,
  output wire         empty
);
  localparam [1:0] DEPTH = D[1:0];

  reg [2*W-1:0] queue_q;   // {second element, head}
  reg [1:0]     count_q;

  assign dout  = queue_q[W-1:0];
  assign full  = (count_q == DEPTH);
  assign empty = (count_q == 2'd0);

  always @(posedge clk) begin
    if (!rst_n) begin
      queue_q <= {2*W{1'b0}};
      count_q <= 2'd0;
    end else begin
      case (count_q)
        2'd0:
          if (push) begin
            queue_q <= {{W{1'b0}}, din};
            count_q <= 2'd1;
          end
        2'd1:
          if (push && pop) begin
            // The pop empties the queue and the push refills it with din.
            queue_q <= {{W{1'b0}}, din};
          end else if (push) begin
            // Shift din in behind the head.
            queue_q <= {din, queue_q[W-1:0]};
            count_q <= 2'd2;
          end else if (pop) begin
            count_q <= 2'd0;
          end
        DEPTH:
          if (pop) begin
            // Shift the second element down; a simultaneous push is ignored.
            queue_q <= {queue_q[2*W-1:W], queue_q[2*W-1:W]};
            count_q <= DEPTH - 2'd1;
          end
        default:
          count_q <= 2'd0;
      endcase
    end
  end

`ifdef FORMAL
  b1_fifo_props #(.W(W), .D(D)) u_props (
    .clk(clk),
    .rst_n(rst_n),
    .push(push),
    .pop(pop),
    .din(din),
    .dout(dout),
    .full(full),
    .empty(empty),
    .count_q(count_q),
    .head_q(queue_q[W-1:0]),
    .second_q(queue_q[2*W-1:W])
  );
`endif

endmodule
`default_nettype wire
