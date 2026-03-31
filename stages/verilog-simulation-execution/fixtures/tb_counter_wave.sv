`timescale 1ns / 1ps

module tb_counter_wave;

    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic en = 1'b0;
    logic [3:0] count;
    string wave_file = "tb_counter_wave.vcd";
    bit wave_arg_seen;
    bit legacy_wave_arg_seen;

    counter_dut u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .en(en),
        .count(count)
    );

    always #5 clk = ~clk;

    initial begin
        wave_arg_seen = $value$plusargs("WAVE_FILE=%s", wave_file);
        legacy_wave_arg_seen = $value$plusargs("wave=%s", wave_file);

        $dumpfile(wave_file);
        $dumpvars(0, tb_counter_wave);

        $display("SIM_START tb_counter_wave");
        $display("SKILL_EVT|time_ps=%0t|kind=tb_start|name=tb_counter_wave", $time);
        repeat (2) @(posedge clk);
        @(negedge clk);
        rst_n = 1'b1;
        en = 1'b1;
        $display("SKILL_EVT|time_ps=%0t|kind=reset_release|signal=rst_n|value=%0b", $time, rst_n);
        $display("SKILL_EVT|time_ps=%0t|kind=enable_assert|signal=en|value=%0b", $time, en);

        repeat (4) begin
            @(posedge clk);
            $display("SKILL_EVT|time_ps=%0t|kind=count_sample|signal=count|value=%0d", $time, count);
        end
        @(negedge clk);
        if (count != 4'd4) begin
            $display("SIM_FAIL count=%0d", count);
            $fatal(1, "counter did not reach expected value");
        end

        $display("SKILL_EVT|time_ps=%0t|kind=simulation_pass|signal=count|value=%0d", $time, count);
        $display("SIM_PASS count=%0d", count);
        $finish;
    end

endmodule
