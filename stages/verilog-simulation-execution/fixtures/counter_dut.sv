`timescale 1ns / 1ps

module counter_dut (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       en,
    output logic [3:0] count
);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            count <= 4'd0;
        end else if (en) begin
            count <= count + 4'd1;
        end
    end

endmodule
