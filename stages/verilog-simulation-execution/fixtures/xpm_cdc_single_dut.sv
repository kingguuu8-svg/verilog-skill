`timescale 1ns / 1ps

module xpm_cdc_single_dut (
    input  logic src_clk,
    input  logic src_in,
    input  logic dest_clk,
    output logic dest_out
);

    xpm_cdc_single #(
        .DEST_SYNC_FF  (2),
        .INIT_SYNC_FF  (0),
        .SIM_ASSERT_CHK(0),
        .SRC_INPUT_REG (0)
    ) u_xpm_cdc_single (
        .src_clk (src_clk),
        .src_in  (src_in),
        .dest_clk(dest_clk),
        .dest_out(dest_out)
    );

endmodule
