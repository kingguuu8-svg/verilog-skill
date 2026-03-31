`timescale 1ns / 1ps

module tb_runtime_soft_fail;

    logic clk = 1'b0;
    string wave_file;

    always #5 clk = ~clk;

    initial begin
        if (!$value$plusargs("WAVE_FILE=%s", wave_file)) begin
            if (!$value$plusargs("wave=%s", wave_file)) begin
                wave_file = "tb_runtime_soft_fail.vcd";
            end
        end

        $dumpfile(wave_file);
        $dumpvars(0, tb_runtime_soft_fail);

        $display("SIM_START tb_runtime_soft_fail");
        repeat (2) @(posedge clk);
        $error("intentional soft runtime failure");
        $display("FINAL RESULT: FAILED");
        $finish;
    end

endmodule
