module pass_verilog_2005(a, b, y);
  input a;
  input b;
  output y;
  reg y;

  always @* begin
    y = a ^ b;
  end
endmodule
