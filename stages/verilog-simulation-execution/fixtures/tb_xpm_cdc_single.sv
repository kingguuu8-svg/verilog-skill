`timescale 1ns / 1ps

module tb_xpm_cdc_single;

    logic src_clk = 1'b0;
    logic dest_clk = 1'b0;
    logic src_in = 1'b0;
    logic dest_out;

    xpm_cdc_single_dut u_dut (
        .src_clk (src_clk),
        .src_in  (src_in),
        .dest_clk(dest_clk),
        .dest_out(dest_out)
    );

    always #5 src_clk = ~src_clk;
    always #7 dest_clk = ~dest_clk;

    initial begin
        $display("SIM_START tb_xpm_cdc_single");
        repeat (3) @(posedge src_clk);
        src_in <= 1'b1;

        repeat (8) @(posedge dest_clk);
        if (dest_out !== 1'b1) begin
            $display("SIM_FAIL dest_out=%b", dest_out);
            $fatal(1, "xpm_cdc_single did not propagate the asserted source value");
        end

        $display("SIM_PASS dest_out=%b", dest_out);
        $finish;
    end

endmodule
