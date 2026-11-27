// SPDX-License-Identifier: Apache-2.0
// B1 reference submission (W=32, D=2). This is the `correct/as_shipped` design;
// every other entry replaces this one file.
//
// At depth 2 the queue is two registers, the occupancy is a 2-bit count, and the
// count selects the transition table in spec.md. The locked SVA pack is
// instantiated under FORMAL, because a wrapper cannot see a submodule's registers:
// the pack is written against the signals `abs.yaml` names, and the design that
// owns them connects them.
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

  reg [1:0]   count_q;
  reg [W-1:0] head_q;
  reg [W-1:0] second_q;

  assign dout  = head_q;
  assign full  = (count_q == DEPTH);
  assign empty = (count_q == 2'd0);

  always @(posedge clk) begin
    if (!rst_n) begin
      count_q  <= 2'd0;
      head_q   <= {W{1'b0}};
      second_q <= {W{1'b0}};
    end else begin
      case (count_q)
        2'd0:
          if (push) begin
            head_q  <= din;
            count_q <= 2'd1;
          end
        2'd1:
          if (push && pop) begin
            // Both succeed: the old head leaves and din becomes the only element.
            head_q <= din;
          end else if (push) begin
            second_q <= din;
            count_q  <= 2'd2;
          end else if (pop) begin
            count_q <= 2'd0;
          end
        DEPTH:
          if (pop) begin
            // MUTANT: at full a simultaneous push is granted and the pop is
            // dropped, so the occupancy stays at DEPTH.
            head_q  <= second_q;
            count_q <= push ? DEPTH : DEPTH - 2'd1;
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
    .head_q(head_q),
    .second_q(second_q)
  );
`endif

endmodule
`default_nettype wire
